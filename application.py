from __future__ import annotations
"""
AWS Elastic Beanstalk default entry point.

EB Python platform looks for a callable named `application` in application.py
by default (when no WSGIPath override is set). This re-exports the FastAPI ASGI
app from app.py under that name.

Local dev:
    uvicorn application:application --reload

Via gunicorn + uvicorn workers (as EB does via Procfile):
    gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 application:application
"""
from app import app as application  # noqa: F401

__all__ = ["application"]
