from __future__ import annotations
"""
ASGI/WSGI bridge for AWS Elastic Beanstalk.

The .ebextensions configs set:
    WSGIPath: wsgi:application

EB's gunicorn process loads this module and looks for `application`.
FastAPI is an ASGI app, so gunicorn MUST use UvicornWorker — this is
configured in the Procfile:
    gunicorn -k uvicorn.workers.UvicornWorker ... wsgi:application

With UvicornWorker, gunicorn treats `application` as an ASGI callable,
not a WSGI callable, so the lifespan startup hooks (NLU + summary
generator initialisation) fire correctly on each worker start.
"""
from app import app as application  # noqa: F401

__all__ = ["application"]
