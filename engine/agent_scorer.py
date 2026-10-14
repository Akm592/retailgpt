from __future__ import annotations
import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv
from supabase import AsyncClient, acreate_client

load_dotenv()
logger = logging.getLogger("human_agent_scorer")

# ---------------------------------------------------------------------------
# Shared Supabase client (module-level singleton used by scorer + app writes)
# ---------------------------------------------------------------------------

_shared_db: Optional[AsyncClient] = None


async def get_db() -> AsyncClient:
    global _shared_db
    if _shared_db is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        _shared_db = await acreate_client(url, key)
    return _shared_db

RUBRIC_WEIGHTS = {
    "resolution_quality":              0.20,
    "customer_satisfaction_alignment": 0.20,
    "empathy_and_tone":                0.15,
    "response_time":                   0.15,
    "communication_clarity":           0.10,
    "problem_understanding":           0.10,
    "process_adherence":               0.10,
}

RUBRIC_LABELS = {
    "resolution_quality":              "Resolution Quality",
    "customer_satisfaction_alignment": "Customer Satisfaction Alignment",
    "empathy_and_tone":                "Empathy & Tone",
    "response_time":                   "Response Time",
    "communication_clarity":           "Communication Clarity",
    "problem_understanding":           "Problem Understanding",
    "process_adherence":               "Process Adherence",
}


def _load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "prompts", filename)
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Prompt file not found: {path}")


def _weighted_overall(rubric_scores: dict) -> float:
    total = 0.0
    for key, weight in RUBRIC_WEIGHTS.items():
        score = rubric_scores.get(key, {}).get("score", 5.0)
        total += float(score) * weight
    return round(total, 2)


def _build_rubric_list(rubric_scores: dict) -> list:
    return [
        {
            "rubric":        key,
            "label":         RUBRIC_LABELS[key],
            "score":         rubric_scores.get(key, {}).get("score", 5.0),
            "justification": rubric_scores.get(key, {}).get("justification", ""),
            "weight":        RUBRIC_WEIGHTS[key],
        }
        for key in RUBRIC_WEIGHTS
    ]


def _format_messages(messages: list) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "unknown").upper()
        ts = (m.get("created_at") or "")[:16]
        content = m.get("content", "")
        if content:
            lines.append(f"{role} [{ts}]: {content}" if ts else f"{role}: {content}")
    return "\n".join(lines)


async def _fetch_agent_name(db: AsyncClient, agent_id: Optional[str]) -> str | None:
    if not agent_id:
        return None
    result = await db.table("users").select("name").eq("id", agent_id).execute()
    if result.data:
        return result.data[0].get("name")
    return None


