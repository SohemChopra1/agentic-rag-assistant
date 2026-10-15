"""
Agent endpoints. Both run the same loop (app.agent.loop.agent_events):

  POST /ask         -> one JSON response with the final answer + tool trace
  POST /ask/stream  -> Server-Sent Events, one per agent step, as they happen

Both require ANTHROPIC_API_KEY and VOYAGE_API_KEY and return a clean 503
(not an unhandled 500) when either is missing.

/ask/stream error handling has two phases, because an SSE response commits
its 200 status as soon as the first byte is sent:
  - before streaming: missing keys raise in agent_events() -> real 503
  - during streaming: an Anthropic API error (or anything else) can no
    longer change the status, so it is sent as a final `error` event and
    the stream ends cleanly instead of being cut off mid-response
"""
import json
import logging
from collections.abc import Iterator

from anthropic import AnthropicError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.agent.loop import agent_events, run_agent
from app.db import SessionLocal, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class AskRequest(BaseModel):
    query: str


class ToolCall(BaseModel):
    tool: str
    input: dict


class AskResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCall]


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, db: Session = Depends(get_db)):
    try:
        result = run_agent(db, req.query)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except AnthropicError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return AskResponse(answer=result.answer, tool_calls=result.tool_calls)


@router.post("/ask/stream")
def ask_stream(req: AskRequest):
    # The stream owns its DB session instead of using Depends(get_db): the
    # loop keeps querying for as long as the response is streaming, so the
    # session must live exactly as long as the generator — opened here,
    # closed in _sse_events' finally — not as long as the request handler.
    db = SessionLocal()
    try:
        events = agent_events(db, req.query)
    except RuntimeError as e:
        db.close()
        raise HTTPException(status_code=503, detail=str(e)) from e

    return EventSourceResponse(_sse_events(events, db))


def _sse_events(events: Iterator[dict], db: Session) -> Iterator[dict]:
    try:
        for event in events:
            yield {"event": event["type"], "data": json.dumps(event)}
    except AnthropicError as e:
        yield _error_event(f"Model API error: {e}")
    except Exception as e:  # noqa: BLE001 — the client must get a terminal event, not a dropped connection
        logger.exception("Agent stream failed")
        yield _error_event(f"Unexpected error: {type(e).__name__}")
    finally:
        db.close()


def _error_event(message: str) -> dict:
    return {"event": "error", "data": json.dumps({"type": "error", "message": message})}
