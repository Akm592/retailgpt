from __future__ import annotations
import time
import uuid
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .assertions import evaluate
from .scoring import AssertionResult, TestResult, TurnResult

logger = logging.getLogger("eval.runner")


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: f"eval_{uuid.uuid4().hex[:12]}")
    customer_id: str = "eval_customer_001"
    context: dict = field(default_factory=dict)
    transcript: list = field(default_factory=list)
    last_response: dict = field(default_factory=dict)


async def execute_turn(
    session: Session,
    turn_input: dict,
    client: httpx.AsyncClient,
) -> Tuple[dict, float]:
    """
    Send one turn to /chat/turn.
    Updates session.context and session.transcript in place.
    Returns (response_dict, duration_ms).
    """
    msg_type = turn_input.get("message_type", "text")
    message = turn_input.get("message", "")
    option_id = turn_input.get("option_id")

    # Merge context overrides from the test case into session context
    ctx_overrides = turn_input.get("context", {})
    context = {**session.context, **ctx_overrides}

    payload = {
        "session_id": session.session_id,
        "customer_id": session.customer_id,
        "message": message,
        "message_type": msg_type,
        "option_id": option_id,
        "context": context,
        "transcript": session.transcript,
    }

    start = time.monotonic()
    try:
        resp = await client.post("/chat/turn", json=payload)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:300]}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Request error: {e}")

    duration_ms = (time.monotonic() - start) * 1000

    # Update transcript
    session.transcript.append({"role": "customer", "content": message})
    session.transcript.append({"role": "bot", "content": data.get("message", "")})

    # Update context from response (if not escalated / terminal)
    next_ctx = data.get("next_context")
    if next_ctx:
        session.context = next_ctx if isinstance(next_ctx, dict) else dict(next_ctx)

    session.last_response = data
    return data, duration_ms


async def run_single_turn_test(
    test_case: dict,
    client: httpx.AsyncClient,
) -> TestResult:
    """Run a single-turn test (NLU or button routing)."""
    session = Session()
    result = TestResult(
        test_id=test_case["id"],
        description=test_case.get("description", ""),
        category=test_case.get("category", ""),
        subcategory=test_case.get("subcategory", ""),
        status="PASS",
    )
    result._tags = test_case.get("tags", [])

    turn_input = test_case["input"]
    expect = test_case.get("expect", {})

    try:
        response, duration_ms = await execute_turn(session, turn_input, client)
        assertions = evaluate(response, expect)
        failed = [a for a in assertions if not a.passed]
        status = "PASS" if not failed else "FAIL"

        turn_result = TurnResult(
            turn_index=1,
            description=test_case.get("description", ""),
            status=status,
            assertions=assertions,
            request=_redact(turn_input),
            response=response,
            duration_ms=duration_ms,
        )
        result.turns.append(turn_result)
        result.status = status
        result.duration_ms = duration_ms

    except Exception as e:
        logger.exception(f"Error in test {test_case['id']}")
        turn_result = TurnResult(
            turn_index=1,
            description=test_case.get("description", ""),
            status="ERROR",
            error=str(e),
        )
        result.turns.append(turn_result)
        result.status = "ERROR"
        result.error = str(e)

    return result


async def run_multi_turn_test(
    test_case: dict,
    client: httpx.AsyncClient,
    with_orders_api: bool = False,
) -> TestResult:
    """Run a multi-turn flow test."""
    session = Session()
    # Pre-seed customer_id if test specifies it
    if test_case.get("customer_id"):
        session.customer_id = test_case["customer_id"]

    # Pre-seed context if test specifies starting state
    if test_case.get("initial_context"):
        session.context = test_case["initial_context"]

    result = TestResult(
        test_id=test_case["id"],
        description=test_case.get("description", ""),
        category=test_case.get("category", ""),
        subcategory=test_case.get("subcategory", ""),
        status="PASS",
    )
    result._tags = test_case.get("tags", [])

    turns = test_case.get("turns", [])
    total_ms = 0.0
    any_fail = False

    for turn_def in turns:
        turn_idx = turn_def.get("turn", 0)
        description = turn_def.get("description", f"Turn {turn_idx}")
        turn_input = turn_def.get("input", {})
        expect = turn_def.get("expect", {})

        # Conditional gate: skip turn if current step doesn't match
        required_step = turn_def.get("input_requires_step")
        if required_step:
            current_step = session.context.get("flow_step")
            if current_step != required_step:
                turn_result = TurnResult(
                    turn_index=turn_idx,
                    description=description,
                    status="SKIP",
                )
                result.turns.append(turn_result)
                continue

        # Resolve flow_step_oneof: if not with_orders_api, allow either path
        # (The assertion in expect handles this — runner doesn't need to do anything special)

        try:
            response, duration_ms = await execute_turn(session, turn_input, client)
            total_ms += duration_ms

            assertions = evaluate(response, expect)
            failed = [a for a in assertions if not a.passed]
            turn_status = "PASS" if not failed else "FAIL"

            if failed:
                any_fail = True

            turn_result = TurnResult(
                turn_index=turn_idx,
                description=description,
                status=turn_status,
                assertions=assertions,
                request=_redact(turn_input),
                response=response,
                duration_ms=duration_ms,
            )
            result.turns.append(turn_result)

            # Stop if escalated (terminal state)
            if response.get("escalate") or response.get("terminal"):
                break

        except Exception as e:
            logger.exception(f"Error in test {test_case['id']} turn {turn_idx}")
            turn_result = TurnResult(
                turn_index=turn_idx,
                description=description,
                status="ERROR",
                error=str(e),
            )
            result.turns.append(turn_result)
            any_fail = True
            break

    # Final assertions (checked against last response)
    final_expect = test_case.get("final_assertions", {})
    if final_expect and session.last_response:
        final_assertions = evaluate(session.last_response, final_expect)
        failed_final = [a for a in final_assertions if not a.passed]
        if failed_final:
            any_fail = True
        # Attach to a synthetic final turn
        if final_assertions:
            final_turn = TurnResult(
                turn_index=9999,
                description="final_assertions",
                status="PASS" if not failed_final else "FAIL",
                assertions=final_assertions,
                request={},
                response=session.last_response,
                duration_ms=0,
            )
            result.turns.append(final_turn)

    result.status = "FAIL" if any_fail else "PASS"
    result.duration_ms = total_ms
    return result


async def run_test(
    test_case: dict,
    client: httpx.AsyncClient,
    with_orders_api: bool = False,
) -> TestResult:
    """Dispatch to single-turn or multi-turn runner."""
    if "turns" in test_case:
        return await run_multi_turn_test(test_case, client, with_orders_api)
    else:
        return await run_single_turn_test(test_case, client)


def _redact(d: dict) -> dict:
    """Return a copy without secrets (nothing sensitive here, but keeps pattern)."""
    return dict(d)
