# RetailGPT Test Evaluator — Guide

Automated accuracy testing for the RetailGPT customer support bot. Tests NLU intent detection, button routing, end-to-end conversation flows, and escalation rule triggers.

---

## Prerequisites

**1. Install the new dependency**

```bash
pip install pyyaml
```

Or reinstall everything:

```bash
pip install -r requirements.txt
```

**2. Start the API** (in a separate terminal)

```bash
uvicorn app:app --reload
```

The evaluator defaults to `http://localhost:8000`. Use `--base-url` if your API runs elsewhere.

---

## Quick Start

```bash
# Fast run — keyword NLU + button routing only (no Gemini API calls, ~2s)
python eval/test_evaluator.py --exclude-tags llm

# Full suite with HTML report
python eval/test_evaluator.py

# Run from project root — all commands below assume project root
```

---

## All CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--base-url TEXT` | `http://localhost:8000` | API base URL |
| `--cases PATH` | `eval/cases` | Directory containing YAML test case files |
| `--category TEXT` | _(all)_ | Run only one category: `nlu`, `button_routing`, `flow`, `escalation` |
| `--tags TEXT` | _(all)_ | Comma-separated tags to **include** (e.g. `keyword,cancel`) |
| `--exclude-tags TEXT` | _(none)_ | Comma-separated tags to **exclude** (e.g. `llm`) |
| `--filter TEXT` | _(all)_ | Substring match on test ID or description |
| `--concurrency INT` | `3` | Number of parallel sessions (keep ≤ 3 to respect Gemini rate limits) |
| `--timeout INT` | `10` | Per-request timeout in seconds |
| `--output-dir PATH` | `eval/reports` | Where to write HTML reports |
| `--no-html` | _(off)_ | Skip HTML report generation |
| `--fail-fast` | _(off)_ | Stop on first failure |
| `--verbose` | _(off)_ | Print full request/response JSON for every turn |
| `--threshold FLOAT` | `0.85` | Exit code 1 if overall accuracy falls below this (0–1 scale) |
| `--with-orders-api` | _(off)_ | Treat `flow_step_oneof` assertions as exact match (use when orders API is running) |

---

## Common Run Recipes

### Keyword-only (deterministic, zero Gemini cost)

Tests all inputs that hit the keyword matcher in `engine/nlu.py`. Always 100% if the API is reachable.

```bash
python eval/test_evaluator.py --exclude-tags llm
```

### NLU accuracy only

```bash
python eval/test_evaluator.py --category nlu
```

### NLU accuracy — English only

```bash
python eval/test_evaluator.py --category nlu --exclude-tags hinglish
```

### NLU accuracy — Hinglish only

```bash
python eval/test_evaluator.py --category nlu --tags hinglish
```

### Button routing only

```bash
python eval/test_evaluator.py --category button_routing
```

### End-to-end flow tests only

```bash
python eval/test_evaluator.py --category flow
```

### Escalation rules only

```bash
python eval/test_evaluator.py --category escalation
```

### Specific flow (e.g. cancel flows)

```bash
python eval/test_evaluator.py --category flow --tags cancel
```

### Single test by ID

```bash
python eval/test_evaluator.py --filter flow_cancel_fb_within_window --verbose
```

### CI mode (fail build if accuracy < 85%)

```bash
python eval/test_evaluator.py --exclude-tags llm --threshold 0.85
echo "Exit code: $?"
```

### With orders API running

```bash
python eval/test_evaluator.py --with-orders-api
```

---

## Test Categories

### `nlu` — NLU Text Input Tests (35 tests)

Single-turn tests. A text message is sent and the response's `nlu.intent` field is checked.

| Tag | Meaning |
|-----|---------|
| `keyword` | Input hits the keyword matcher — deterministic, fast |
| `llm` | Input goes to Gemini — non-deterministic, costs API quota |
| `english` | English language input |
| `hinglish` | Hindi/Hinglish input |

Subcategories: `agent`, `track_order`, `cancel`, `delayed`, `quality`, `missing`, `payment`, `quantity`, `coupon`, `delivery`, `modify`

### `button_routing` — Button Click Tests (25 tests)

Single-turn tests. An `option_select` event is sent from a known `flow_step` and the landing step is verified.

All button routing tests are deterministic (no NLU runs for button clicks).

Subcategories: `main_menu`, `cancel`, `quality`, `delivery`, `coupon`, `escalation`

### `flow` — End-to-End Conversation Tests (33 tests)

Multi-turn tests that simulate complete conversations from first message to resolution or escalation. Each turn's `context` is automatically carried forward from the previous response.