class AgentScorer:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)

        self.score_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=_load_prompt("agent_score_system.txt"),
            generation_config={
                "temperature": 0.2,
                "top_p": 0.95,
                "max_output_tokens": 1500,
                "response_mime_type": "application/json",
            },
        )
        self.perf_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=_load_prompt("agent_performance_system.txt"),
            generation_config={
                "temperature": 0.2,
                "top_p": 0.95,
                "max_output_tokens": 2000,
                "response_mime_type": "application/json",
            },
        )

        self._db: Optional[AsyncClient] = None
        logger.info("Human AgentScorer initialised")

    async def _get_db(self) -> AsyncClient:
        return await get_db()

    # ------------------------------------------------------------------
    # Per-handover scoring
    # ------------------------------------------------------------------

    async def score(self, handover_id: str) -> dict:
        db = await self._get_db()

        # Q1: fetch handover
        q1 = await db.table("handovers").select("*").eq("id", handover_id).execute()
        if not q1.data:
            raise LookupError(f"handover_not_found:{handover_id}")
        handover = q1.data[0]

        session_id = handover.get("session_id")
        agent_id = handover.get("agent_id")

        # Q2-Q5 concurrently
        q2_coro = db.table("messages").select("role,content,created_at").eq("session_id", session_id).order("created_at").execute()
        q3_coro = db.table("support_surveys").select("*").eq("handover_id", handover_id).execute()
        q4_coro = db.table("tickets").select("issue_type,status,ticket_source").eq("session_id", session_id).execute()

        q2, q3, q4, agent_name = await asyncio.gather(
            q2_coro,
            q3_coro,
            q4_coro,
            _fetch_agent_name(db, agent_id),
        )

        messages = q2.data or []
        survey = q3.data[0] if q3.data else None
        ticket = q4.data[0] if q4.data else None

        prompt = self._build_score_prompt(handover, messages, survey, ticket)

        try:
            response = await self.score_model.generate_content_async(prompt)
            parsed = json.loads(response.text.strip())
        except Exception as e:
            logger.error(f"Gemini scoring error: {e}")
            raise

        rubric_scores = parsed.get("rubric_scores", {})
        overall = _weighted_overall(rubric_scores)

        return {
            "handover_id":     handover_id,
            "agent_id":        agent_id,
            "agent_name":      agent_name,
            "overall_score":   overall,
            "rubric_scores":   _build_rubric_list(rubric_scores),
            "summary":         parsed.get("summary", ""),
            "recommendations": parsed.get("recommendations", []),
            "survey_available": survey is not None,
            "ticket_available": ticket is not None,
            "scored_at":       datetime.now(timezone.utc).isoformat(),
        }

    def _build_score_prompt(self, handover: dict, messages: list, survey: dict | None, ticket: dict | None) -> str:
        transcript = _format_messages(messages) or handover.get("transcript") or "No transcript available."

        if survey:
            survey_block = (
                f"Overall satisfaction: {survey.get('overall_satisfaction')}/5\n"
                f"Response time rating: {survey.get('response_time')}\n"
                f"Helpfulness: {survey.get('helpfulness')}\n"
                f"NPS: {survey.get('nps')}/10\n"
                f"Optional feedback: {survey.get('optional_feedback') or 'none'}"
            )
        else:
            survey_block = "No survey data available."

        if ticket:
            ticket_block = (
                f"Issue type: {ticket.get('issue_type')}\n"
                f"Ticket status: {ticket.get('status')}\n"
                f"Ticket source: {ticket.get('ticket_source')}"
            )
        else:
            ticket_block = "No ticket data available."

        return (
            f"HANDOVER STATUS: {handover.get('status', 'unknown')}\n"
            f"SUPPORT GROUP: {handover.get('support_group', 'unknown')}\n"
            f"CREATED AT: {handover.get('created_at', '')}\n"
            f"RESOLVED AT: {handover.get('resolved_at', '') or 'not resolved'}\n\n"
            f"--- CUSTOMER SURVEY ---\n{survey_block}\n\n"
            f"--- TICKET INFO ---\n{ticket_block}\n\n"
            f"--- CONVERSATION TRANSCRIPT ---\n{transcript}"
        )

    # ------------------------------------------------------------------
    # Aggregate agent performance
    # ------------------------------------------------------------------

    async def performance(
        self,
        agent_id: str,
        start_date: str | None,
        end_date: str | None,
        sample_limit: int,
    ) -> dict:
        db = await self._get_db()

        # Validate agent exists
        agent_q = await db.table("users").select("name,support_group").eq("id", agent_id).execute()
        if not agent_q.data:
            raise LookupError(f"agent_not_found:{agent_id}")
        agent_name = agent_q.data[0].get("name")
        support_group = agent_q.data[0].get("support_group")

        # Fetch handovers with optional date filters
        query = db.table("handovers").select("id,session_id,status,created_at,resolved_at").eq("agent_id", agent_id)
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59Z")
        handovers_q = await query.order("created_at", desc=True).execute()
        handovers = handovers_q.data or []

        # Compute resolution stats
        resolution_stats = self._compute_resolution_stats(handovers)

        # Compute timing stats (only for resolved handovers)
        timing_stats = self._compute_timing_stats(handovers)

        if not handovers:
            # Return zero-data report without AI call
            return self._empty_performance_report(
                agent_id, agent_name, start_date, end_date,
                resolution_stats, timing_stats,
            )

        handover_ids = [h["id"] for h in handovers]
        session_ids = [h["session_id"] for h in handovers if h.get("session_id")]

        # Fetch surveys and tickets concurrently
        surveys_q, tickets_q = await asyncio.gather(
            db.table("support_surveys").select("*").in_("handover_id", handover_ids).execute(),
            db.table("tickets").select("issue_type,status,session_id").in_("session_id", session_ids).execute(),
        )
        surveys = surveys_q.data or []
        survey_stats = self._compute_survey_stats(surveys)

        # Select sample handovers for transcript (prefer resolved + surveyed)
        surveyed_ids = {s["handover_id"] for s in surveys}
        resolved_handovers = [h for h in handovers if h["status"] == "resolved"]
        sample_pool = sorted(
            resolved_handovers,
            key=lambda h: (h["id"] in surveyed_ids),
            reverse=True,
        )[:sample_limit]
        if len(sample_pool) < sample_limit:
            remaining = [h for h in handovers if h not in sample_pool]
            sample_pool.extend(remaining[:sample_limit - len(sample_pool)])

        # Fetch messages for sampled handovers concurrently
        sample_session_ids = [h["session_id"] for h in sample_pool if h.get("session_id")]
        msg_results = await asyncio.gather(*[
            db.table("messages").select("role,content,created_at").eq("session_id", sid).order("created_at").execute()
            for sid in sample_session_ids
        ])

        # Build sample transcripts keyed by handover id
        sample_transcripts = []
        for i, h in enumerate(sample_pool):
            if i < len(msg_results) and msg_results[i].data:
                transcript_text = _format_messages(msg_results[i].data)
            else:
                transcript_text = "No transcript available."
            sample_transcripts.append({
                "handover_id": h["id"],
                "status": h["status"],
                "transcript": transcript_text,
            })

        prompt = self._build_performance_prompt(
            agent_name, support_group,
            resolution_stats, timing_stats, survey_stats,
            sample_transcripts,
        )

        try:
            response = await self.perf_model.generate_content_async(prompt)
            parsed = json.loads(response.text.strip())
        except Exception as e:
            logger.error(f"Gemini performance error: {e}")
            raise

        rubric_scores = parsed.get("rubric_scores", {})
        overall = _weighted_overall(rubric_scores)

        return {
            "agent_id":         agent_id,
            "agent_name":       agent_name,
            "period": {
                "start":               start_date or "all time",
                "end":                 end_date or "all time",
                "handovers_analyzed":  len(handovers),
            },
            "resolution_stats":  resolution_stats,
            "survey_stats":      survey_stats,
            "timing_stats":      timing_stats,
            "overall_score":     overall,
            "rubric_scores":     _build_rubric_list(rubric_scores),
            "summary":           parsed.get("summary", ""),
            "strengths":         parsed.get("strengths", []),
            "improvement_areas": parsed.get("improvement_areas", []),
            "recommendations":   parsed.get("recommendations", []),
            "survey_available":  len(surveys) > 0,
            "scored_at":         datetime.now(timezone.utc).isoformat(),
        }

    def _compute_resolution_stats(self, handovers: list) -> dict:
        counts = {"resolved": 0, "expired": 0, "pending": 0, "accepted": 0}
        for h in handovers:
            status = h.get("status", "")
            if status in counts:
                counts[status] += 1
        denom = counts["resolved"] + counts["expired"]
        resolution_rate = round(counts["resolved"] / denom, 4) if denom > 0 else 0.0
        return {
            "total":           len(handovers),
            "resolved":        counts["resolved"],
            "expired":         counts["expired"],
            "pending":         counts["pending"],
            "accepted":        counts["accepted"],
            "resolution_rate": resolution_rate,
        }

    def _compute_timing_stats(self, handovers: list) -> dict:
        durations = []
        for h in handovers:
            if h.get("status") == "resolved" and h.get("created_at") and h.get("resolved_at"):
                try:
                    created = datetime.fromisoformat(h["created_at"].replace("Z", "+00:00"))
                    resolved = datetime.fromisoformat(h["resolved_at"].replace("Z", "+00:00"))
                    hours = (resolved - created).total_seconds() / 3600
                    if hours >= 0:
                        durations.append(hours)
                except Exception:
                    pass
        if not durations:
            return {"avg_resolution_hours": None, "min_resolution_hours": None, "max_resolution_hours": None}
        return {
            "avg_resolution_hours": round(sum(durations) / len(durations), 2),
            "min_resolution_hours": round(min(durations), 2),
            "max_resolution_hours": round(max(durations), 2),
        }

    def _compute_survey_stats(self, surveys: list) -> dict:
        if not surveys:
            return {
                "total_responses": 0,
                "avg_overall_satisfaction": None,
                "avg_nps": None,
                "response_time_distribution": {"fast": 0, "average": 0, "slow": 0},
                "helpfulness_distribution": {"very_helpful": 0, "somewhat_helpful": 0, "not_helpful": 0},
            }

        sat_scores = [s["overall_satisfaction"] for s in surveys if s.get("overall_satisfaction") is not None]
        nps_scores = [s["nps"] for s in surveys if s.get("nps") is not None]

        rt_dist = {"fast": 0, "average": 0, "slow": 0}
        for s in surveys:
            rt = s.get("response_time")
            if rt in rt_dist:
                rt_dist[rt] += 1

        help_dist = {"very_helpful": 0, "somewhat_helpful": 0, "not_helpful": 0}
        for s in surveys:
            h = s.get("helpfulness")
            if h in help_dist:
                help_dist[h] += 1

        return {
            "total_responses":          len(surveys),
            "avg_overall_satisfaction": round(sum(sat_scores) / len(sat_scores), 2) if sat_scores else None,
            "avg_nps":                  round(sum(nps_scores) / len(nps_scores), 2) if nps_scores else None,
            "response_time_distribution": rt_dist,
            "helpfulness_distribution":   help_dist,
        }

    def _build_performance_prompt(
        self,
        agent_name: str | None,
        support_group: str | None,
        resolution_stats: dict,
        timing_stats: dict,
        survey_stats: dict,
        sample_transcripts: list,
    ) -> str:
        lines = [
            f"AGENT NAME: {agent_name or 'Unknown'}",
            f"SUPPORT GROUP: {support_group or 'Unknown'}",
            "",
            "--- RESOLUTION STATISTICS ---",
            f"Total handovers: {resolution_stats['total']}",
            f"Resolved: {resolution_stats['resolved']}",
            f"Expired: {resolution_stats['expired']}",
            f"Pending: {resolution_stats['pending']}",
            f"Accepted: {resolution_stats['accepted']}",
            f"Resolution rate: {resolution_stats['resolution_rate']:.1%}",
            "",
            "--- TIMING STATISTICS ---",
            f"Avg resolution time: {timing_stats['avg_resolution_hours']} hours" if timing_stats['avg_resolution_hours'] is not None else "Avg resolution time: N/A",
            f"Min resolution time: {timing_stats['min_resolution_hours']} hours" if timing_stats['min_resolution_hours'] is not None else "Min resolution time: N/A",
            f"Max resolution time: {timing_stats['max_resolution_hours']} hours" if timing_stats['max_resolution_hours'] is not None else "Max resolution time: N/A",
            "",
            "--- SURVEY STATISTICS ---",
            f"Total survey responses: {survey_stats['total_responses']}",
            f"Avg customer satisfaction (1-5): {survey_stats['avg_overall_satisfaction']}",
            f"Avg NPS (0-10): {survey_stats['avg_nps']}",
            f"Response time distribution: {survey_stats['response_time_distribution']}",
            f"Helpfulness distribution: {survey_stats['helpfulness_distribution']}",
        ]

        if sample_transcripts:
            lines.append("")
            lines.append(f"--- SAMPLE TRANSCRIPTS ({len(sample_transcripts)} interactions) ---")
            for i, t in enumerate(sample_transcripts, 1):
                lines.append(f"\n[Sample {i} | Handover: {t['handover_id']} | Status: {t['status']}]")
                lines.append(t["transcript"])

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Team performance (manager view — stats only, no Gemini per agent)
    # ------------------------------------------------------------------

    async def team_performance(
        self,
        support_group: str,
        start_date: str | None,
        end_date: str | None,
    ) -> dict:
        db = await self._get_db()

        # Q1: all agents in the group
        agents_q = await db.table("users").select("id,name,support_group").eq("support_group", support_group).execute()
        agents = agents_q.data or []
        if not agents:
            raise LookupError(f"support_group_not_found:{support_group}")

        agent_ids = [a["id"] for a in agents]

        # Q2: all handovers for all agents in one query
        query = db.table("handovers").select("id,session_id,status,created_at,resolved_at,agent_id").in_("agent_id", agent_ids)
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59Z")
        handovers_q = await query.execute()
        all_handovers = handovers_q.data or []

        # Group handovers by agent_id
        handovers_by_agent: dict = defaultdict(list)
        for h in all_handovers:
            handovers_by_agent[h["agent_id"]].append(h)

        # Q3 + Q4 concurrently: surveys and latest cached scores
        all_handover_ids = [h["id"] for h in all_handovers]
        if all_handover_ids:
            surveys_q, cached_q = await asyncio.gather(
                db.table("support_surveys").select("*").in_("handover_id", all_handover_ids).execute(),
                db.table("agent_scores").select("agent_id,overall_score,evaluated_at").in_("agent_id", agent_ids).order("evaluated_at", desc=True).execute(),
            )
            all_surveys = surveys_q.data or []
            cached_scores = cached_q.data or []
        else:
            all_surveys, cached_scores = [], []

        # Map surveys by agent via handover
        handover_to_agent = {h["id"]: h["agent_id"] for h in all_handovers}
        surveys_by_agent: dict = defaultdict(list)
        for s in all_surveys:
            aid = handover_to_agent.get(s["handover_id"])
            if aid:
                surveys_by_agent[aid].append(s)

        # Latest cached score per agent (already sorted desc by evaluated_at)
        latest_score_by_agent: dict = {}
        for c in cached_scores:
            aid = c["agent_id"]
            if aid not in latest_score_by_agent:
                latest_score_by_agent[aid] = c["overall_score"]

        # Build per-agent summaries
        agent_summaries = []
        for agent in agents:
            aid = agent["id"]
            agent_summaries.append({
                "agent_id": aid,
                "agent_name": agent.get("name"),
                "resolution_stats": self._compute_resolution_stats(handovers_by_agent[aid]),
                "survey_stats": self._compute_survey_stats(surveys_by_agent[aid]),
                "timing_stats": self._compute_timing_stats(handovers_by_agent[aid]),
                "overall_score": latest_score_by_agent.get(aid),
            })

        agent_summaries.sort(
            key=lambda a: (a["overall_score"] is not None, a["overall_score"] or 0.0),
            reverse=True,
        )

        # Group-level aggregates
        total_handovers_count = sum(a["resolution_stats"]["total"] for a in agent_summaries)
        total_resolved = sum(a["resolution_stats"]["resolved"] for a in agent_summaries)
        all_scores = [a["overall_score"] for a in agent_summaries if a["overall_score"] is not None]

        sat_vals, nps_vals = [], []
        for a in agent_summaries:
            ss = a["survey_stats"]
            n = ss["total_responses"]
            if ss["avg_overall_satisfaction"] is not None:
                sat_vals.extend([ss["avg_overall_satisfaction"]] * n)
            if ss["avg_nps"] is not None:
                nps_vals.extend([ss["avg_nps"]] * n)

        return {
            "support_group": support_group,
            "period": {"start": start_date or "all time", "end": end_date or "all time"},
            "agents": agent_summaries,
            "group_stats": {
                "total_agents": len(agents),
                "total_handovers": total_handovers_count,
                "total_resolved": total_resolved,
                "group_resolution_rate": round(total_resolved / total_handovers_count, 4) if total_handovers_count > 0 else 0.0,
                "avg_score": round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
                "total_survey_responses": sum(a["survey_stats"]["total_responses"] for a in agent_summaries),
                "avg_overall_satisfaction": round(sum(sat_vals) / len(sat_vals), 2) if sat_vals else None,
                "avg_nps": round(sum(nps_vals) / len(nps_vals), 2) if nps_vals else None,
            },
        }

    # ------------------------------------------------------------------
    # Org performance (admin view — cross-group, stats only)
    # ------------------------------------------------------------------

    async def org_performance(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> dict:
        db = await self._get_db()

        # Q1: all agents (filter out non-agent users without support_group)
        agents_q = await db.table("users").select("id,name,support_group").not_.is_("support_group", "null").execute()
        agents = agents_q.data or []
        support_groups = list({a["support_group"] for a in agents if a.get("support_group")})

        # Q2: all handovers across all groups
        query = db.table("handovers").select("id,status,created_at,resolved_at,agent_id,support_group")
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59Z")
        handovers_q = await query.execute()
        all_handovers = handovers_q.data or []

        # Group handovers by support_group (use handover.support_group directly)
        handovers_by_group: dict = defaultdict(list)
        for h in all_handovers:
            grp = h.get("support_group") or "unknown"
            handovers_by_group[grp].append(h)

        # Q3 + Q4 concurrently: surveys and cached scores
        all_handover_ids = [h["id"] for h in all_handovers]
        agent_ids = [a["id"] for a in agents]
        if all_handover_ids:
            surveys_q = await db.table("support_surveys").select("handover_id,overall_satisfaction,nps,response_time,helpfulness").in_("handover_id", all_handover_ids).execute()
            all_surveys = surveys_q.data or []
        else:
            all_surveys = []

        if agent_ids:
            cached_q = await db.table("agent_scores").select("agent_id,overall_score").in_("agent_id", agent_ids).execute()
            cached_scores = cached_q.data or []
        else:
            cached_scores = []

        handover_to_group = {h["id"]: (h.get("support_group") or "unknown") for h in all_handovers}
        surveys_by_group: dict = defaultdict(list)
        for s in all_surveys:
            grp = handover_to_group.get(s["handover_id"], "unknown")
            surveys_by_group[grp].append(s)

        agent_to_group = {a["id"]: (a.get("support_group") or "unknown") for a in agents}
        scores_by_group: dict = defaultdict(list)
        for c in cached_scores:
            grp = agent_to_group.get(c["agent_id"], "unknown")
            if c.get("overall_score") is not None:
                scores_by_group[grp].append(c["overall_score"])

        # Build group summaries
        group_summaries = []
        for grp in support_groups:
            grp_handovers = handovers_by_group[grp]
            grp_surveys = surveys_by_group[grp]
            grp_scores = scores_by_group[grp]
            grp_agent_count = len([a for a in agents if a.get("support_group") == grp])

            res_stats = self._compute_resolution_stats(grp_handovers)
            surv_stats = self._compute_survey_stats(grp_surveys)

            group_summaries.append({
                "support_group": grp,
                "agent_count": grp_agent_count,
                "avg_score": round(sum(grp_scores) / len(grp_scores), 2) if grp_scores else None,
                "resolution_stats": res_stats,
                "survey_stats": surv_stats,
            })

        # Org-wide aggregates
        total_handovers_count = sum(g["resolution_stats"]["total"] for g in group_summaries)
        total_resolved = sum(g["resolution_stats"]["resolved"] for g in group_summaries)
        all_scores = [g["avg_score"] for g in group_summaries if g["avg_score"] is not None]

        sat_vals, nps_vals = [], []
        for g in group_summaries:
            ss = g["survey_stats"]
            n = ss["total_responses"]
            if ss["avg_overall_satisfaction"] is not None:
                sat_vals.extend([ss["avg_overall_satisfaction"]] * n)
            if ss["avg_nps"] is not None:
                nps_vals.extend([ss["avg_nps"]] * n)

        return {
            "period": {"start": start_date or "all time", "end": end_date or "all time"},
            "groups": group_summaries,
            "org_stats": {
                "total_groups": len(support_groups),
                "total_agents": len(agents),
                "total_handovers": total_handovers_count,
                "total_resolved": total_resolved,
                "org_resolution_rate": round(total_resolved / total_handovers_count, 4) if total_handovers_count > 0 else 0.0,
                "avg_score": round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
                "total_survey_responses": sum(g["survey_stats"]["total_responses"] for g in group_summaries),
                "avg_overall_satisfaction": round(sum(sat_vals) / len(sat_vals), 2) if sat_vals else None,
                "avg_nps": round(sum(nps_vals) / len(nps_vals), 2) if nps_vals else None,
            },
        }

    # ------------------------------------------------------------------
    # Funnel breakdown (AI resolved vs escalated vs abandoned)
    # ------------------------------------------------------------------

    async def funnel(
        self,
        start_date: str | None,
        end_date: str | None,
        support_group: str | None = None,
    ) -> dict:
        db = await self._get_db()

        # Fetch sessions with outcome columns
        query = db.table("sessions").select("id,outcome,escalation_reason,ai_turns,fallback_count,created_at")
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59Z")
        sessions_q = await query.execute()
        sessions = sessions_q.data or []

        # Optional: narrow to sessions that escalated into a specific support_group
        if support_group:
            handovers_q = await db.table("handovers").select("session_id").eq("support_group", support_group).execute()
            group_session_ids = {h["session_id"] for h in (handovers_q.data or [])}
            sessions = [s for s in sessions if s["id"] in group_session_ids]

        outcome_counts: dict = {"resolved_by_ai": 0, "escalated": 0, "abandoned": 0, "open": 0}
        escalation_reasons: dict = {}
        for s in sessions:
            outcome = s.get("outcome") or "open"
            outcome_counts[outcome if outcome in outcome_counts else "open"] += 1
            if outcome == "escalated" and s.get("escalation_reason"):
                reason = s["escalation_reason"]
                escalation_reasons[reason] = escalation_reasons.get(reason, 0) + 1

        total = len(sessions)
        def pct(n: int) -> float:
            return round(n / total * 100, 1) if total > 0 else 0.0

        # AI ratings from ai_session_feedback
        query2 = db.table("ai_session_feedback").select("rating")
        if start_date:
            query2 = query2.gte("created_at", start_date)
        if end_date:
            query2 = query2.lte("created_at", f"{end_date}T23:59:59Z")
        ratings_q = await query2.execute()
        ratings = [r["rating"] for r in (ratings_q.data or []) if r.get("rating") is not None]

        return {
            "period": {"start": start_date or "all time", "end": end_date or "all time"},
            "total_sessions": total,
            "resolved_by_ai": outcome_counts["resolved_by_ai"],
            "resolved_by_ai_pct": pct(outcome_counts["resolved_by_ai"]),
            "escalated": outcome_counts["escalated"],
            "escalated_pct": pct(outcome_counts["escalated"]),
            "abandoned": outcome_counts["abandoned"],
            "abandoned_pct": pct(outcome_counts["abandoned"]),
            "open": outcome_counts["open"],
            "avg_ai_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "total_ai_ratings": len(ratings),
            "escalation_reasons": escalation_reasons,
        }

    # ------------------------------------------------------------------
    # AI performance metrics
    # ------------------------------------------------------------------

    async def ai_performance(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> dict:
        db = await self._get_db()

        # Fetch all sessions with AI metric columns
        query = db.table("sessions").select("id,outcome,escalation_reason,ai_turns,fallback_count,created_at")
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59Z")
        sessions_q = await query.execute()
        sessions = sessions_q.data or []

        resolved_ai = [s for s in sessions if s.get("outcome") == "resolved_by_ai"]
        escalated = [s for s in sessions if s.get("outcome") == "escalated"]
        total_actioned = len(resolved_ai) + len(escalated)

        containment_rate = round(len(resolved_ai) / total_actioned, 4) if total_actioned > 0 else 0.0
        bot_failure_rate = round(
            len([s for s in sessions if (s.get("fallback_count") or 0) > 0]) / len(sessions), 4
        ) if sessions else 0.0

        ai_turns_resolved = [s["ai_turns"] for s in resolved_ai if s.get("ai_turns")]
        ai_turns_escalated = [s["ai_turns"] for s in escalated if s.get("ai_turns")]

        escalation_reasons: dict = {}
        for s in escalated:
            reason = s.get("escalation_reason")
            if reason:
                escalation_reasons[reason] = escalation_reasons.get(reason, 0) + 1

        # AI ratings
        query2 = db.table("ai_session_feedback").select("rating")
        if start_date:
            query2 = query2.gte("created_at", start_date)
        if end_date:
            query2 = query2.lte("created_at", f"{end_date}T23:59:59Z")
        ratings_q = await query2.execute()
        ratings = [r["rating"] for r in (ratings_q.data or []) if r.get("rating") is not None]

        return {
            "period": {"start": start_date or "all time", "end": end_date or "all time"},
            "total_sessions": len(sessions),
            "total_ai_resolved": len(resolved_ai),
            "total_escalated": len(escalated),
            "containment_rate": containment_rate,
            "avg_ai_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "total_ai_ratings": len(ratings),
            "avg_turns_before_resolution": round(sum(ai_turns_resolved) / len(ai_turns_resolved), 1) if ai_turns_resolved else None,
            "avg_turns_before_escalation": round(sum(ai_turns_escalated) / len(ai_turns_escalated), 1) if ai_turns_escalated else None,
            "bot_failure_rate": bot_failure_rate,
            "escalation_reasons": escalation_reasons,
        }

    # ------------------------------------------------------------------
    # Score a handover and persist result to agent_scores cache
    # ------------------------------------------------------------------

    async def score_and_cache(self, handover_id: str) -> dict:
        db = await self._get_db()
        result = await self.score(handover_id)

        cached = False
        try:
            await db.table("agent_scores").insert({
                "handover_id": handover_id,
                "agent_id": result.get("agent_id"),
                "overall_score": result["overall_score"],
                "rubric_scores": result["rubric_scores"],
                "ai_summary": result["summary"],
                "recommendations": result["recommendations"],
            }).execute()
            cached = True
        except Exception as e:
            logger.warning(f"Failed to cache score for handover {handover_id}: {e}")

        return {
            "handover_id": handover_id,
            "agent_id": result.get("agent_id"),
            "overall_score": result["overall_score"],
            "cached": cached,
            "scored_at": result["scored_at"],
        }

    def _empty_performance_report(
        self,
        agent_id: str,
        agent_name: str | None,
        start_date: str | None,
        end_date: str | None,
        resolution_stats: dict,
        timing_stats: dict,
    ) -> dict:
        return {
            "agent_id":    agent_id,
            "agent_name":  agent_name,
            "period": {
                "start":              start_date or "all time",
                "end":                end_date or "all time",
                "handovers_analyzed": 0,
            },
            "resolution_stats":  resolution_stats,
            "survey_stats": {
                "total_responses": 0,
                "avg_overall_satisfaction": None,
                "avg_nps": None,
                "response_time_distribution": {"fast": 0, "average": 0, "slow": 0},
                "helpfulness_distribution": {"very_helpful": 0, "somewhat_helpful": 0, "not_helpful": 0},
            },
            "timing_stats":      timing_stats,
            "overall_score":     0.0,
            "rubric_scores":     [],
            "summary":           "No handovers found for this agent in the specified period.",
            "strengths":         [],
            "improvement_areas": [],
            "recommendations":   [],
            "survey_available":  False,
            "scored_at":         datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_scorer_instance: Optional[AgentScorer] = None


def get_agent_scorer() -> AgentScorer:
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = AgentScorer()
    return _scorer_instance


async def initialize_agent_scorer() -> None:
    global _scorer_instance
    _scorer_instance = AgentScorer()


async def score_agent(handover_id: str) -> dict:
    return await get_agent_scorer().score(handover_id)


async def agent_performance(
    agent_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    sample_limit: int = 5,
) -> dict:
    return await get_agent_scorer().performance(agent_id, start_date, end_date, sample_limit)


async def team_performance_analytics(
    support_group: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    return await get_agent_scorer().team_performance(support_group, start_date, end_date)


async def org_performance_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    return await get_agent_scorer().org_performance(start_date, end_date)


async def funnel_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    support_group: str | None = None,
) -> dict:
    return await get_agent_scorer().funnel(start_date, end_date, support_group)


async def ai_performance_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    return await get_agent_scorer().ai_performance(start_date, end_date)


async def score_and_cache_handover(handover_id: str) -> dict:
    return await get_agent_scorer().score_and_cache(handover_id)
