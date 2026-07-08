web: gunicorn run:app --workers 4 --bind 0.0.0.0:$PORT
worker: celery -A app.celery worker --loglevel=info