| Flow file | What it tests |
|-----------|---------------|
| `flow_cancel.yaml` | FB within 30s, FB outside window, grocery not-home→reschedule, fashion reschedule accepted |
| `flow_quality.yaml` | FB stale (upload→ticket), FB burnt, fashion wrong size, fashion packing, electronics mandatory escalation, ticket then agent |
| `flow_items.yaml` | FB incorrect, FB missing, fashion incorrect, electronics missing |
| `flow_order_status.yaml` | FB status, fashion status, electronics status, delayed late→done, delayed on-time, delayed→agent escalation |
| `flow_delivery.yaml` | Avoid bell, leave at door, directions (text input), neighbour, loop (two instructions) |
| `flow_coupon_billing.yaml` | Coupon forgot/find/apply, payment mandatory escalation, refund processing, invoice, payment failure, bill escalation |

### `escalation` — Escalation Rule Tests (9 tests)

Tests all 6 escalation rules from `engine/escalation.py`:

| Test ID | Rule | Trigger |
|---------|------|---------|
| `esc_customer_requested_001` | Rule 1 | "talk to agent" |
| `esc_customer_requested_002` | Rule 1 | "koi insaan chahiye" (Hinglish) |
| `esc_bot_fallback_001` | Rule 2 | 3 consecutive gibberish inputs |
| `esc_repeat_complaint_001` | Rule 3 | Same order+issue with open ticket in context |
| `esc_payment_mandatory_001` | Rule 4 | "payment issue" keyword |
| `esc_payment_mandatory_002` | Rule 4 | "paisa wapas chahiye" |
| `esc_electronics_mandatory_001` | Rule 5 | quality_issue + category=electronics |
| `esc_electronics_mandatory_002` | Rule 5 | missing_item + category=electronics |
| `esc_negative_sentiment_001` | Rule 6 | 2 strongly negative messages (Gemini sentiment) |

---

## Output

### Terminal

Color-coded per test: green `[PASS]`, red `[FAIL]`, yellow `[SKIP/ERR!]`.

Failed assertions are printed inline:

```
  [PASS] nlu_cancel_001                      45ms  English cancel intent (keyword)
  [FAIL] nlu_delayed_002                    130ms  Order late ho gaya (LLM)
         ✗ nlu_intent: expected='delayed_order', actual='unknown'
```

Followed by a score summary:

```
  ────────────────────────────────────────────────────────────
  SCORE SUMMARY
  ────────────────────────────────────────────────────────────
  NLU Accuracy                       87.5%  (21/24)
    └─ keyword tests                100.0%  (15/15)
    └─ llm tests                     66.7%  (6/9)
  Button Routing Accuracy            100.0%  (25/25)
  Flow Completion Rate                85.7%  (12/14)
  Escalation Accuracy                100.0%  (9/9)
  NLU Avg Confidence                  0.891
  ────────────────────────────────────────────────────────────
  Overall Accuracy                    91.2%  (84/92)
```

### HTML Report

Written to `eval/reports/report_YYYYMMDD_HHMMSS.html` — a self-contained file (no external dependencies, works offline).

- **Scorecard table** — accuracy % per category, color-coded (green ≥90%, amber 75–89%, red <75%)
- **Per-test expandable panels** — click to see turn-by-turn details, assertion results, and full request/response JSON
- Open in any browser: `xdg-open eval/reports/report_*.html`

---

## Understanding Test Case Files

### Single-turn (NLU or button routing)

```yaml
- id: nlu_cancel_001
  description: "English cancel intent (keyword)"
  category: nlu
  subcategory: cancel
  input:
    message: "cancel my order"
    message_type: text          # text | option_select | upload_complete
  expect:
    nlu_intent: cancel_order    # from RetailIntent enum
    nlu_source: keyword         # keyword | llm
    nlu_confidence_min: 0.90    # floor check
    render_type: options
    next_context.flow_step: flow_cancel_detect
  tags: [keyword, english, cancel]
```

### Multi-turn flow

```yaml
- id: flow_cancel_fb_within_window
  description: "Cancel FB within 30s"
  category: flow
  subcategory: cancel
  skip_order_api: true          # accept either path when orders API is absent
  tags: [flow, cancel, fb]
  turns:
    - turn: 1
      description: "User types cancel intent"
      input:
        message: "cancel my order"
        message_type: text
      expect:
        nlu_intent: cancel_order
        render_type: options

    - turn: 2
      description: "Select FB"
      input:
        message: "fb"
        message_type: option_select
        option_id: fb
      expect:
        # flow_step_oneof: accepts either step (order-select or direct)
        next_context.flow_step_oneof: [flow_order_select_cancel_fb, flow_cancel_fb]

    - turn: 3
      description: "Confirm within window"
      input_requires_step: flow_cancel_fb  # skip this turn if not at this step
      input:
        message: "yes"
        message_type: option_select
        option_id: yes
      expect:
        next_context.flow_step: flow_cancel_fb_reason

  final_assertions:             # checked against the last response
    escalate: false
```

