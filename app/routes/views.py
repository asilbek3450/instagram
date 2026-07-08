from flask import Blueprint, render_template, request, make_response, redirect

views_bp = Blueprint('views', __name__)

@views_bp.route('/set_language/<lang>')
def set_language(lang):
    # Only allow supported languages
    if lang not in ['en', 'uz', 'ru']:
        lang = 'en'
    
    # Get the referer so we can redirect back to the page the user was on
    referer = request.referrer or '/'
    
    resp = make_response(redirect(referer))
    # Set cookie to expire in 1 year (approx 365 days)
    resp.set_cookie('lang', lang, max_age=60*60*24*365)
    return resp

@views_bp.route('/')
@views_bp.route('/landing')
def landing():
    return render_template('landing.html')

@views_bp.route('/login')
def login():
    return render_template('login.html')

@views_bp.route('/register')
def register():
    return render_template('register.html')

@views_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@views_bp.route('/followers')
def followers():
    return render_template('followers.html')

@views_bp.route('/posts')
def posts():
    return render_template('posts.html')

@views_bp.route('/stories')
def stories():
    return render_template('stories.html')

@views_bp.route('/comments')
def comments():
    return render_template('comments.html')

@views_bp.route('/ai-features')
def ai_features():
    return render_template('ai_features.html')

@views_bp.route('/reports')
def reports():
    return render_template('reports.html')

@views_bp.route('/profile')
def profile():
    return render_template('profile.html')

@views_bp.route('/admin')
def admin():
    return render_template('admin.html')

@views_bp.route('/downloader')
def downloader():
    # Public tool — works without an account/login
    return render_template('downloader.html')
