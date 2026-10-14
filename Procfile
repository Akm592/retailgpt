web: gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers 2 --timeout 120 --log-level info wsgi:application
