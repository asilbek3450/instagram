from app import create_app, celery

# Create Flask application instance
app = create_app()

# Push application context so extensions can access config
app.app_context().push()

# Ensure Celery can discover tasks
import app.tasks
