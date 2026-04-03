# RetailGPT Analytics Endpoints - Instruction & Logic Guide

This guide explains the technical logic, use cases, and internal working of the 8 core analytics endpoints in the RetailGPT MVP.

---

## 1. AI-Powered Individual Evaluation (Gemini-Driven)
These endpoints use **Gemini 2.5-flash-lite** to analyze conversation transcripts and provide qualitative feedback based on 7 scoring rubrics (Resolution Quality, Empathy, Clarity, etc.).

### **POST /analytics/evaluate-human-handover**
*   **Logic:** Fetches a specific handover's transcript, customer surveys, and ticket info. It sends this context to Gemini, which returns scores (1–10) and justifications for each rubric.
*   **Where to Use:** Drill-down views when a manager wants to see exactly *why* a specific interaction was rated a certain way.
*   **Working:** Triggers a live call to the Gemini API. It’s "expensive" in terms of tokens and time (~3-5 seconds).

### **POST /analytics/evaluate-human-agent** & **GET /analytics/agent-self**
*   **Logic:** Aggregates all handovers for a specific agent over a date range. It computes hard stats (resolution rate, avg response time) and then sends a *sample* of transcripts to Gemini to generate a narrative performance review.
*   **Where to Use:** Monthly 1:1s, performance reviews, or the agent's personal "My Performance" tab.
*   **Working:** Combines SQL aggregations with a single comprehensive Gemini prompt that summarizes strengths, weaknesses, and coaching tips.

---

## 2. Dashboard Performance (Cache-Driven)
These are designed to be extremely fast by reading pre-computed data from the database instead of calling AI on every request.

### **GET /analytics/team-performance**
*   **Logic:** Generates a leaderboard for a specific team (e.g., "Billing"). It pulls the latest cached scores from the `agent_scores` table.
*   **Where to Use:** The main Manager Dashboard to see at a glance how all their agents are performing relative to each other.
*   **Working:** Pure SQL query. It does **not** call Gemini, making it near-instant.

### **GET /analytics/org-performance**
*   **Logic:** Similar to team performance but compares different support groups (e.g., "Billing" vs. "Operations") to see which department needs more resources or training.
*   **Where to Use:** Admin/Executive dashboard for high-level organizational health.

---

## 3. System Health & Funnel (Pure Data)
These focus on the "Big Picture" of the AI bot's effectiveness and the customer journey.

### **GET /analytics/funnel**
*   **Logic:** Tracks the lifecycle of all sessions. How many were resolved by AI? How many were escalated? How many were abandoned?
*   **Where to Use:** Monitoring the "Containment Rate"—the percentage of customers who didn't need a human.
*   **Working:** Aggregates the `sessions` table based on the `outcome` column.

### **GET /analytics/ai-performance**
*   **Logic:** A deep dive into the bot's failures. It tracks `fallback_count` (how often the bot didn't understand) and maps out `escalation_reasons` (e.g., "customer frustrated").
*   **Where to Use:** Product/Engineering teams looking to improve the NLU (Natural Language Understanding) or the chat flows.

---

## 4. The "Glue" Endpoint
### **POST /analytics/score-and-cache**
*   **Logic:** This is the bridge between the AI and the fast dashboards. It runs the Gemini evaluation on a resolved handover and **saves** the result to the `agent_scores` table.
*   **Where to Use:** It should be called automatically by the frontend as a "fire-and-forget" request as soon as an agent marks a case as resolved.
*   **Working:** It ensures the `team-performance` and `org-performance` endpoints stay fresh without needing to call Gemini in real-time.
