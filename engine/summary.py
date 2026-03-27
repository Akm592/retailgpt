from __future__ import annotations
import os
import logging
from typing import List, Optional

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("summary")


class SummaryGenerator:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)

        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "summary_system.txt")
        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"Summary prompt not found at: {prompt_path}")

        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt,
            generation_config={
                "temperature": 0.2,
                "top_p": 0.95,
                "max_output_tokens": 300,
            }
        )
        logger.info("SummaryGenerator initialised")

    async def generate(
        self,
        transcript: List[dict],
        issue_type: Optional[str] = None,
        category: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> str:
        try:
            formatted = "\n".join(
                f"{msg.get('role','unknown').upper()}: {msg.get('content','')}"
                for msg in transcript if msg.get("content")
            )
            context_lines = []
            if issue_type:
                context_lines.append(f"Issue type: {issue_type}")
            if category:
                context_lines.append(f"Product category: {category}")
            if order_id:
                context_lines.append(f"Order ID: {order_id}")

            context_str = "\n".join(context_lines)
            prompt = f"{context_str}\n\nConversation:\n{formatted}" if context_str else f"Conversation:\n{formatted}"

            response = await self.model.generate_content_async(prompt)
            summary = response.text.strip()
            return summary if summary else "Customer contacted support. Details in conversation transcript."
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return "Summary unavailable. Please review the conversation transcript."


_summary_instance: Optional[SummaryGenerator] = None


def get_summary_generator() -> SummaryGenerator:
    global _summary_instance
    if _summary_instance is None:
        _summary_instance = SummaryGenerator()
    return _summary_instance


async def initialize_summary_generator():
    global _summary_instance
    _summary_instance = SummaryGenerator()


async def generate_summary(
    transcript: List[dict],
    issue_type: Optional[str] = None,
    category: Optional[str] = None,
    order_id: Optional[str] = None,
) -> str:
    return await get_summary_generator().generate(transcript, issue_type, category, order_id)
