from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, unset_jwt_cookies,
    set_access_cookies, set_refresh_cookies, create_access_token,
)
from app.services.auth_service import AuthService
import re

auth_bp = Blueprint('auth_api', __name__, url_prefix='/api/auth')

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = 'user'  # Hardcode role to user for all registrations

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if not re.match(EMAIL_REGEX, email) and email != 'asilbek':
        return jsonify({'error': 'Invalid email address format'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long'}), 400

    try:
        user = AuthService.register_user(email, password, role=role)
        return jsonify({
            'message': 'Registration successful. Please login.',
            'user': user.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    try:
        login_res = AuthService.login_user(email, password)
        # Construct response
        resp = jsonify({
            'message': 'Login successful',
            'user': login_res['user'],
            'access_token': login_res['access_token']
        })
        
        # Optionally set cookie for browser clients
        set_access_cookies(resp, login_res['access_token'])
        set_refresh_cookies(resp, login_res['refresh_token'])
        return resp
    except ValueError as e:
        return jsonify({'error': str(e)}), 401


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Issue a new access token from a valid refresh token (cookie or header)."""
    user_id = get_jwt_identity()
    new_access_token = create_access_token(identity=user_id)
    resp = jsonify({'access_token': new_access_token})
    set_access_cookies(resp, new_access_token)
    return resp, 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    resp = jsonify({'message': 'Logout successful'})
    unset_jwt_cookies(resp)
    return resp, 200


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    # In production, send a secure email reset token. For simulation, return a mock URL.
    reset_url = f"http://localhost:5001/reset-password?token=mock_token_{int(datetime_utcnow().timestamp())}"
    return jsonify({
        'message': 'If the email exists, a password reset link has been dispatched.',
        'reset_link_dev': reset_url  # Left for demonstration/testing
    }), 200


@auth_bp.route('/verify-email', methods=['POST'])
@jwt_required()
def verify_email():
    user_id = int(get_jwt_identity())
    try:
        AuthService.verify_email(user_id)
        return jsonify({'message': 'Email verified successfully'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@auth_bp.route('/profile', methods=['GET', 'PUT'])
@jwt_required()
def profile():
    user_id = int(get_jwt_identity())
    
    if request.method == 'GET':
        try:
            prof = AuthService.get_user_profile(user_id)
            return jsonify({'user': prof}), 200
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
            
    elif request.method == 'PUT':
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if email and not re.match(EMAIL_REGEX, email) and email != 'asilbek':
            return jsonify({'error': 'Invalid email address format'}), 400
            
        try:
            prof = AuthService.update_profile(user_id, email, password if password else None)
            return jsonify({
                'message': 'Profile updated successfully',
                'user': prof
            }), 200
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

@auth_bp.route('/instagram/login')
@jwt_required(locations=['query_string', 'cookies', 'headers'])
def instagram_login():
    # This endpoint is opened in a popup via window.open(), which cannot send an
    # Authorization header. The frontend therefore passes the token as the `jwt`
    # query-string param; cookies/headers remain accepted as fallbacks.
    user_id = int(get_jwt_identity())
    from itsdangerous import URLSafeSerializer
    from flask import current_app, redirect
    
    s = URLSafeSerializer(current_app.config['SECRET_KEY'])
    state = s.dumps({'user_id': user_id})
    
    app_id = current_app.config.get('INSTAGRAM_APP_ID')
    redirect_uri = current_app.config.get('INSTAGRAM_REDIRECT_URI')
    
    # Scopes required:
    # - instagram_business_basic: profile info, media
    # - instagram_business_manage_insights: account + media insights
    # - instagram_business_manage_comments: read + reply to comments
    import urllib.parse
    redirect_uri_encoded = urllib.parse.quote(redirect_uri, safe='')
    
    # NOTE: "Instagram API with Instagram Login" (Business login) authorizes on
    # www.instagram.com — NOT api.instagram.com (the deprecated Basic Display
    # host). Using the wrong host silently breaks the real OAuth flow.
    instagram_auth_url = (
        f"https://www.instagram.com/oauth/authorize"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri_encoded}"
        f"&scope=instagram_business_basic,instagram_business_manage_insights,instagram_business_manage_comments"
        f"&response_type=code"
        f"&state={state}"
    )
    return redirect(instagram_auth_url)

@auth_bp.route('/instagram/callback')
def instagram_callback():
    code = request.args.get('code')
    state_str = request.args.get('state')
    
    from flask import current_app, render_template_string
    
    def popup_close_script(success=False, error_msg="", account_id="", sync_status=""):
        if success:
            return f"""
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'INSTAGRAM_AUTH_SUCCESS', sync: '{sync_status}', accountId: '{account_id}' }}, '*');
                    window.close();
                }} else {{
                    window.location.href = '/dashboard?ig_connected=1&sync={sync_status}';
                }}
            </script>
            """
        else:
            return f"""
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'INSTAGRAM_AUTH_ERROR', error: '{error_msg}' }}, '*');
                    window.close();
                }} else {{
                    window.location.href = '/dashboard?error={error_msg}';
                }}
            </script>
            """
    
    if not code:
        return popup_close_script(success=False, error_msg="auth_cancelled")
        
    from itsdangerous import URLSafeSerializer
    s = URLSafeSerializer(current_app.config['SECRET_KEY'])
    try:
        state_data = s.loads(state_str)
        user_id = state_data['user_id']
    except Exception:
        return popup_close_script(success=False, error_msg="invalid_state")
        
    import requests
    api_version = current_app.config.get('INSTAGRAM_API_VERSION', 'v23.0')
    graph_base = f"https://graph.instagram.com/{api_version}"

    # ── 1. Exchange the authorization code for a short-lived token ───────────
    token_url = "https://api.instagram.com/oauth/access_token"
    token_data = {
        'client_id': current_app.config.get('INSTAGRAM_APP_ID'),
        'client_secret': current_app.config.get('INSTAGRAM_APP_SECRET'),
        'redirect_uri': current_app.config.get('INSTAGRAM_REDIRECT_URI'),
        'code': code,
        'grant_type': 'authorization_code'
    }

    resp = requests.post(token_url, data=token_data, timeout=15)
    if resp.status_code != 200:
        # Surface the real Instagram error server-side so the developer can debug.
        current_app.logger.error(f"[Instagram] token exchange failed ({resp.status_code}): {resp.text[:500]}")
        return popup_close_script(success=False, error_msg="token_exchange_failed")

    res_json = resp.json()
    # Instagram Login returns a flat object, but some responses wrap the payload
    # in a "data" array — handle both shapes.
    if isinstance(res_json.get('data'), list) and res_json['data']:
        res_json = res_json['data'][0]
    short_token = res_json.get('access_token')
    if not short_token:
        current_app.logger.error(f"[Instagram] no access_token in token response: {res_json}")
        return popup_close_script(success=False, error_msg="token_exchange_failed")

    # ── 2. Exchange the short-lived token for a 60-day long-lived token ──────
    exchange_url = f"{graph_base}/access_token"
    exchange_params = {
        'grant_type': 'ig_exchange_token',
        'client_secret': current_app.config.get('INSTAGRAM_APP_SECRET'),
        'access_token': short_token
    }
    exchange_resp = requests.get(exchange_url, params=exchange_params, timeout=15)

    if exchange_resp.status_code == 200:
        ex_json = exchange_resp.json()
        long_token = ex_json.get('access_token', short_token)
        from datetime import datetime, timedelta
        expires_in = ex_json.get('expires_in', 5184000)
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    else:
        current_app.logger.warning(f"[Instagram] long-lived exchange failed ({exchange_resp.status_code}): {exchange_resp.text[:300]}")
        long_token = short_token
        token_expires_at = None

    # ── 3. Fetch the profile ────────────────────────────────────────────────
    profile_url = f"{graph_base}/me"
    profile_params = {
        'fields': 'id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url',
        'access_token': long_token
    }
    profile_resp = requests.get(profile_url, params=profile_params, timeout=15)
    if profile_resp.status_code != 200:
        current_app.logger.error(f"[Instagram] profile fetch failed ({profile_resp.status_code}): {profile_resp.text[:500]}")
        return popup_close_script(success=False, error_msg="profile_fetch_failed")
        
    profile_data = profile_resp.json()
    username = profile_data.get('username')
    
    from app.services.instagram_service import InstagramService
    account = InstagramService.save_real_account(
        user_id=user_id,
        username=username,
        full_name=profile_data.get('name'),
        biography=profile_data.get('biography'),
        followers_count=profile_data.get('followers_count', 0),
        following_count=profile_data.get('follows_count', 0),
        posts_count=profile_data.get('media_count', 0),
        profile_picture_url=profile_data.get('profile_picture_url'),
        access_token=long_token,
        token_expires_at=token_expires_at
    )
    
    try:
        InstagramService.sync_real_account_data(account.id)
        sync_status = 'synced'
    except Exception as e:
        print(f"Error during initial sync: {e}")
        sync_status = 'pending'

    from flask import make_response
    response = make_response(popup_close_script(success=True, account_id=str(account.id), sync_status=sync_status))
    response.set_cookie('last_connected_account_id', str(account.id), max_age=300)
    return response

def datetime_utcnow():
    from datetime import datetime
    return datetime.utcnow()
