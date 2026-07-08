from app import create_app, db
import os

app = create_app()

# Ensure database tables exist at import time so both `python run.py` (dev)
# and `gunicorn run:app` (Docker/production) start against a ready schema.
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=app.config.get('DEBUG', False))
