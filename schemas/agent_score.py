from __future__ import annotations
from typing import Optional, List, Dict, Any
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


# ---------------------------------------------------------------------------
# GET /analytics/agent-self  (agent's own view — same shape as evaluate-human-agent)
# Reuses EvaluateHumanAgentRequest / EvaluateHumanAgentResponse
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /analytics/team-performance
# ---------------------------------------------------------------------------

class AgentSummary(BaseModel):
    """Lightweight per-agent card used inside team and org views (no Gemini narrative)."""
    agent_id: str
    agent_name: Optional[str] = None
    resolution_stats: ResolutionStats
    survey_stats: SurveyStats
    timing_stats: TimingStats
    overall_score: Optional[float] = Field(None, description="Latest cached score from agent_scores table (null if never scored)")


class TeamPerformanceResponse(BaseModel):
    support_group: str
    period: Dict[str, Any]
    agents: List[AgentSummary] = Field(..., description="Agents sorted by overall_score descending")
    group_stats: Dict[str, Any] = Field(..., description="Aggregated stats across all agents in the group")


# ---------------------------------------------------------------------------
# GET /analytics/org-performance
# ---------------------------------------------------------------------------

class GroupSummary(BaseModel):
    support_group: str
    agent_count: int
    avg_score: Optional[float] = None
    resolution_stats: ResolutionStats
    survey_stats: SurveyStats


class OrgPerformanceResponse(BaseModel):
    period: Dict[str, Any]
    groups: List[GroupSummary]
    org_stats: Dict[str, Any] = Field(..., description="Aggregated stats across the entire organisation")


# ---------------------------------------------------------------------------
# GET /analytics/funnel
# ---------------------------------------------------------------------------

class FunnelResponse(BaseModel):
    period: Dict[str, Any]
    total_sessions: int
    resolved_by_ai: int
    resolved_by_ai_pct: float
    escalated: int
    escalated_pct: float
    abandoned: int
    abandoned_pct: float
    open: int
    avg_ai_rating: Optional[float] = None
    total_ai_ratings: int
    escalation_reasons: Dict[str, int] = Field(..., description="Breakdown of escalation_reason values and their counts")


# ---------------------------------------------------------------------------
# GET /analytics/ai-performance
# ---------------------------------------------------------------------------

class AIPerformanceResponse(BaseModel):
    period: Dict[str, Any]
    total_sessions: int
    total_ai_resolved: int
    total_escalated: int
    containment_rate: float = Field(..., description="resolved_by_ai / (resolved_by_ai + escalated)")
    avg_ai_rating: Optional[float] = None
    total_ai_ratings: int
    avg_turns_before_resolution: Optional[float] = None
    avg_turns_before_escalation: Optional[float] = None
    bot_failure_rate: float = Field(..., description="Fraction of sessions with at least one NLU fallback")
    escalation_reasons: Dict[str, int]


# ---------------------------------------------------------------------------
# POST /analytics/score-and-cache
# ---------------------------------------------------------------------------

class ScoreAndCacheRequest(BaseModel):
    handover_id: str = Field(..., description="Handover to score and persist to agent_scores table")

    class Config:
        json_schema_extra = {"example": {"handover_id": "hov_xyz789"}}


class ScoreAndCacheResponse(BaseModel):
    handover_id: str
    agent_id: Optional[str] = None
    overall_score: float
    cached: bool = Field(..., description="True if the score was successfully written to agent_scores table")
    scored_at: str
