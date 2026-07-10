web: sh -c "gunicorn run:app --workers 4 --bind 0.0.0.0:${PORT:-5000}"
worker: celery -A app.celery worker --loglevel=info
bot: python telegram_bot.py
