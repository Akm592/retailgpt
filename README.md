# RetailGPT MVP

RetailGPT MVP is a FastAPI-based customer support assistant for retail workflows. It uses a lightweight flow engine plus Gemini-powered NLU and conversation summarization to route customer issues, gather context, and escalate when needed.

## Features

- FastAPI service with JSON endpoints
- Intent detection with keyword fallback and Gemini classification
- Flow-based conversation routing for common retail support cases
- Escalation handling with AI-generated handover summaries
- Built-in test UI at `/test`

## Tech Stack

- Python 3.10+
- FastAPI
- Uvicorn
- Google Generative AI
- Pydantic
- python-dotenv

## Project Structure

- `app.py` - FastAPI application and routes
- `engine/` - NLU, flow engine, escalation, and summary logic
- `schemas/` - Pydantic request and response models
- `prompts/` - System prompts for Gemini
- `static/test.html` - Simple test chat UI

## Setup

1. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set your Gemini API key in a `.env` file:

```env
GEMINI_API_KEY=your_api_key_here
```

## Run the App

Start the API with Uvicorn:

```bash
uvicorn app:app --reload
```

The app will be available at:

- API: `http://127.0.0.1:8000`
- Test UI: `http://127.0.0.1:8000/test`
- Interactive docs: `http://127.0.0.1:8000/docs`

## API Endpoints

- `POST /intent` - health/status-style placeholder endpoint
- `POST /chat/turn` - process one customer turn and return the next response
- `POST /chat/summary` - generate a support handover summary

## Example Request

```bash
curl -X POST http://127.0.0.1:8000/chat/turn \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_abc123",
    "message": "My order is delayed",
    "message_type": "text",
    "context": {
      "current_flow": null,
      "flow_step": null,
      "category": null,
      "order_id": null,
      "turn_count": 0,
      "negative_turns": 0,
      "fallback_count": 0,
      "customer_id": "cust_xyz",
      "open_handovers": []
    },
    "transcript": [
      {"role": "customer", "content": "My order is delayed"}
    ]
  }'
```

## Notes

- `GEMINI_API_KEY` is required for NLU and summary generation.
- The flow engine uses a flat step graph in `engine/flows.py`.
- The `/test` page is a quick way to exercise the chat flow in the browser.
