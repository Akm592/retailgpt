from __future__ import annotations
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from schemas.chat_request import ChatContext


class OptionItem(BaseModel):
    id: str
    label: str


class UploadConfig(BaseModel):
    required: bool = True
    min_photos: int = 3
    video: bool = True
    max_size_mb: int = 20


class NLUOutput(BaseModel):
    intent: str
    category: str
    confidence: float
    sentiment: str
    order_id: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    source: str


class ChatTurnResponse(BaseModel):
    render_type: str
    message: str = ""
    options: Optional[List[OptionItem]] = None
    upload_config: Optional[Any] = None
    terminal: bool = False
    escalate: bool = False
    escalate_reason: Optional[str] = None
    ai_summary: Optional[str] = None
    next_context: Optional[ChatContext] = None
    nlu: Optional[NLUOutput] = None


class SummaryResponse(BaseModel):
    summary: str
