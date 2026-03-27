from __future__ import annotations
import logging
from typing import Optional, List
from dataclasses import dataclass

from engine.nlu import RetailIntent, RetailCategory

logger = logging.getLogger("escalation")


@dataclass
class EscalationResult:
    should_escalate: bool
    reason: Optional[str]
    priority: str


def rule_customer_requested(intent: Optional[RetailIntent]) -> Optional[str]:
    if intent == RetailIntent.REQUEST_AGENT:
        return "customer_requested"
    return None


def rule_bot_fallback(fallback_count: int, threshold: int = 3) -> Optional[str]:
    if fallback_count >= threshold:
        return f"bot_fallback_limit_reached_{fallback_count}"
    return None


def rule_repeat_complaint(
    customer_id: Optional[str],
    order_id: Optional[str],
    intent: Optional[RetailIntent],
    open_handovers: List[dict]
) -> Optional[str]:
    if not customer_id or not order_id or not intent:
        return None
    issue_type = intent.value
    for h in open_handovers:
        if (
            h.get("order_id") == order_id
            and h.get("issue_type") == issue_type
            and h.get("status") not in ("resolved", "expired", "auto_closed")
        ):
            return f"repeat_complaint_open_ticket_{h.get('id', 'unknown')}"
    return None


def rule_payment_always_escalate(intent: Optional[RetailIntent]) -> Optional[str]:
    if intent == RetailIntent.PAYMENT_QUERY:
        return "payment_query_mandatory_escalation"
    return None


def rule_electronics_always_escalate(
    intent: Optional[RetailIntent],
    category: Optional[RetailCategory]
) -> Optional[str]:
    if (
        intent in (RetailIntent.QUALITY_ISSUE, RetailIntent.MISSING_ITEM, RetailIntent.WRONG_ITEM)
        and category == RetailCategory.ELECTRONICS
    ):
        return "electronics_mandatory_escalation"
    return None


def rule_negative_sentiment(negative_turns: int, threshold: int = 2) -> Optional[str]:
    if negative_turns >= threshold:
        return f"customer_frustrated_{negative_turns}_negative_turns"
    return None


def check_escalation(
    intent: Optional[RetailIntent],
    category: Optional[RetailCategory],
    negative_turns: int,
    fallback_count: int,
    open_handovers: List[dict],
    order_id: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> EscalationResult:

    for reason in [
        rule_customer_requested(intent),
        rule_bot_fallback(fallback_count),
        rule_repeat_complaint(customer_id, order_id, intent, open_handovers),
    ]:
        if reason:
            logger.info(f"Immediate escalation: {reason}")
            return EscalationResult(True, reason, "immediate")

    for reason in [
        rule_payment_always_escalate(intent),
        rule_electronics_always_escalate(intent, category),
    ]:
        if reason:
            logger.info(f"Mandatory escalation: {reason}")
            return EscalationResult(True, reason, "normal")

    sentiment_reason = rule_negative_sentiment(negative_turns)
    if sentiment_reason:
        logger.info(f"Sentiment escalation: {sentiment_reason}")
        return EscalationResult(True, sentiment_reason, "normal")

    return EscalationResult(False, None, "none")
