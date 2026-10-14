from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Any, Dict, List

from .scoring import TestResult, TurnResult

# ANSI colors
_G = "\033[92m"   # green
_R = "\033[91m"   # red
_Y = "\033[93m"   # yellow
_B = "\033[96m"   # cyan
_W = "\033[97m"   # white
_DIM = "\033[2m"
_RST = "\033[0m"


def print_terminal(results: List[TestResult], scores: Dict[str, Any]) -> None:
    """Print a colored terminal report."""
    print()
    for r in results:
        icon, color = {
            "PASS": ("PASS", _G),
            "FAIL": ("FAIL", _R),
            "SKIP": ("SKIP", _Y),
            "ERROR": ("ERR!", _Y),
        }.get(r.status, ("????", _W))

        ms = f"{r.duration_ms:.0f}ms"
        print(f"  {color}[{icon}]{_RST} {_DIM}{r.test_id:<40}{_RST} {_DIM}{ms:>6}{_RST}  {r.description}")

        if r.status in ("FAIL", "ERROR"):
            for detail in r.failure_details:
                print(f"         {_R}✗{_RST} {detail}")
            if r.error:
                print(f"         {_Y}⚠ {r.error}{_RST}")

    print()
    print(f"  {'─' * 60}")
    print(f"  {_B}SCORE SUMMARY{_RST}")
    print(f"  {'─' * 60}")

    def _row(label: str, s: Dict) -> str:
        if s["total"] == 0:
            return f"  {label:<34} {_DIM}(no tests){_RST}"
        pct = s["pct"]
        color = _G if pct >= 90 else (_Y if pct >= 75 else _R)
        bar = f"{color}{pct:5.1f}%{_RST}"
        return f"  {label:<34} {bar}  ({s['passed']}/{s['total']})"

    print(_row("NLU Accuracy", scores["nlu"]))
    print(_row("  └─ keyword tests", scores["nlu_keyword"]))
    print(_row("  └─ llm tests", scores["nlu_llm"]))
    for sub, s in scores.get("nlu_by_subcategory", {}).items():
        print(_row(f"     [{sub}]", s))
    print(_row("Button Routing Accuracy", scores["button_routing"]))
    print(_row("Flow Completion Rate", scores["flow"]))
    for sub, s in scores.get("flow_by_subcategory", {}).items():
        print(_row(f"  └─ {sub}", s))
    print(_row("Escalation Accuracy", scores["escalation"]))

    conf = scores.get("nlu_confidence_avg")
    if conf is not None:
        print(f"  {'NLU Avg Confidence':<34} {_B}{conf:.3f}{_RST}")

    print(f"  {'─' * 60}")
    overall = scores["overall"]
    pct = overall["pct"]
    if pct is not None:
        color = _G if pct >= 90 else (_Y if pct >= 75 else _R)
        print(f"  {'Overall Accuracy':<34} {color}{pct:5.1f}%{_RST}  ({overall['passed']}/{overall['total']})")
    print()


