#!/usr/bin/env python3
"""
RetailGPT Test Evaluator
Usage:
  python eval/test_evaluator.py [OPTIONS]
  # or: python -m eval.test_evaluator [OPTIONS]

  --base-url TEXT        API base URL  [default: http://localhost:8000]
  --category TEXT        Run only: nlu | button_routing | flow | escalation
  --tags TEXT            Comma-separated tags to include
  --exclude-tags TEXT    Comma-separated tags to exclude (e.g. llm)
  --concurrency INT      Parallel sessions  [default: 3]
  --timeout INT          Per-request timeout seconds  [default: 10]
  --output-dir PATH      Report output directory  [default: eval/reports]
  --no-html              Skip HTML report
  --fail-fast            Stop on first failure
  --verbose              Print full JSON per turn to stdout
  --threshold FLOAT      Exit 1 if overall accuracy < this  [default: 0.85]
  --with-orders-api      Treat flow_step_oneof as exact match (orders API available)
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure the project root is on sys.path so `eval` is importable when
# running as `python eval/test_evaluator.py` from the project root.
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import httpx
import yaml

from eval.runner import run_test
from eval.scoring import TestResult, compute_scores
from eval.reporter import print_terminal, write_html

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval")


def load_cases(cases_dir: str) -> List[dict]:
    """Load all YAML test case files from cases_dir."""
    cases = []
    cases_path = Path(cases_dir)
    for yml_file in sorted(cases_path.glob("*.yaml")):
        with open(yml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            for item in data:
                item.setdefault("_source_file", yml_file.name)
            cases.extend(data)
    return cases


def filter_cases(
    cases: List[dict],
    category: str | None,
    include_tags: List[str],
    exclude_tags: List[str],
    filter_text: str | None,
) -> List[dict]:
    filtered = []
    for c in cases:
        # Category filter
        if category and c.get("category") != category:
            continue

        # Tag filters
        tags = set(c.get("tags", []))
        if include_tags and not any(t in tags for t in include_tags):
            continue
        if exclude_tags and any(t in tags for t in exclude_tags):
            continue

        # Text filter (id or description)
        if filter_text:
            haystack = f"{c.get('id','')} {c.get('description','')}".lower()
            if filter_text.lower() not in haystack:
                continue

        filtered.append(c)
    return filtered


async def run_all(
    cases: List[dict],
    base_url: str,
    concurrency: int,
    timeout: int,
    fail_fast: bool,
    with_orders_api: bool,
    verbose: bool,
) -> List[TestResult]:
    results: List[TestResult] = []
    failed = False
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:

        async def _run_one(case: dict) -> TestResult:
            async with sem:
                result = await run_test(case, client, with_orders_api=with_orders_api)
                return result

        tasks = [asyncio.create_task(_run_one(c)) for c in cases]

        for task in asyncio.as_completed(tasks):
            result = await task

            if verbose:
                _print_verbose(result)

            results.append(result)

            if fail_fast and result.status in ("FAIL", "ERROR"):
                if not failed:
                    failed = True
                    # Cancel remaining tasks
                    for t in tasks:
                        if not t.done():
                            t.cancel()

    # Sort results to match original case order by test_id
    id_order = {c["id"]: i for i, c in enumerate(cases)}
    results.sort(key=lambda r: id_order.get(r.test_id, 9999))
    return results


def _print_verbose(result: TestResult) -> None:
    import json
    print(f"\n{'='*60}")
    print(f"TEST: {result.test_id}  [{result.status}]")
    for t in result.turns:
        print(f"\n  Turn {t.turn_index}: {t.description}  [{t.status}]")
        if t.request:
            print("  REQUEST:", json.dumps(t.request, indent=4, default=str))
        if t.response:
            print("  RESPONSE:", json.dumps(t.response, indent=4, default=str))
        for a in t.assertions:
            mark = "✓" if a.passed else "✗"
            print(f"  {mark} {a.key}: expected={a.expected!r}  actual={a.actual!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="RetailGPT Test Evaluator")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--cases", default="eval/cases", help="Path to cases directory")
    parser.add_argument("--category", default=None, help="nlu|button_routing|flow|escalation")
    parser.add_argument("--tags", default=None, help="Comma-separated tags to include")
    parser.add_argument("--exclude-tags", default=None, help="Comma-separated tags to exclude")
    parser.add_argument("--filter", default=None, dest="filter_text", help="Filter by id/description substring")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--output-dir", default="eval/reports")
    parser.add_argument("--no-html", action="store_true", help="Skip HTML report")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.85, help="Min overall accuracy (0-1) to exit 0")
    parser.add_argument("--with-orders-api", action="store_true", dest="with_orders_api")
    args = parser.parse_args()

    include_tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    exclude_tags = [t.strip() for t in args.exclude_tags.split(",")] if args.exclude_tags else []

    # Load and filter cases
    all_cases = load_cases(args.cases)
    cases = filter_cases(all_cases, args.category, include_tags, exclude_tags, args.filter_text)

    if not cases:
        print("No test cases match the given filters.")
        return 0

    print(f"\n  RetailGPT Evaluator  →  {args.base_url}")
    print(f"  Cases: {len(cases)} / {len(all_cases)} loaded")
    if args.category:
        print(f"  Category filter: {args.category}")
    if exclude_tags:
        print(f"  Excluding tags: {exclude_tags}")
    print()

    # Run
    results = asyncio.run(run_all(
        cases=cases,
        base_url=args.base_url,
        concurrency=args.concurrency,
        timeout=args.timeout,
        fail_fast=args.fail_fast,
        with_orders_api=args.with_orders_api,
        verbose=args.verbose,
    ))

    # Score and report
    scores = compute_scores(results)
    print_terminal(results, scores)

    if not args.no_html:
        html_path = write_html(results, scores, args.output_dir)
        print(f"  HTML report: {html_path}\n")

    # Exit code
    overall_pct = scores["overall"].get("pct")
    if overall_pct is None:
        return 0
    threshold_pct = args.threshold * 100
    return 0 if overall_pct >= threshold_pct else 1


if __name__ == "__main__":
    sys.exit(main())
