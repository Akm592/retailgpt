from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass

from engine.nlu import RetailIntent, RetailCategory
from engine.flows import FLOWS, INTENT_TO_STEP

logger = logging.getLogger("flow_engine")


@dataclass
class FlowResult:
    render_instruction: dict
    next_flow: Optional[str]
    next_step: Optional[str]
    escalate: bool
    escalate_reason: Optional[str]


def process_turn(
    intent: Optional[RetailIntent],
    category: Optional[RetailCategory],
    option_selected: Optional[str],
    current_flow: Optional[str],
    current_step: Optional[str],
) -> FlowResult:
    """
    Flat step-graph navigation.

    current_step is the globally unique step ID (= ctx.flow_step).
    Both next_flow and next_step in FlowResult are set to the next global step ID.

    Case 1 — option selected at a known step: look up transition in FLOWS[current_step].
    Case 2 — NLU intent provided (text message): look up INTENT_TO_STEP.
    Default — show main menu.
    """

    # Case 1: navigating within the flat graph (option/upload selected at a known step)
    if current_step and current_step in FLOWS and option_selected:
        step_data = FLOWS[current_step]
        transitions = step_data.get("transitions", {})
        next_id = transitions.get(option_selected) or transitions.get("*")

        if next_id == "ESCALATE":
            logger.info(f"Escalation from step '{current_step}' via option '{option_selected}'")
            return FlowResult({}, current_step, "escalated", True, "flow_endpoint")

        if next_id and next_id in FLOWS:
            logger.info(f"Step transition: {current_step} --[{option_selected}]--> {next_id}")
            return FlowResult(dict(FLOWS[next_id]["render"]), next_id, next_id, False, None)

        # No valid transition found — return to main
        logger.warning(f"No transition for '{option_selected}' in step '{current_step}', returning to main")
        return FlowResult(dict(FLOWS["main"]["render"]), "main", "main", False, None)

    # Case 2: NLU-intent routing (text message or fresh session)
    if intent and intent != RetailIntent.UNKNOWN:
        if intent == RetailIntent.REQUEST_AGENT:
            return FlowResult({}, None, None, True, "customer_requested")

        intent_steps = INTENT_TO_STEP.get(intent, {})
        cat = category if category else RetailCategory.UNKNOWN
        step_id = intent_steps.get(cat) or intent_steps.get("*") or "main"

        if step_id == "ESCALATE":
            return FlowResult({}, None, None, True, f"mandatory_{intent.value}")

        if step_id in FLOWS:
            logger.info(f"Intent routing: {intent.value}/{cat.value} --> {step_id}")
            return FlowResult(dict(FLOWS[step_id]["render"]), step_id, step_id, False, None)

    # Default: show main menu
    return FlowResult(dict(FLOWS["main"]["render"]), "main", "main", False, None)
