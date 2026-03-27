from __future__ import annotations
import os
import json
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from enum import Enum

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("nlu")


class RetailIntent(str, Enum):
    TRACK_ORDER      = "track_order"
    CANCEL_ORDER     = "cancel_order"
    DELAYED_ORDER    = "delayed_order"
    MODIFY_ORDER     = "modify_order"
    QUALITY_ISSUE    = "quality_issue"
    MISSING_ITEM     = "missing_item"
    WRONG_ITEM       = "wrong_item"
    PAYMENT_QUERY    = "payment_query"
    COUPON_QUERY     = "coupon_query"
    DELIVERY_INSTR   = "delivery_instructions"
    REQUEST_AGENT    = "request_agent"
    QUANTITY_ISSUE   = "quantity_issue"
    UNKNOWN          = "unknown"


class RetailCategory(str, Enum):
    FB          = "fb"
    GROCERY     = "grocery"
    FASHION     = "fashion"
    ELECTRONICS = "electronics"
    UNKNOWN     = "unknown"


@dataclass
class NLUResult:
    intent: RetailIntent
    category: RetailCategory
    confidence: float
    sentiment: str
    order_id: Optional[str]
    entities: List[str] = field(default_factory=list)
    source: str = "llm"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "category": self.category.value,
            "confidence": self.confidence,
            "sentiment": self.sentiment,
            "order_id": self.order_id,
            "entities": self.entities,
            "source": self.source,
        }


KEYWORD_MAP: Dict[str, RetailIntent] = {
    "talk to agent":    RetailIntent.REQUEST_AGENT,
    "human please":     RetailIntent.REQUEST_AGENT,
    "talk to human":    RetailIntent.REQUEST_AGENT,
    "agent please":     RetailIntent.REQUEST_AGENT,
    "real person":      RetailIntent.REQUEST_AGENT,
    "support agent":    RetailIntent.REQUEST_AGENT,
    "speak to someone": RetailIntent.REQUEST_AGENT,
    "koi insaan":       RetailIntent.REQUEST_AGENT,
    "aadmi chahiye":    RetailIntent.REQUEST_AGENT,
    "where is my order":    RetailIntent.TRACK_ORDER,
    "order status":         RetailIntent.TRACK_ORDER,
    "track my order":       RetailIntent.TRACK_ORDER,
    "track order":          RetailIntent.TRACK_ORDER,
    "mera order kahan":     RetailIntent.TRACK_ORDER,
    "kab aayega":           RetailIntent.TRACK_ORDER,
    "order kab":            RetailIntent.TRACK_ORDER,
    "cancel order":         RetailIntent.CANCEL_ORDER,
    "cancel my order":      RetailIntent.CANCEL_ORDER,
    "order cancel":         RetailIntent.CANCEL_ORDER,
    "cancel karna":         RetailIntent.CANCEL_ORDER,
    "order band karo":      RetailIntent.CANCEL_ORDER,
    "quality issue":        RetailIntent.QUALITY_ISSUE,
    "food was cold":        RetailIntent.QUALITY_ISSUE,
    "food is cold":         RetailIntent.QUALITY_ISSUE,
    "stale food":           RetailIntent.QUALITY_ISSUE,
    "khana kharab":         RetailIntent.QUALITY_ISSUE,
    "khana thanda":         RetailIntent.QUALITY_ISSUE,
    "missing item":         RetailIntent.MISSING_ITEM,
    "item missing":         RetailIntent.MISSING_ITEM,
    "item not received":    RetailIntent.MISSING_ITEM,
    "item nahi mila":       RetailIntent.MISSING_ITEM,
    "nahi aaya":            RetailIntent.MISSING_ITEM,
    "payment issue":        RetailIntent.PAYMENT_QUERY,
    "payment query":        RetailIntent.PAYMENT_QUERY,
    "refund status":        RetailIntent.PAYMENT_QUERY,
    "paisa wapas":          RetailIntent.PAYMENT_QUERY,
    "amount deducted":      RetailIntent.PAYMENT_QUERY,
    "quantity issue":       RetailIntent.QUANTITY_ISSUE,
    "quantity less":        RetailIntent.QUANTITY_ISSUE,
    "quantity kam":         RetailIntent.QUANTITY_ISSUE,
    "kam mila":             RetailIntent.QUANTITY_ISSUE,
    "thoda kam":            RetailIntent.QUANTITY_ISSUE,
    "portion issue":        RetailIntent.QUANTITY_ISSUE,
}


