# RetailGPT Analytics API

Reference guide for all 8 analytics endpoints — what they do, how they work internally, which database tables they touch, and which dashboard role should call them.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [How VoC Data Gets Into The System](#2-how-voc-data-gets-into-the-system)
3. [The 7 Scoring Rubrics](#3-the-7-scoring-rubrics)
4. [Escalation Reason Values](#4-escalation-reason-values)
5. [Score Caching — How It Works](#5-score-caching--how-it-works)
6. [Role → Endpoint Mapping](#6-role--endpoint-mapping)
7. [Endpoint Reference](#7-endpoint-reference)
   - [POST /analytics/evaluate-human-handover](#post-analyticsevaluate-human-handover)
   - [POST /analytics/evaluate-human-agent](#post-analyticsevaluate-human-agent)
   - [GET /analytics/agent-self](#get-analyticsagent-self)
   - [GET /analytics/team-performance](#get-analyticsteam-performance)
   - [GET /analytics/org-performance](#get-analyticsorg-performance)
   - [GET /analytics/funnel](#get-analyticsfunnel)
   - [GET /analytics/ai-performance](#get-analyticsai-performance)
   - [POST /analytics/score-and-cache](#post-analyticsscore-and-cache)

---

## 1. System Overview

RetailGPT support interactions follow this lifecycle:

```
Customer
   │
   ▼
AI Bot (/chat/turn)
   │
   ├── Resolved by AI ──────────────► Customer rates bot (1-5 stars)
   │                                         │
   │                                         ▼
   │                                  ai_session_feedback table
   │
   └── Escalated to Human ──────────► Agent handles the case
                │                            │
                ▼                            ▼
         handovers table            Handover resolved
                                            │
                                            ▼
                                  Customer rates agent (CSAT form)
                                            │
                                            ▼
                                   support_surveys table
```

### Two Survey Types

| Survey | Table | Linked to | Written by | When |
|--------|-------|-----------|-----------|------|
| Human agent feedback | `support_surveys` | `handover_id` | Frontend | After agent closes the handover |
| AI bot rating | `ai_session_feedback` | `session_id` | Backend (`/chat/turn`) | When customer selects a star rating at end of AI session |

These are intentionally separate. `support_surveys` always has a `handover_id` — it is never used for AI-only sessions.

### Three Dashboard Roles

| Role | Scope | Key Question |
|------|-------|-------------|
| **Agent** | Own handovers only | "How am I performing?" |
| **Manager** | All agents in their `support_group` | "How is my team performing?" |
| **Admin** | All agents across all groups | "How is the whole org performing?" |

---

## 2. How VoC Data Gets Into The System

No extra writes are required from the frontend. The backend captures all analytics signals automatically inside `/chat/turn`.

### Signal A — Escalation

When any escalation rule fires (rules-based or flow-based), **before returning the response** the backend writes:

```
sessions table
  outcome          = 'escalated'
  escalation_reason = <reason string>   (e.g. "customer_requested")
  ai_turns         = ctx.turn_count     (turns taken before escalation)
  fallback_count   = ctx.fallback_count (bot NLU failures in session)
```

This happens at two points in `app.py`:
- **Rules-based escalation** (lines ~125–142): triggered by `check_escalation()` — sentiment, fallback limit, payment query, etc.
- **Flow-based escalation** (lines ~152–169): triggered when the flow graph step transitions to `ESCALATE`.

### Signal B — AI Session Rating

When the customer submits a star rating (`option_id` = `"1"`–`"5"` at the `flow_end` step), the backend detects `flow_result.next_flow == "flow_rated"` and writes two records simultaneously:

```
ai_session_feedback table (INSERT)
  session_id    = request.session_id
  customer_id   = request.customer_id
  rating        = int(option_id)         (1–5)
  category      = ctx.category           (e.g. "fashion")
  turn_count    = ctx.turn_count
  fallback_count = ctx.fallback_count

sessions table (UPDATE)
  outcome       = 'resolved_by_ai'
  resolved_at   = now()
  ai_turns      = ctx.turn_count
  fallback_count = ctx.fallback_count
```

Both writes happen as a single `asyncio.gather()` call before the response is returned. Failures are caught and logged as warnings — they never break the customer's chat turn.

### Signal C — Human Survey

Unchanged. The frontend writes to `support_surveys` after the agent closes the handover. This has always been the case.

---

## 3. The 7 Scoring Rubrics

Used by `evaluate-human-handover`, `evaluate-human-agent`, `agent-self`, and `score-and-cache`. Gemini scores each rubric 1.0–10.0 with a written justification. The overall score is the weighted average.

| # | Rubric Key | Label | Weight | What Gemini Evaluates |
|---|-----------|-------|--------|----------------------|
| 1 | `resolution_quality` | Resolution Quality | **20%** | Was the customer's issue actually solved? Was the outcome complete? |
| 2 | `customer_satisfaction_alignment` | Customer Satisfaction Alignment | **20%** | Does the agent's behaviour match the CSAT/NPS the customer gave? Are there surprises either way? |
| 3 | `empathy_and_tone` | Empathy & Tone | **15%** | Did the agent acknowledge frustration, use warm language, and stay professional throughout? |
| 4 | `response_time` | Response Time | **15%** | How quickly did the agent respond? Was wait time appropriate given complexity? |
| 5 | `communication_clarity` | Communication Clarity | **10%** | Were messages clear, jargon-free, and easy for the customer to act on? |
| 6 | `problem_understanding` | Problem Understanding | **10%** | Did the agent correctly identify and scope the issue without the customer needing to repeat themselves? |
| 7 | `process_adherence` | Process Adherence | **10%** | Did the agent follow correct procedures, escalation policies, and resolution workflows? |

**Overall score formula:**
```
overall = (resolution_quality × 0.20)
        + (customer_satisfaction_alignment × 0.20)
        + (empathy_and_tone × 0.15)
        + (response_time × 0.15)
        + (communication_clarity × 0.10)
        + (problem_understanding × 0.10)
        + (process_adherence × 0.10)
```

Range: **1.0** (very poor) → **10.0** (excellent).

---

## 4. Escalation Reason Values

These are the possible values for `sessions.escalation_reason`. They appear in the `/analytics/funnel` and `/analytics/ai-performance` responses under `escalation_reasons`.

| Value | Trigger | Priority |
|-------|---------|----------|
| `customer_requested` | Customer's message matched the `REQUEST_AGENT` intent | Immediate |
| `bot_fallback_limit_reached_N` | Bot failed to understand N consecutive messages (N ≥ 3) | Immediate |
| `repeat_complaint_open_ticket_{id}` | Same `order_id` + same `issue_type` already has an open handover | Immediate |
| `payment_query_mandatory_escalation` | Any `PAYMENT_QUERY` intent — always goes to human | Mandatory |
| `electronics_mandatory_escalation` | Quality/missing/wrong item issue for Electronics category — always escalated | Mandatory |
| `customer_frustrated_N_negative_turns` | N turns detected as negative sentiment (N ≥ 2) | Normal |
| `flow_endpoint` | The flow graph for this issue type has an `ESCALATE` terminal step | Normal |
| `mandatory_{intent}` | Intent maps directly to an escalation step in the flow graph | Normal |

**Immediate** escalations bypass all other rules. **Mandatory** rules apply regardless of sentiment or fallback count. **Normal** rules are checked after immediate ones.

---

## 5. Score Caching — How It Works

`evaluate-human-handover` and `evaluate-human-agent` call Gemini every time — useful for on-demand drill-downs but too slow and costly for a dashboard that loads scores for 10 agents at once.

`team-performance` and `org-performance` solve this by reading from the `agent_scores` cache table instead of calling Gemini. The cache is populated by `score-and-cache`.

```
                           ┌─────────────────────────┐
Handover resolved          │ POST /score-and-cache    │
(frontend marks resolved)  │                         │
        │                  │  1. Calls score() logic  │
        └─────────────────►│  2. Calls Gemini once    │
                           │  3. INSERTs to           │
                           │     agent_scores table   │
                           └───────────┬─────────────┘
                                       │
                              agent_scores table
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                      │
                    ▼                                      ▼
     GET /team-performance                   GET /org-performance
     (reads latest score per agent,          (same — reads cached scores,
      no Gemini call, fast)                   no Gemini call)
```

**Recommendation:** Call `POST /score-and-cache` fire-and-forget every time an agent marks a handover as resolved. This keeps the cache fresh so team and org dashboards are always fast.

---

## 6. Role → Endpoint Mapping

| Role | Endpoint | Purpose |
|------|----------|---------|
| **Agent** | `GET /analytics/agent-self` | Own score, rubric breakdown, AI coaching |
| **Manager** | `GET /analytics/team-performance` | Leaderboard of all agents in their group |
| **Manager** | `GET /analytics/funnel?support_group=X` | Funnel for their group's issue categories |
| **Manager** | `GET /analytics/ai-performance` | AI bot metrics affecting their group's load |
| **Admin** | `GET /analytics/org-performance` | Cross-group comparison |
| **Admin** | `GET /analytics/funnel` | Org-wide session funnel |
| **Admin** | `GET /analytics/ai-performance` | Org-wide AI bot metrics |
| **System** (on handover resolve) | `POST /analytics/score-and-cache` | Populate score cache |
| **Any role** (drill-down) | `POST /analytics/evaluate-human-handover` | Score one specific case |
| **Any role** (drill-down) | `POST /analytics/evaluate-human-agent` | Full AI narrative for one agent |

---

## 7. Endpoint Reference

---

### POST /analytics/evaluate-human-handover

**Score a single human agent interaction using AI rubric evaluation.**

#### When to Use
Use this for drill-down views — when a manager or admin clicks on a specific handover card to see the detailed rubric breakdown and AI justifications. Also useful for flagged/escalated cases that need review.

#### Request Body

```json
{
  "handover_id": "hov_xyz789"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `handover_id` | string | Yes | ID of the handover to score |

#### Internal Flow

```
1. Fetch handover record (id, session_id, agent_id, status, created_at,
   resolved_at, transcript, support_group) from handovers table

2. Concurrently fetch:
   - messages for the session (role, content, created_at) — ordered by time
   - support_surveys for this handover_id (CSAT, NPS, helpfulness, response_time)
   - tickets for this session (issue_type, status, ticket_source)
   - agent name from users table

3. Build a structured prompt containing:
   - Handover status + support group + timestamps
   - Survey data (or "No survey data available" if absent)
   - Ticket info (or "No ticket data available" if absent)
   - Full conversation transcript

4. Call Gemini 2.5-flash-lite → returns JSON with 7 rubric scores + justifications
   + summary + recommendations

5. Compute weighted overall score
   Return response
```

**Gemini called:** Yes — every request.

#### Tables Read

`handovers` · `messages` · `support_surveys` · `tickets` · `users`

#### Response

```json
{
  "handover_id": "hov_xyz789",
  "agent_id": "agent_uuid_123",
  "agent_name": "Sarah M.",
  "overall_score": 7.85,
  "rubric_scores": [
    {
      "rubric": "resolution_quality",
      "label": "Resolution Quality",
      "score": 8.5,
      "justification": "The agent successfully resolved the cancellation request within one exchange.",
      "weight": 0.20
    }
    // ... 6 more rubrics
  ],
  "summary": "Sarah handled the billing dispute professionally and resolved it in under 10 minutes. The customer appeared satisfied based on the survey score.",
  "recommendations": [
    "Acknowledge wait time at the start of calls",
    "Confirm resolution before closing the ticket"
  ],
  "survey_available": true,
  "ticket_available": true,
  "scored_at": "2026-04-02T10:30:00+00:00"
}
```

#### Error Responses

| Code | Condition |
|------|-----------|
| 404 | `handover_id` not found in database |
| 503 | `SUPABASE_URL` or `GEMINI_API_KEY` not set |
| 500 | Gemini API failure or unexpected error |

---

### POST /analytics/evaluate-human-agent

**Evaluate an agent's overall performance across all their handovers with full AI narrative, stats, and coaching.**

#### When to Use
Use for deep performance reviews — monthly 1:1s, performance improvement plans, or when a manager wants the full AI-generated narrative for a specific agent. This is the most detailed and expensive endpoint (calls Gemini once per request).

#### Request Body

```json
{
  "agent_id": "agent_uuid_123",
  "start_date": "2026-03-01",
  "end_date": "2026-03-31",
  "sample_limit": 5
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `agent_id` | string | Yes | — | Agent's user ID |
| `start_date` | string | No | all time | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | No | all time | Inclusive end date (YYYY-MM-DD) |
| `sample_limit` | integer | No | 5 | Number of transcripts sent to Gemini (1–10). Higher = more accurate, slower. |

#### Internal Flow

```
1. Validate agent exists — fetch name + support_group from users table
   → 404 if not found

2. Fetch all handovers for this agent in the date range
   (id, session_id, status, created_at, resolved_at)

3. Compute resolution stats: total / resolved / expired / pending / accepted / rate
   Compute timing stats: avg/min/max resolution hours

4. If no handovers → return zero-data report (no Gemini call)

5. Concurrently fetch:
   - All support_surveys for all handover_ids
   - All tickets for all session_ids

6. Compute survey stats: avg CSAT, avg NPS, response_time distribution,
   helpfulness distribution

7. Select sample handovers for transcripts (up to sample_limit):
   - Prefer resolved handovers that have surveys (most data-rich for Gemini)
   - Fill remaining slots from any other handovers

8. Fetch messages for each sampled handover (concurrently)

9. Build structured prompt with all stats + sample transcripts
   Call Gemini 2.5-flash-lite → returns rubric_scores + summary +
   strengths + improvement_areas + recommendations

10. Compute weighted overall score
    Return response
```

**Gemini called:** Yes — once per request.

#### Tables Read

`users` · `handovers` · `support_surveys` · `tickets` · `messages`

#### Response

```json
{
  "agent_id": "agent_uuid_123",
  "agent_name": "Sarah M.",
  "period": {
    "start": "2026-03-01",
    "end": "2026-03-31",
    "handovers_analyzed": 47
  },
  "resolution_stats": {
    "total": 47,
    "resolved": 41,
    "expired": 3,
    "pending": 2,
    "accepted": 1,
    "resolution_rate": 0.9318
  },
  "survey_stats": {
    "total_responses": 28,
    "avg_overall_satisfaction": 4.2,
    "avg_nps": 7.8,
    "response_time_distribution": { "fast": 18, "average": 8, "slow": 2 },
    "helpfulness_distribution": { "very_helpful": 20, "somewhat_helpful": 6, "not_helpful": 2 }
  },
  "timing_stats": {
    "avg_resolution_hours": 1.4,
    "min_resolution_hours": 0.1,
    "max_resolution_hours": 8.2
  },
  "overall_score": 7.9,
  "rubric_scores": [ /* 7 rubrics */ ],
  "summary": "Sarah is a consistent performer with strong resolution rates...",
  "strengths": [
    "Consistently fast first response time",
    "High survey scores in the billing group"
  ],
  "improvement_areas": [
    "Occasionally closes tickets before confirming resolution with customer",
    "Tone becomes terse on repeat contacts"
  ],
  "recommendations": [
    "Add a closing confirmation step to every resolved handover",
    "Review the repeat complaint handling playbook"
  ],
  "survey_available": true,
  "scored_at": "2026-04-02T10:35:00+00:00"
}
```

#### Error Responses

| Code | Condition |
|------|-----------|
| 404 | `agent_id` not found |
| 503 | Env config missing |
| 500 | Gemini failure or unexpected error |

---

### GET /analytics/agent-self

**An agent's own performance dashboard — same data as `evaluate-human-agent` but designed for self-service via query params.**

#### When to Use
This is the endpoint the agent's own dashboard tab calls. The frontend passes the currently logged-in agent's ID. The agent can only see their own data — the frontend enforces this by always passing the authenticated user's ID.

The response is identical in shape to `evaluate-human-agent` — the only difference is that it's a GET with query parameters instead of a POST with a body.

#### Query Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `agent_id` | string | Yes | — | Agent's own user ID |
| `start_date` | string | No | all time | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | No | all time | Inclusive end date (YYYY-MM-DD) |
| `sample_limit` | integer | No | 5 | Transcript samples sent to Gemini (1–10) |

#### Example Request

```
GET /analytics/agent-self?agent_id=agent_uuid_123&start_date=2026-03-01&end_date=2026-03-31
```

#### Internal Flow

Identical to `evaluate-human-agent`. The same `agent_performance()` function is called internally.

**Gemini called:** Yes — once per request.

#### Response

Same shape as `EvaluateHumanAgentResponse` — see the `evaluate-human-agent` section above.

---

### GET /analytics/team-performance

**Manager view — leaderboard and aggregate stats for all agents in a support group. Does not call Gemini.**

#### When to Use
The primary endpoint for the manager's dashboard. Call this on page load to get the team leaderboard. It is deliberately fast — it reads pre-computed scores from the `agent_scores` cache table rather than calling Gemini per agent. Pair it with `POST /score-and-cache` to keep scores fresh.

#### Query Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `support_group` | string | Yes | One of: `billing`, `operations`, `general` |
| `start_date` | string | No | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | No | Inclusive end date (YYYY-MM-DD) |

#### Example Request

```
GET /analytics/team-performance?support_group=billing&start_date=2026-03-01&end_date=2026-03-31
```

#### Internal Flow

```
1. Fetch all agents WHERE support_group = <param> from users table
   → 404 if no agents found for this group

2. Batch-fetch ALL handovers for all agent_ids in ONE query
   (filtered by date range)
   Group handovers by agent_id in Python

3. Concurrently:
   a. Batch-fetch ALL surveys for all handover_ids in ONE query
      Group surveys by agent_id via handover→agent mapping
   b. Fetch latest cached overall_score from agent_scores for each agent_id
      (ordered by evaluated_at DESC — most recent score wins)

4. For each agent: compute
   - resolution_stats (total/resolved/expired/pending/accepted/rate)
   - survey_stats (avg CSAT, avg NPS, distributions)
   - timing_stats (avg/min/max resolution hours)
   - overall_score (from cache, null if never scored via score-and-cache)

5. Sort agents by overall_score descending (null scores go last)

6. Compute group-level aggregates across all agents

7. Return response
```

**Gemini called:** No. All scores come from the `agent_scores` cache.

#### Tables Read

`users` · `handovers` · `support_surveys` · `agent_scores`

#### Response

```json
{
  "support_group": "billing",
  "period": { "start": "2026-03-01", "end": "2026-03-31" },
  "agents": [
    {
      "agent_id": "agent_uuid_123",
      "agent_name": "Sarah M.",
      "overall_score": 8.1,
      "resolution_stats": { "total": 47, "resolved": 41, "expired": 3, "pending": 2, "accepted": 1, "resolution_rate": 0.9318 },
      "survey_stats": { "total_responses": 28, "avg_overall_satisfaction": 4.2, "avg_nps": 7.8, "response_time_distribution": {...}, "helpfulness_distribution": {...} },
      "timing_stats": { "avg_resolution_hours": 1.4, "min_resolution_hours": 0.1, "max_resolution_hours": 8.2 }
    }
    // ... more agents, sorted by overall_score desc
  ],
  "group_stats": {
    "total_agents": 5,
    "total_handovers": 203,
    "total_resolved": 178,
    "group_resolution_rate": 0.8768,
    "avg_score": 7.4,
    "total_survey_responses": 112,
    "avg_overall_satisfaction": 4.1,
    "avg_nps": 7.2
  }
}
```

#### Error Responses

| Code | Condition |
|------|-----------|
| 404 | `support_group` has no agents in the users table |
| 503 | Env config missing |
| 500 | Unexpected error |

---

### GET /analytics/org-performance

**Admin view — cross-group comparison with org-wide aggregates. Does not call Gemini.**

#### When to Use
The admin's top-level dashboard. Shows all support groups side by side — which group has the best resolution rate, highest CSAT, lowest average score — so the admin can identify which group needs attention. Supports the same date range filtering as team-performance.

#### Query Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | No | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | No | Inclusive end date (YYYY-MM-DD) |

#### Example Request

```
GET /analytics/org-performance?start_date=2026-03-01&end_date=2026-03-31
```

#### Internal Flow

```
1. Fetch all users WHERE support_group IS NOT NULL
   (excludes customer accounts that have no support_group)
   Collect distinct support_group values

2. Batch-fetch ALL handovers for ALL agent_ids in ONE query
   (date-filtered)
   Group handovers by handover.support_group (uses the group stored on the handover)

3. Batch-fetch ALL surveys for all handover_ids
   Group surveys by support_group via handover→group mapping

4. Fetch all agent_scores for all agent_ids
   Map scores to groups via agent_id → support_group

5. For each support_group: compute
   - agent_count
   - avg_score (mean of all cached scores in that group)
   - resolution_stats
   - survey_stats

6. Compute org-wide aggregates across all groups

7. Return response
```

**Gemini called:** No.

#### Tables Read

`users` · `handovers` · `support_surveys` · `agent_scores`

#### Response

```json
{
  "period": { "start": "2026-03-01", "end": "2026-03-31" },
  "groups": [
    {
      "support_group": "billing",
      "agent_count": 5,
      "avg_score": 7.4,
      "resolution_stats": { "total": 203, "resolved": 178, "expired": 14, "pending": 8, "accepted": 3, "resolution_rate": 0.9271 },
      "survey_stats": { "total_responses": 112, "avg_overall_satisfaction": 4.1, "avg_nps": 7.2, "response_time_distribution": {...}, "helpfulness_distribution": {...} }
    },
    {
      "support_group": "operations",
      "agent_count": 4,
      "avg_score": 6.9,
      "resolution_stats": { ... },
      "survey_stats": { ... }
    }
  ],
  "org_stats": {
    "total_groups": 3,
    "total_agents": 12,
    "total_handovers": 580,
    "total_resolved": 511,
    "org_resolution_rate": 0.8810,
    "avg_score": 7.2,
    "total_survey_responses": 298,
    "avg_overall_satisfaction": 4.0,
    "avg_nps": 7.1
  }
}
```

---

### GET /analytics/funnel

**Session funnel breakdown — how many sessions were resolved by AI vs escalated to a human vs abandoned.**

#### When to Use
The funnel is the top-level health metric for the whole support system. Use it on the manager and admin dashboards to answer:
- "What fraction of customer sessions never needed a human?" (containment)
- "Why are customers escalating?" (escalation_reason breakdown)
- "How satisfied are customers with the AI bot?" (avg_ai_rating)

The optional `support_group` filter narrows the funnel to sessions that escalated into a specific group — useful for managers who only care about escalations that landed on their team.

#### Query Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | No | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | No | Inclusive end date (YYYY-MM-DD) |
| `support_group` | string | No | If provided, only includes sessions linked to this group via their escalation handover |

#### Example Requests

```
GET /analytics/funnel?start_date=2026-03-01&end_date=2026-03-31
GET /analytics/funnel?support_group=billing&start_date=2026-04-01
```

#### Internal Flow

```
1. Fetch all sessions in date range
   (id, outcome, escalation_reason, ai_turns, fallback_count, created_at)

2. If support_group filter provided:
   Fetch session_ids from handovers WHERE support_group = <param>
   Filter sessions list to only those session_ids

3. Count sessions by outcome:
   resolved_by_ai / escalated / abandoned / open
   (outcome is null → counted as "open")

4. Build escalation_reasons dict:
   { "customer_requested": 12, "payment_query_mandatory_escalation": 8, ... }

5. Compute percentages: each outcome / total × 100

6. Fetch ratings from ai_session_feedback in same date range
   Compute avg_ai_rating

7. Return response
```

**Gemini called:** No — pure DB aggregation.

#### Tables Read

`sessions` · `ai_session_feedback` · `handovers` (only if `support_group` filter used)

#### Response

```json
{
  "period": { "start": "2026-03-01", "end": "2026-03-31" },
  "total_sessions": 1240,
  "resolved_by_ai": 862,
  "resolved_by_ai_pct": 69.5,
  "escalated": 311,
  "escalated_pct": 25.1,
  "abandoned": 54,
  "abandoned_pct": 4.4,
  "open": 13,
  "avg_ai_rating": 4.1,
  "total_ai_ratings": 724,
  "escalation_reasons": {
    "customer_requested": 98,
    "payment_query_mandatory_escalation": 87,
    "bot_fallback_limit_reached_3": 52,
    "customer_frustrated_2_negative_turns": 38,
    "electronics_mandatory_escalation": 21,
    "flow_endpoint": 15
  }
}
```

**Reading the escalation_reasons:** A high `bot_fallback_limit_reached_N` count means the AI is failing to understand customers — consider retraining NLU. A high `customer_requested` count means customers are losing confidence in the bot early.

---

### GET /analytics/ai-performance

**AI bot quality metrics — containment rate, bot failure rate, conversation efficiency, and satisfaction.**

#### When to Use
This is the deep-dive on AI bot quality. While `/funnel` gives the headline numbers, this endpoint answers the "why" questions:
- "What fraction of sessions did the bot handle without needing a human?" (containment_rate)
- "How often did the bot fail to understand the customer?" (bot_failure_rate)
- "How many turns did it take to resolve vs escalate?" (avg_turns)
- "What are the most common escalation triggers?" (escalation_reasons)

Use this for: monthly AI model quality reviews, deciding whether to retrain NLU, and benchmarking AI improvements over time.

#### Query Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | No | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | No | Inclusive end date (YYYY-MM-DD) |

#### Example Request

```
GET /analytics/ai-performance?start_date=2026-03-01&end_date=2026-03-31
```

#### Internal Flow

```
1. Fetch all sessions in date range
   (id, outcome, escalation_reason, ai_turns, fallback_count, created_at)

2. Separate into:
   - resolved_ai   = sessions WHERE outcome = 'resolved_by_ai'
   - escalated     = sessions WHERE outcome = 'escalated'
   - total_actioned = resolved_ai + escalated  (excludes open/abandoned)

3. Compute:
   containment_rate = len(resolved_ai) / total_actioned
   bot_failure_rate = sessions with fallback_count > 0 / total sessions

4. Compute avg turns:
   avg_turns_before_resolution = mean(ai_turns) for resolved_ai sessions
   avg_turns_before_escalation = mean(ai_turns) for escalated sessions

5. Build escalation_reasons dict from escalated sessions

6. Fetch ratings from ai_session_feedback in same date range
   Compute avg_ai_rating

7. Return response
```

**Gemini called:** No.

#### Tables Read

`sessions` · `ai_session_feedback`

#### Response

```json
{
  "period": { "start": "2026-03-01", "end": "2026-03-31" },
  "total_sessions": 1240,
  "total_ai_resolved": 862,
  "total_escalated": 311,
  "containment_rate": 0.7350,
  "avg_ai_rating": 4.1,
  "total_ai_ratings": 724,
  "avg_turns_before_resolution": 5.2,
  "avg_turns_before_escalation": 3.8,
  "bot_failure_rate": 0.1210,
  "escalation_reasons": {
    "customer_requested": 98,
    "payment_query_mandatory_escalation": 87,
    "bot_fallback_limit_reached_3": 52,
    "customer_frustrated_2_negative_turns": 38,
    "electronics_mandatory_escalation": 21,
    "flow_endpoint": 15
  }
}
```

**Interpreting the numbers:**
- `containment_rate` of `0.735` means 73.5% of sessions were fully handled by the AI — no human agent needed.
- `bot_failure_rate` of `0.121` means in 12.1% of sessions the bot failed to understand at least one message.
- `avg_turns_before_escalation` (3.8) being lower than `avg_turns_before_resolution` (5.2) suggests escalations happen early in conversations, not after long frustrating exchanges.

---

### POST /analytics/score-and-cache

**Score a resolved handover with Gemini rubrics and save the result to the `agent_scores` cache table.**

#### When to Use
Call this automatically every time an agent marks a handover as **resolved** in the frontend. It is designed to be **fire-and-forget** — the frontend does not need to wait for the response or display it.

This keeps the `agent_scores` table fresh so that `GET /team-performance` and `GET /org-performance` always show up-to-date scores without calling Gemini on every dashboard load.

#### Request Body

```json
{
  "handover_id": "hov_xyz789"
}
```

#### Internal Flow

```
1. Call score() — identical to evaluate-human-handover logic:
   Fetch handover + messages + survey + ticket
   Build prompt → call Gemini → parse rubric scores → compute overall score

2. INSERT into agent_scores table:
   {
     handover_id,
     agent_id,
     overall_score,
     rubric_scores,   ← full JSON array of 7 rubric objects
     ai_summary,      ← the summary text
     recommendations, ← array of recommendation strings
     evaluated_at: now()
   }

3. Return {handover_id, agent_id, overall_score, cached, scored_at}
   cached = true if INSERT succeeded, false if it failed (score still returned)
```

**Gemini called:** Yes — once per handover.

**Note:** Each call creates a new row in `agent_scores`. If the same handover is scored multiple times (e.g. re-score after a dispute), multiple rows exist — `team-performance` reads the most recent one (`ORDER BY evaluated_at DESC LIMIT 1` per agent).

#### Tables Read

`handovers` · `messages` · `support_surveys` · `tickets` · `users`

#### Tables Written

`agent_scores`

#### Response

```json
{
  "handover_id": "hov_xyz789",
  "agent_id": "agent_uuid_123",
  "overall_score": 7.85,
  "cached": true,
  "scored_at": "2026-04-02T10:30:00+00:00"
}
```

| Field | Description |
|-------|-------------|
| `overall_score` | Weighted rubric average (1.0–10.0) |
| `cached` | `true` if successfully written to `agent_scores`. `false` means the score was computed but the DB write failed — the score is still returned to the caller. |
| `scored_at` | ISO 8601 UTC timestamp |

#### Frontend Integration Pattern

```js
// After agent marks handover as resolved
await supabase.from('handovers')
  .update({ status: 'resolved', resolved_at: new Date().toISOString() })
  .eq('id', handoverId)

// Fire-and-forget — do not await, do not block the UI
fetch('/analytics/score-and-cache', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ handover_id: handoverId }),
}).catch(() => {})  // silent fail — analytics should never break the agent workflow
```

#### Error Responses

| Code | Condition |
|------|-----------|
| 404 | `handover_id` not found |
| 503 | Env config missing |
| 500 | Gemini failure or unexpected error |

---

## General Notes

- **Gemini model:** `gemini-2.5-flash-lite` — optimised for speed and cost.
- **Date filtering:** All `start_date` / `end_date` params are inclusive. Format: `YYYY-MM-DD`. Omitting both returns all-time data.
- **Error codes:** `404` entity not found · `503` missing env config · `500` unexpected server error.
- **Supabase client:** All endpoints use the same shared `AsyncClient` singleton initialised with `SUPABASE_SERVICE_ROLE_KEY`. The client is lazy-loaded on first use.
- **Thread safety:** All DB-heavy operations use `asyncio.gather()` for concurrent queries — a single request to `team-performance` for 8 agents does not make 8 sequential DB round-trips.
