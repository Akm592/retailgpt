from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field


class OpenHandover(BaseModel):
    id: str
    order_id: Optional[str] = None
    issue_type: Optional[str] = None
    status: str = "pending_assignment"


class ChatContext(BaseModel):
    current_flow: Optional[str] = None
    flow_step: Optional[str] = None
    category: Optional[str] = None
    order_id: Optional[str] = None
    turn_count: int = 0
    negative_turns: int = 0
    fallback_count: int = 0
    open_handovers: List[OpenHandover] = Field(default_factory=list)


class TranscriptMessage(BaseModel):
    role: str
    content: str


class ChatTurnRequest(BaseModel):
    session_id: str = Field(..., description="Session ID created by frontend")
    customer_id: Optional[str] = Field(None, description="Customer ID — sent once per turn at top level")
    message: str = Field(..., min_length=1, max_length=2000)
    message_type: str = Field(default="text")
    option_id: Optional[str] = None
    context: ChatContext = Field(default_factory=ChatContext)
    transcript: List[TranscriptMessage] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_abc123",
                "customer_id": "cust_xyz",
                "message": "mera dal thanda tha",
                "message_type": "text",
                "option_id": None,
                "context": {
                    "current_flow": None,
                    "flow_step": None,
                    "category": None,
                    "order_id": None,
                    "turn_count": 1,
                    "negative_turns": 0,
                    "fallback_count": 0,
                    "open_handovers": []
                },
                "transcript": [
                    {"role": "customer", "content": "mera dal thanda tha"}
                ]
            }
        }


class SummaryRequest(BaseModel):
    session_id: str
    transcript: List[TranscriptMessage]
    issue_type: Optional[str] = None
    category: Optional[str] = None
    order_id: Optional[str] = None