class NLUClassifier:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in environment")

        genai.configure(api_key=api_key)

        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "nlu_system.txt")
        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"NLU system prompt not found at: {prompt_path}")

        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt,
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95,
                "max_output_tokens": 256,
                "response_mime_type": "application/json",
            }
        )
        logger.info("NLUClassifier initialised")

    async def classify(self, message: str, known_category: Optional[str] = None) -> NLUResult:
        clean = message.strip()

        keyword_result = self._check_keywords(clean)
        if keyword_result:
            return keyword_result

        try:
            prompt = f"Customer message: {clean}"
            if known_category and known_category != "unknown":
                prompt += f"\nContext: product category already identified as '{known_category}'"
            response = await self.model.generate_content_async(prompt)
            return self._parse(response.text, known_category)
        except Exception as e:
            logger.error(f"NLU Gemini error: {e}")
            return self._fallback(known_category)

    def _check_keywords(self, message: str) -> Optional[NLUResult]:
        msg_lower = message.lower()
        for keyword, intent in KEYWORD_MAP.items():
            if keyword in msg_lower:
                logger.info(f"Keyword match: '{keyword}' -> {intent}")
                return NLUResult(
                    intent=intent,
                    category=RetailCategory.UNKNOWN,
                    confidence=0.97,
                    sentiment="neutral",
                    order_id=None,
                    entities=[],
                    source="keyword"
                )
        return None

    def _parse(self, response_text: str, known_category: Optional[str] = None) -> NLUResult:
        try:
            data = json.loads(response_text)

            intent_str = data.get("intent", "unknown").lower()
            try:
                intent = RetailIntent(intent_str)
            except ValueError:
                intent = RetailIntent.UNKNOWN

            category_str = data.get("category", "unknown").lower()
            try:
                category = RetailCategory(category_str)
            except ValueError:
                category = RetailCategory.UNKNOWN
            if category == RetailCategory.UNKNOWN and known_category:
                try:
                    category = RetailCategory(known_category)
                except ValueError:
                    pass

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            sentiment = data.get("sentiment", "neutral")
            if sentiment not in ("positive", "neutral", "negative"):
                sentiment = "neutral"

            order_id = data.get("order_id") or None
            if order_id:
                order_id = str(order_id).strip()

            entities = data.get("entities", [])
            if not isinstance(entities, list):
                entities = []
            entities = [str(e) for e in entities if e]

            return NLUResult(
                intent=intent,
                category=category,
                confidence=confidence,
                sentiment=sentiment,
                order_id=order_id,
                entities=entities,
                source="llm"
            )
        except Exception as e:
            logger.error(f"NLU parse error: {e} | response: {response_text[:200]}")
            return self._fallback(known_category)

    def _fallback(self, known_category: Optional[str] = None) -> NLUResult:
        try:
            cat = RetailCategory(known_category) if known_category else RetailCategory.UNKNOWN
        except ValueError:
            cat = RetailCategory.UNKNOWN
        return NLUResult(
            intent=RetailIntent.UNKNOWN,
            category=cat,
            confidence=0.3,
            sentiment="neutral",
            order_id=None,
            entities=[],
            source="fallback"
        )


_nlu_instance: Optional[NLUClassifier] = None


def get_nlu_classifier() -> NLUClassifier:
    global _nlu_instance
    if _nlu_instance is None:
        _nlu_instance = NLUClassifier()
    return _nlu_instance


async def initialize_nlu_classifier():
    global _nlu_instance
    _nlu_instance = NLUClassifier()
    logger.info("NLUClassifier singleton ready")