def write_html(results: List[TestResult], scores: Dict[str, Any], output_dir: str) -> str:
    """Write an HTML report and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"report_{ts}.html")

    def pct_color(pct):
        if pct is None:
            return "#888"
        if pct >= 90:
            return "#22c55e"
        if pct >= 75:
            return "#f59e0b"
        return "#ef4444"

    def score_row(label, s):
        if s["total"] == 0:
            return f'<tr><td>{label}</td><td style="color:#888">—</td><td style="color:#888">—</td></tr>'
        color = pct_color(s["pct"])
        return (f'<tr><td>{label}</td>'
                f'<td style="color:{color};font-weight:bold">{s["pct"]:.1f}%</td>'
                f'<td>{s["passed"]}/{s["total"]}</td></tr>')

    # Build scorecard rows
    score_rows = (
        score_row("NLU Accuracy", scores["nlu"])
        + score_row("&nbsp;&nbsp;└─ keyword tests", scores["nlu_keyword"])
        + score_row("&nbsp;&nbsp;└─ llm tests", scores["nlu_llm"])
        + "".join(score_row(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[{k}]", v)
                  for k, v in scores.get("nlu_by_subcategory", {}).items())
        + score_row("Button Routing Accuracy", scores["button_routing"])
        + score_row("Flow Completion Rate", scores["flow"])
        + "".join(score_row(f"&nbsp;&nbsp;└─ {k}", v)
                  for k, v in scores.get("flow_by_subcategory", {}).items())
        + score_row("Escalation Accuracy", scores["escalation"])
        + score_row("Overall", scores["overall"])
    )

    # Build test details
    def turn_html(t: TurnResult) -> str:
        color = {"PASS": "#22c55e", "FAIL": "#ef4444", "SKIP": "#f59e0b", "ERROR": "#f59e0b"}.get(t.status, "#888")
        req_json = json.dumps(t.request, indent=2, default=str)
        resp_json = json.dumps(t.response, indent=2, default=str)
        assertions_html = ""
        for a in t.assertions:
            ic = "✓" if a.passed else "✗"
            ac = "#22c55e" if a.passed else "#ef4444"
            msg = f" — {a.message}" if a.message else ""
            assertions_html += f'<div style="color:{ac}">{ic} <code>{a.key}</code>: expected={a.expected!r}{msg}</div>'
        if t.error:
            assertions_html += f'<div style="color:#f59e0b">⚠ {t.error}</div>'
        return f"""
        <details style="margin:4px 0;border-left:3px solid {color};padding-left:8px">
          <summary style="cursor:pointer;color:{color}">Turn {t.turn_index}: {t.description} [{t.status}] ({t.duration_ms:.0f}ms)</summary>
          <div style="margin-top:8px">{assertions_html}</div>
          <details style="margin-top:8px">
            <summary style="cursor:pointer;color:#888;font-size:0.85em">Request / Response JSON</summary>
            <pre style="background:#1e1e1e;color:#d4d4d4;padding:8px;border-radius:4px;font-size:0.75em;overflow-x:auto">{req_json}</pre>
            <pre style="background:#1e1e1e;color:#d4d4d4;padding:8px;border-radius:4px;font-size:0.75em;overflow-x:auto">{resp_json}</pre>
          </details>
        </details>"""

    test_rows = ""
    for r in results:
        color = {"PASS": "#22c55e", "FAIL": "#ef4444", "SKIP": "#f59e0b", "ERROR": "#f59e0b"}.get(r.status, "#888")
        turns_html = "".join(turn_html(t) for t in r.turns)
        failure_lines = "".join(f'<div style="color:#ef4444;margin:2px 0">✗ {d}</div>' for d in r.failure_details)
        test_rows += f"""
        <details style="border:1px solid #333;border-radius:6px;margin:6px 0;padding:8px">
          <summary style="cursor:pointer">
            <span style="color:{color};font-weight:bold">[{r.status}]</span>
            <code style="margin:0 8px">{r.test_id}</code>
            <span style="color:#888">{r.description}</span>
            <span style="color:#888;font-size:0.8em;float:right">{r.duration_ms:.0f}ms · {r.category}/{r.subcategory}</span>
          </summary>
          <div style="margin-top:8px">{failure_lines}{turns_html}</div>
        </details>"""

    conf = scores.get("nlu_confidence_avg")
    conf_row = f'<tr><td>NLU Avg Confidence</td><td style="color:#60a5fa;font-weight:bold">{conf:.3f}</td><td>—</td></tr>' if conf else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RetailGPT Eval Report — {ts}</title>
<style>
  body {{ background:#0f0f0f; color:#e5e5e5; font-family:system-ui,sans-serif; margin:0; padding:24px; }}
  h1,h2 {{ color:#f5f5f5; }}
  table {{ border-collapse:collapse; width:100%; max-width:600px; }}
  th,td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #333; }}
  th {{ color:#888; font-weight:normal; font-size:0.85em; }}
  code {{ background:#1e1e1e; padding:2px 5px; border-radius:3px; font-size:0.9em; }}
  details > summary {{ list-style:none; }}
  details > summary::-webkit-details-marker {{ display:none; }}
</style>
</head>
<body>
<h1>RetailGPT Evaluation Report</h1>
<p style="color:#888">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

<h2>Score Summary</h2>
<table>
  <tr><th>Category</th><th>Accuracy</th><th>Tests</th></tr>
  {score_rows}
  {conf_row}
</table>

<h2 style="margin-top:32px">Test Results</h2>
{test_rows}
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path