### Escalation test with pre-seeded context

```yaml
- id: esc_repeat_complaint_001
  description: "Repeat complaint"
  category: escalation
  customer_id: "cust_repeat_test"
  initial_context:
    order_id: "ord_test_001"
    open_handovers:
      - id: "ticket_abc123"
        order_id: "ord_test_001"
        issue_type: "quality_issue"
        status: "pending_assignment"
  turns:
    - turn: 1
      input:
        message: "quality issue"
        message_type: text
      expect:
        escalate: true
        escalate_reason_contains: repeat_complaint
```

---

## All Assertion Keys

| Key | What it checks |
|-----|---------------|
| `render_type` | Exact match: `options`, `upload`, `text`, `text_input`, `handover` |
| `message_contains` | Case-insensitive substring in `response.message` |
| `message_not_contains` | Inverse substring check |
| `options_include_id` | List — all IDs must be present in `response.options` |
| `options_exact_ids` | List — exact set of option IDs (order-independent) |
| `options_count_min` | Minimum number of options |
| `next_context.flow_step` | Exact step ID match |
| `next_context.flow_step_oneof` | Step must match any value in list |
| `next_context.category` | Category value (`fb`, `fashion`, `electronics`, etc.) |
| `escalate` | `true` or `false` |
| `escalate_reason_contains` | Substring in `escalate_reason` |
| `nlu_intent` | Intent string (e.g. `cancel_order`, `quality_issue`) |
| `nlu_confidence_min` | Minimum confidence float (0.0–1.0) |
| `nlu_sentiment` | `positive`, `neutral`, or `negative` |
| `nlu_category` | Category detected by NLU |
| `nlu_source` | `keyword` or `llm` |
| `ticket_raised` | `true` or `false` |
| `issue_type` | e.g. `quality_issue_fb`, `incorrect_item` |
| `upload_config.min_photos` | Integer |
| `upload_config.video` | `true` or `false` |
| `terminal` | `true` or `false` |

---

## Adding New Test Cases

1. Find the appropriate YAML file in `eval/cases/` (or create a new one)
2. Add a new entry following the schema above
3. Pick a unique `id` (convention: `nlu_xxx`, `btn_xxx`, `flow_xxx`, `esc_xxx`)
4. Tag with relevant tags from the tables above
5. Run the specific test to verify: `python eval/test_evaluator.py --filter your_test_id --verbose`

---

## Interpreting NLU Accuracy Results

| Score | Meaning |
|-------|---------|
| keyword tests < 100% | Bug in keyword matching or API is down |
| llm tests < 70% | Gemini prompt needs tuning; check `prompts/nlu_system.txt` |
| llm tests 70–85% | Expected variance — LLM is non-deterministic |
| llm tests > 85% | Good NLU coverage |

**Hinglish accuracy is expected to be lower** (~60–75%) than English (~85–95%) on the LLM path. If keyword Hinglish tests fail, check `KEYWORD_MAP` in `engine/nlu.py`.

---

## Flow Order API

Several flow tests pass through an **order-select step** (`fetch_orders: true`) that calls an external orders API. When the orders API is not running:

- The app auto-skips to the next real step and prepends a notice
- Test cases with `skip_order_api: true` use `flow_step_oneof` assertions to accept either landing step
- Run with `--with-orders-api` when the orders API is available to enforce the exact expected step

---

## Files Reference

```
eval/
├── test_evaluator.py   CLI entry point (argparse, load cases, run, report)
├── runner.py           HTTP client, Session state, execute_turn()
├── assertions.py       Assertion evaluator (response dict + expect dict → results)
├── scoring.py          TestResult / TurnResult dataclasses, compute_scores()
├── reporter.py         Terminal ANSI output + HTML report generator
└── cases/
    ├── nlu_text_tests.yaml
    ├── button_routing_tests.yaml
    ├── flow_cancel.yaml
    ├── flow_quality.yaml
    ├── flow_items.yaml
    ├── flow_order_status.yaml
    ├── flow_delivery.yaml
    ├── flow_coupon_billing.yaml
    └── flow_escalation.yaml
```
