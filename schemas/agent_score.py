from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class RubricScore(BaseModel):
    rubric: str = Field(..., description="Snake-case rubric key")
    label: str = Field(..., description="Human-readable rubric name")
    score: float = Field(..., description="Score from 1.0 (very poor) to 10.0 (excellent)")
    justification: str = Field(..., description="AI-generated 1-2 sentence explanation")
    weight: float = Field(..., description="Rubric weight in overall score calculation (0.0-1.0)")


# ---------------------------------------------------------------------------
# POST /analytics/evaluate-human-handover
# ---------------------------------------------------------------------------

class EvaluateHumanHandoverRequest(BaseModel):
    handover_id: str = Field(..., description="Handover ID to score")

    class Config:
        json_schema_extra = {
            "example": {
                "handover_id": "hov_xyz789",
            }
        }


class EvaluateHumanHandoverResponse(BaseModel):
    handover_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    overall_score: float = Field(..., description="Weighted average of all 7 rubric scores (1.0-10.0)")
    rubric_scores: List[RubricScore]
    summary: str = Field(..., description="AI-generated 2-3 sentence performance summary")
    recommendations: List[str] = Field(..., description="2-4 specific, actionable improvement items")
    survey_available: bool = Field(..., description="Whether customer survey data was available for scoring")
    ticket_available: bool = Field(..., description="Whether ticket data was available for scoring")
    scored_at: str = Field(..., description="ISO 8601 UTC timestamp of when scoring ran")


# ---------------------------------------------------------------------------
# POST /analytics/evaluate-human-agent  (overall / aggregate)
# ---------------------------------------------------------------------------

class EvaluateHumanAgentRequest(BaseModel):
    agent_id: str = Field(..., description="Agent user ID to evaluate")
    start_date: Optional[str] = Field(None, description="Filter handovers from this date inclusive (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Filter handovers until this date inclusive (YYYY-MM-DD)")
    sample_limit: int = Field(5, ge=1, le=10, description="Number of transcript samples to send to AI (1-10)")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_uuid_123",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "sample_limit": 5,
            }
        }


class ResolutionStats(BaseModel):
    total: int = Field(..., description="Total handovers assigned to this agent in the period")
    resolved: int
    expired: int
    pending: int
    accepted: int
    resolution_rate: float = Field(..., description="resolved / (resolved + expired); 0.0 if no completed handovers")


class SurveyStats(BaseModel):
    total_responses: int
    avg_overall_satisfaction: Optional[float] = Field(None, description="Average CSAT score (1-5)")
    avg_nps: Optional[float] = Field(None, description="Average NPS (0-10)")
    response_time_distribution: dict = Field(..., description='{"fast": N, "average": N, "slow": N}')
    helpfulness_distribution: dict = Field(..., description='{"very_helpful": N, "somewhat_helpful": N, "not_helpful": N}')


class TimingStats(BaseModel):
    avg_resolution_hours: Optional[float] = Field(None, description="Mean hours from handover created_at to resolved_at")
    min_resolution_hours: Optional[float] = None
    max_resolution_hours: Optional[float] = None


class EvaluateHumanAgentResponse(BaseModel):
    agent_id: str
    agent_name: Optional[str] = None
    period: dict = Field(..., description='{"start": "...", "end": "...", "handovers_analyzed": N}')
    resolution_stats: ResolutionStats
    survey_stats: SurveyStats
    timing_stats: TimingStats
    overall_score: float = Field(..., description="AI-computed weighted rubric average (1.0-10.0)")
    rubric_scores: List[RubricScore]
    summary: str = Field(..., description="AI-generated 3-4 sentence overall performance narrative")
    strengths: List[str] = Field(..., description="2-3 things the agent consistently does well")
    improvement_areas: List[str] = Field(..., description="2-3 areas where performance is consistently below expectations")
    recommendations: List[str] = Field(..., description="2-4 concrete coaching actions")
    survey_available: bool
    scored_at: str = Field(..., description="ISO 8601 UTC timestamp of when scoring ran")
