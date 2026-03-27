from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

ORDERS_API_BASE_URL: str = os.getenv("ORDERS_API_BASE_URL", "")


# ---------------------------------------------------------------------------
# CRM engine imports
# ---------------------------------------------------------------------------
from engine.nlu import get_nlu_classifier, initialize_nlu_classifier, RetailIntent, RetailCategory
from engine.flow_engine import process_turn
from engine.escalation import check_escalation
from engine.summary import generate_summary, initialize_summary_generator
from engine.order_lookup import fetch_order_options
from schemas.chat_request import ChatTurnRequest, SummaryRequest, ChatContext
from schemas.chat_response import ChatTurnResponse, SummaryResponse, NLUOutput, OptionItem


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_nlu_classifier()
    await initialize_summary_generator()
    logger.info("CRM engine modules ready")
    logger.info("API ready to accept requests")
    yield


app = FastAPI(title="RetailGPT Customer Support API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Test UI
# ---------------------------------------------------------------------------
@app.get("/test", include_in_schema=False)
async def test_ui():
    return FileResponse("static/test.html", media_type="text/html")


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------
@app.post("/intent", tags=["Existing"])
async def intent():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# CRM Chat routes
# ---------------------------------------------------------------------------
@app.post("/chat/turn", response_model=ChatTurnResponse, tags=["CRM Chat"])
async def chat_turn(request: ChatTurnRequest):
    ctx = request.context
    nlu_result = None

    if request.message_type == "text":
        classifier = get_nlu_classifier()
        nlu_result = await classifier.classify(message=request.message, known_category=ctx.category)

        if nlu_result.sentiment == "negative":
            ctx.negative_turns += 1
        if nlu_result.intent == RetailIntent.UNKNOWN:
            ctx.fallback_count += 1
        else:
            ctx.fallback_count = 0

        if nlu_result.order_id:
            ctx.order_id = nlu_result.order_id
        if nlu_result.category != RetailCategory.UNKNOWN:
            ctx.category = nlu_result.category.value

        intent = nlu_result.intent
    else:
        intent = None

    try:
        category = RetailCategory(ctx.category) if ctx.category else RetailCategory.UNKNOWN
    except ValueError:
        category = RetailCategory.UNKNOWN

    esc = check_escalation(
        intent=intent,
        category=category,
        negative_turns=ctx.negative_turns,
        fallback_count=ctx.fallback_count,
        open_handovers=[h.dict() for h in ctx.open_handovers],
        order_id=ctx.order_id,
        customer_id=ctx.customer_id,
    )

    if esc.should_escalate:
        summary = await generate_summary(
            transcript=[m.dict() for m in request.transcript],
            issue_type=intent.value if intent else ctx.current_flow,
            category=ctx.category,
            order_id=ctx.order_id,
        )
        nlu_out = NLUOutput(**nlu_result.to_dict()) if nlu_result else None
        return ChatTurnResponse(
            render_type="handover",
            message="Let me connect you to a support agent who can help you with this.",
            escalate=True,
            escalate_reason=esc.reason,
            ai_summary=summary,
            next_context=None,
            nlu=nlu_out
        )

    flow_result = process_turn(
        intent=intent,
        category=category,
        option_selected=request.option_id,
        current_flow=ctx.current_flow,
        current_step=ctx.flow_step,
    )

    if flow_result.escalate:
        summary = await generate_summary(
            transcript=[m.dict() for m in request.transcript],
            issue_type=flow_result.escalate_reason,
            category=ctx.category,
            order_id=ctx.order_id,
        )
        nlu_out = NLUOutput(**nlu_result.to_dict()) if nlu_result else None
        return ChatTurnResponse(
            render_type="handover",
            message="Let me connect you to a support agent who can help you with this.",
            escalate=True,
            escalate_reason=flow_result.escalate_reason,
            ai_summary=summary,
            next_context=None,
            nlu=nlu_out
        )

    # Capture order_id if the selected option came from an order-select step
    render = flow_result.render_instruction
    if render.get("capture_as_order_id") and request.option_id:
        ctx.order_id = request.option_id

    ctx.turn_count += 1
    ctx.current_flow = flow_result.next_flow
    ctx.flow_step = flow_result.next_step

    # If the next step needs orders from the API, fetch them now
    options = None
    if render.get("fetch_orders"):
        order_category = render.get("order_category", ctx.category or "")
        fetched_options, api_order_id = await fetch_order_options(
            customer_id=ctx.customer_id or "",
            category=order_category,
            base_url=ORDERS_API_BASE_URL,
        )
        if fetched_options:
            options = [OptionItem(**o) for o in fetched_options]
            if api_order_id and not ctx.order_id:
                ctx.order_id = api_order_id
        else:
            # Category not supported by orders API (e.g. Grocery) or no past orders —
            # auto-follow the wildcard transition to skip the order-select step.
            skip_result = process_turn(
                intent=None,
                category=category,
                option_selected="*",
                current_flow=ctx.current_flow,
                current_step=ctx.flow_step,
            )
            if not skip_result.escalate:
                ctx.current_flow = skip_result.next_flow
                ctx.flow_step = skip_result.next_step
                render = skip_result.render_instruction
                options = [OptionItem(**o) for o in render["options"]] if "options" in render else None
    elif "options" in render:
        options = [OptionItem(**o) for o in render["options"]]

    nlu_out = NLUOutput(**nlu_result.to_dict()) if nlu_result else None

    return ChatTurnResponse(
        render_type=render.get("render_type", "text"),
        message=render.get("message", ""),
        options=options,
        upload_config=render.get("upload_config"),
        terminal=render.get("terminal", False),
        ticket_raised=render.get("ticket_raised", False),
        issue_type=render.get("issue_type"),
        escalate=False,
        escalate_reason=None,
        ai_summary=None,
        next_context=ctx,
        nlu=nlu_out
    )


@app.post("/chat/summary", response_model=SummaryResponse, tags=["CRM Chat"])
async def chat_summary_endpoint(request: SummaryRequest):
    summary = await generate_summary(
        transcript=[m.dict() for m in request.transcript],
        issue_type=request.issue_type,
        category=request.category,
        order_id=request.order_id,
    )
    return SummaryResponse(summary=summary)
