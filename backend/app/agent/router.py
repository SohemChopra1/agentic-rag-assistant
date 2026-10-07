"""
/ask endpoint: runs the ReAct agent loop against a user query and returns
the final answer plus a trace of which tools were called. Requires both
ANTHROPIC_API_KEY and VOYAGE_API_KEY — raises a clean 503 rather than an
unhandled 500 when either is missing or the Anthropic API itself errors.
"""
from anthropic import AnthropicError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.loop import run_agent
from app.db import get_db

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
