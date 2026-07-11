from flask import Flask, request, session, make_response, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from celery import Celery
from flask_babel import Babel

# Initialize extensions at the package level
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
celery = Celery()

def get_locale():
    # 1. Check URL parameters
    lang = request.args.get('lang')
    if lang in ['en', 'uz', 'ru']:
        return lang
    # 2. Check cookies
    lang = request.cookies.get('lang')
    if lang in ['en', 'uz', 'ru']:
        return lang
    # 3. Fallback to Accept-Language header
    return request.accept_languages.best_match(['en', 'uz', 'ru']) or 'en'

babel = Babel()

def make_celery(app):
    """
    Configure Celery to work with Flask's application context.
    """
    celery.conf.update(
        broker_url=app.config.get('CELERY_BROKER_URL'),
        result_backend=app.config.get('CELERY_RESULT_BACKEND'),
        task_ignore_result=False
    )

    # Periodic maintenance for real (non-simulated) Instagram accounts.
    # Run a `celery beat` process alongside the worker to activate these.
    from celery.schedules import crontab
    celery.conf.beat_schedule = {
        'refresh-expiring-instagram-tokens': {
            'task': 'app.tasks.refresh_expiring_tokens',
            'schedule': crontab(hour=3, minute=0),  # daily 03:00
        },
        'sync-real-instagram-accounts': {
            'task': 'app.tasks.sync_all_real_accounts',
            'schedule': crontab(hour=4, minute=0),  # daily 04:00
        },
    }

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
                
    celery.Task = ContextTask
    return celery

def create_app(config_class='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    babel.init_app(app, locale_selector=get_locale)

    # Auto-migration columns check for SQLite
    with app.app_context():
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'instagram_accounts' in inspector.get_table_names():
                columns = [c['name'] for c in inspector.get_columns('instagram_accounts')]
                with db.engine.begin() as conn:
                    if 'access_token' not in columns:
                        conn.execute(db.text("ALTER TABLE instagram_accounts ADD COLUMN access_token VARCHAR(500)"))
                    if 'token_expires_at' not in columns:
                        conn.execute(db.text("ALTER TABLE instagram_accounts ADD COLUMN token_expires_at DATETIME"))
                    if 'last_synced_at' not in columns:
                        conn.execute(db.text("ALTER TABLE instagram_accounts ADD COLUMN last_synced_at DATETIME"))
        except Exception as e:
            app.logger.warning(f"Database auto-migration check warning: {e}")

    # Initialize Celery
    make_celery(app)

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.analytics import analytics_bp
    from app.routes.posts import posts_bp
    from app.routes.stories import stories_bp
    from app.routes.ai import ai_bp
    from app.routes.reports import reports_bp
    from app.routes.admin import admin_bp
    from app.routes.views import views_bp
    from app.routes.instagram import instagram_bp
    from app.routes.downloader import downloader_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(posts_bp)
    app.register_blueprint(stories_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(instagram_bp)
    app.register_blueprint(downloader_bp)

    # Context processor to inject user helper or checks if needed
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}

    # ── Health check ────────────────────────────────────────────────────────
    @app.route('/healthz')
    def healthz():
        from flask import jsonify
        from app.services import llm_service
        try:
            db.session.execute(db.text('SELECT 1'))
            db_ok = True
        except Exception:
            db_ok = False
        return jsonify({
            'status': 'ok' if db_ok else 'degraded',
            'database': db_ok,
            'ai_enabled': llm_service.is_enabled(),
        }), (200 if db_ok else 503)

    # ── JSON error handlers for the API ─────────────────────────────────────
    from flask import jsonify, request

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Resource not found'}), 404
        return e

    @app.errorhandler(405)
    def handle_405(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Method not allowed'}), 405
        return e

    @app.errorhandler(500)
    def handle_500(e):
        db.session.rollback()
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return e

    # ── Keep-alive ping endpoint ───────────────────────────────────
    @app.route('/ping')
    def ping():
        from flask import jsonify
        return jsonify({'status': 'alive'}), 200

    # ── Telegram Bot Webhook ───────────────────────────────────────
    # Bot ni webhook rejimida ishga tushiramiz (cold-start yo'q)
    if not app.testing:
        try:
            from telegram_bot import init_bot_webhook
            init_bot_webhook(app)
        except ImportError:
            app.logger.warning('telegram_bot moduli topilmadi, bot o\'chirilgan.')
        except Exception:
            app.logger.exception('Bot webhook ishga tushmadi.')

    return app
