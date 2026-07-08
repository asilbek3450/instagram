# Blueprints packaging
from app.routes.auth import auth_bp
from app.routes.analytics import analytics_bp
from app.routes.posts import posts_bp
from app.routes.stories import stories_bp
from app.routes.ai import ai_bp
from app.routes.reports import reports_bp
from app.routes.admin import admin_bp
from app.routes.views import views_bp

__all__ = [
    'auth_bp',
    'analytics_bp',
    'posts_bp',
    'stories_bp',
    'ai_bp',
    'reports_bp',
    'admin_bp',
    'views_bp'
]
