from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional


@dataclass
class AssertionResult:
    passed: bool
    key: str
    expected: Any
    actual: Any
    message: str = ""


@dataclass
class TurnResult:
    turn_index: int
    description: str
    status: str  # PASS | FAIL | SKIP | ERROR
    assertions: List[AssertionResult] = field(default_factory=list)
    request: dict = field(default_factory=dict)
    response: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass
class TestResult:
    test_id: str
    description: str
    category: str      # nlu | button_routing | flow | escalation
    subcategory: str
    status: str        # PASS | FAIL | SKIP | ERROR
    turns: List[TurnResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def assertions_passed(self) -> int:
        return sum(1 for t in self.turns for a in t.assertions if a.passed)

    @property
    def assertions_failed(self) -> int:
        return sum(1 for t in self.turns for a in t.assertions if not a.passed)

    @property
    def failure_details(self) -> List[str]:
        details = []
        for t in self.turns:
            for a in t.assertions:
                if not a.passed:
                    details.append(f"Turn {t.turn_index} [{a.key}]: {a.message}")
        return details


def compute_scores(results: List[TestResult]) -> Dict[str, Any]:
    """Compute accuracy scores by category."""
    scores: Dict[str, Any] = {}

    def _accuracy(items: List[TestResult]) -> Dict[str, Any]:
        if not items:
            return {"passed": 0, "total": 0, "pct": None}
        passed = sum(1 for r in items if r.passed)
        total = len(items)
        return {"passed": passed, "total": total, "pct": round(passed / total * 100, 1)}

    nlu_all = [r for r in results if r.category == "nlu"]
    nlu_keyword = [r for r in nlu_all if "keyword" in _get_tags(r)]
    nlu_llm = [r for r in nlu_all if "llm" in _get_tags(r)]

    btn_all = [r for r in results if r.category == "button_routing"]
    flow_all = [r for r in results if r.category == "flow"]
    esc_all = [r for r in results if r.category == "escalation"]

    scores["nlu"] = _accuracy(nlu_all)
    scores["nlu_keyword"] = _accuracy(nlu_keyword)
    scores["nlu_llm"] = _accuracy(nlu_llm)
    scores["button_routing"] = _accuracy(btn_all)
    scores["flow"] = _accuracy(flow_all)
    scores["escalation"] = _accuracy(esc_all)

    # Per-subcategory breakdown for NLU
    nlu_subcats: Dict[str, List[TestResult]] = {}
    for r in nlu_all:
        nlu_subcats.setdefault(r.subcategory, []).append(r)
    scores["nlu_by_subcategory"] = {k: _accuracy(v) for k, v in nlu_subcats.items()}

    # Flow subcategory breakdown
    flow_subcats: Dict[str, List[TestResult]] = {}
    for r in flow_all:
        flow_subcats.setdefault(r.subcategory, []).append(r)
    scores["flow_by_subcategory"] = {k: _accuracy(v) for k, v in flow_subcats.items()}

    # NLU confidence average
    conf_vals = []
    for r in nlu_all:
        for t in r.turns:
            if t.response.get("nlu"):
                c = t.response["nlu"].get("confidence")
                if c is not None:
                    conf_vals.append(float(c))
    scores["nlu_confidence_avg"] = round(sum(conf_vals) / len(conf_vals), 3) if conf_vals else None

    # Overall
    non_skip = [r for r in results if r.status != "SKIP"]
    scores["overall"] = _accuracy(non_skip)

    return scores


def _get_tags(result: TestResult) -> List[str]:
    """Tags are stored in the test result metadata if present."""
    return getattr(result, "_tags", [])
