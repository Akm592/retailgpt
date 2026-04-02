from __future__ import annotations
from typing import Any, Dict, List
from .scoring import AssertionResult


def _get_nested(obj: Any, dotpath: str) -> Any:
    """Traverse a nested dict/list using dot notation, e.g. 'next_context.flow_step'."""
    parts = dotpath.split(".")
    cur = obj
    for part in parts:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def evaluate(response: dict, expect: dict) -> List[AssertionResult]:
    """
    Evaluate all assertion keys in `expect` against `response`.
    Returns a list of AssertionResult (one per assertion key).
    """
    results: List[AssertionResult] = []

    for key, expected in expect.items():
        result = _check(response, key, expected)
        if result is not None:
            results.append(result)

    return results


def _check(response: dict, key: str, expected: Any) -> AssertionResult | None:
    """Dispatch to the right assertion handler based on key."""

    # ── render_type ───────────────────────────────────────────────────────────
    if key == "render_type":
        actual = response.get("render_type")
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected={expected!r}, actual={actual!r}"
        )

    # ── message_contains ─────────────────────────────────────────────────────
    if key == "message_contains":
        actual = response.get("message", "")
        passed = expected.lower() in actual.lower()
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual[:120],
            message="" if passed else f"'{expected}' not found in message"
        )

    # ── message_not_contains ─────────────────────────────────────────────────
    if key == "message_not_contains":
        actual = response.get("message", "")
        passed = expected.lower() not in actual.lower()
        return AssertionResult(
            passed=passed, key=key, expected=f"NOT {expected!r}", actual=actual[:120],
            message="" if passed else f"'{expected}' unexpectedly found in message"
        )

    # ── options_include_id ────────────────────────────────────────────────────
    if key == "options_include_id":
        opts = response.get("options") or []
        actual_ids = {o.get("id") for o in opts}
        missing = [e for e in expected if e not in actual_ids]
        passed = len(missing) == 0
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=list(actual_ids),
            message="" if passed else f"missing option IDs: {missing}"
        )

    # ── options_exact_ids ─────────────────────────────────────────────────────
    if key == "options_exact_ids":
        opts = response.get("options") or []
        actual_ids = {o.get("id") for o in opts}
        passed = actual_ids == set(expected)
        return AssertionResult(
            passed=passed, key=key, expected=sorted(expected), actual=sorted(actual_ids),
            message="" if passed else f"expected {sorted(expected)}, got {sorted(actual_ids)}"
        )

    # ── options_count_min ─────────────────────────────────────────────────────
    if key == "options_count_min":
        opts = response.get("options") or []
        actual = len(opts)
        passed = actual >= expected
        return AssertionResult(
            passed=passed, key=key, expected=f">={expected}", actual=actual,
            message="" if passed else f"expected >= {expected} options, got {actual}"
        )

    # ── next_context.flow_step (exact) ────────────────────────────────────────
    if key == "next_context.flow_step":
        nc = response.get("next_context") or {}
        actual = nc.get("flow_step") if isinstance(nc, dict) else None
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected step={expected!r}, got={actual!r}"
        )

    # ── next_context.flow_step_oneof ──────────────────────────────────────────
    if key == "next_context.flow_step_oneof":
        nc = response.get("next_context") or {}
        actual = nc.get("flow_step") if isinstance(nc, dict) else None
        passed = actual in expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"step={actual!r} not in {expected}"
        )

    # ── generic next_context.* dot-notation ──────────────────────────────────
    if key.startswith("next_context."):
        nc = response.get("next_context") or {}
        subkey = key[len("next_context."):]
        actual = nc.get(subkey) if isinstance(nc, dict) else None
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected={expected!r}, actual={actual!r}"
        )

    # ── escalate ─────────────────────────────────────────────────────────────
    if key == "escalate":
        actual = response.get("escalate", False)
        passed = bool(actual) == bool(expected)
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected escalate={expected}, got {actual}"
        )

    # ── escalate_reason_contains ─────────────────────────────────────────────
    if key == "escalate_reason_contains":
        actual = response.get("escalate_reason") or ""
        passed = expected.lower() in actual.lower()
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"'{expected}' not in escalate_reason={actual!r}"
        )

    # ── NLU assertions ────────────────────────────────────────────────────────
    if key == "nlu_intent":
        nlu = response.get("nlu") or {}
        actual = nlu.get("intent")
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected intent={expected!r}, got={actual!r}"
        )

    if key == "nlu_confidence_min":
        nlu = response.get("nlu") or {}
        actual = nlu.get("confidence")
        if actual is None:
            return AssertionResult(
                passed=False, key=key, expected=f">={expected}", actual=None,
                message="nlu.confidence is None (no NLU result)"
            )
        passed = float(actual) >= float(expected)
        return AssertionResult(
            passed=passed, key=key, expected=f">={expected}", actual=actual,
            message="" if passed else f"confidence {actual} < {expected}"
        )

    if key == "nlu_sentiment":
        nlu = response.get("nlu") or {}
        actual = nlu.get("sentiment")
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected sentiment={expected!r}, got={actual!r}"
        )

    if key == "nlu_category":
        nlu = response.get("nlu") or {}
        actual = nlu.get("category")
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected category={expected!r}, got={actual!r}"
        )

    if key == "nlu_source":
        nlu = response.get("nlu") or {}
        actual = nlu.get("source")
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected source={expected!r}, got={actual!r}"
        )

    # ── ticket_raised ─────────────────────────────────────────────────────────
    if key == "ticket_raised":
        actual = response.get("ticket_raised", False)
        passed = bool(actual) == bool(expected)
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected ticket_raised={expected}, got {actual}"
        )

    # ── issue_type ────────────────────────────────────────────────────────────
    if key == "issue_type":
        actual = response.get("issue_type")
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected issue_type={expected!r}, got={actual!r}"
        )

    # ── upload_config.* ───────────────────────────────────────────────────────
    if key.startswith("upload_config."):
        uc = response.get("upload_config") or {}
        subkey = key[len("upload_config."):]
        actual = uc.get(subkey) if isinstance(uc, dict) else None
        passed = actual == expected
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected {key}={expected!r}, got={actual!r}"
        )

    # ── terminal ──────────────────────────────────────────────────────────────
    if key == "terminal":
        actual = response.get("terminal", False)
        passed = bool(actual) == bool(expected)
        return AssertionResult(
            passed=passed, key=key, expected=expected, actual=actual,
            message="" if passed else f"expected terminal={expected}, got {actual}"
        )

    # Unknown assertion key — skip silently
    return None
