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

    # Case 0: text typed at a text_input step — follow the * wildcard directly,
    # bypassing NLU routing (the step expects free-form text, not a recognised intent).
    if current_step and current_step in FLOWS and not option_selected:
        step_render = FLOWS[current_step]["render"]
        if step_render.get("render_type") == "text_input":
            next_id = FLOWS[current_step].get("transitions", {}).get("*")
            if next_id and next_id in FLOWS:
                logger.info(f"text_input passthrough: {current_step} --> {next_id}")
                return FlowResult(dict(FLOWS[next_id]["render"]), next_id, next_id, False, None)

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

        # No valid transition — re-render current step with a nudge if it has options,
        # otherwise fall back to the friendly fallback menu.
        logger.warning(f"No transition for '{option_selected}' in step '{current_step}'")
        step_render = step_data["render"]
        if step_render.get("render_type") == "options" and step_render.get("options"):
            nudge = dict(step_render)
            nudge["message"] = "Please select one of the available options. " + step_render.get("message", "")
            return FlowResult(nudge, current_step, current_step, False, None)
        return FlowResult(dict(FLOWS["flow_fallback"]["render"]), "flow_fallback", "flow_fallback", False, None)

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

    # Default: UNKNOWN intent or no recognisable input.
    # If the user is mid-flow at an options step, re-render that step with a gentle
    # nudge so they stay in context instead of being dumped at the main menu.
    if current_step and current_step in FLOWS:
        step_render = FLOWS[current_step]["render"]
        if step_render.get("render_type") == "options" and step_render.get("options"):
            nudge = dict(step_render)
            nudge["message"] = (
                "I'm sorry, I didn't quite understand that. 😊 "
                + step_render.get("message", "")
            )
            return FlowResult(nudge, current_step, current_step, False, None)

    # Fresh session or at a non-options step — show friendly fallback with full menu.
    return FlowResult(dict(FLOWS["flow_fallback"]["render"]), "flow_fallback", "flow_fallback", False, None)
