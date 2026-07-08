"""
Instagram-specific API routes:
  POST /api/instagram/sync/<account_id>    — manually trigger full data sync
  POST /api/instagram/refresh/<account_id> — refresh long-lived access token
  GET  /api/instagram/status/<account_id>  — token expiry, last sync, account type
"""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.instagram_service import InstagramService
from app.models.instagram import InstagramAccount
from datetime import datetime

instagram_bp = Blueprint('instagram_api', __name__, url_prefix='/api/instagram')


@instagram_bp.route('/sync/<int:account_id>', methods=['POST'])
@jwt_required()
def sync(account_id):
    user_id = int(get_jwt_identity())
    try:
        account = InstagramService.get_account_details(user_id, account_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 403

    if account.is_simulated:
        return jsonify({'error': 'Simulated accounts cannot be synced from the real API.'}), 400

    if not account.access_token:
        return jsonify({'error': 'No access token stored. Please reconnect your account via OAuth.'}), 400

    # Check token expiry
    if account.token_expires_at and account.token_expires_at < datetime.utcnow():
        return jsonify({'error': 'Access token has expired. Please reconnect your Instagram account.'}), 401

    ok = InstagramService.sync_real_account_data(account_id)
    if ok:
        # Re-fetch to get updated last_synced_at
        account = InstagramAccount.query.get(account_id)
        return jsonify({
            'message': 'Sync completed successfully.',
            'last_synced_at': account.last_synced_at.isoformat() if account.last_synced_at else None,
            'account': account.to_dict()
        }), 200
    else:
        return jsonify({'error': 'Sync failed. Check server logs for details.'}), 500


@instagram_bp.route('/refresh/<int:account_id>', methods=['POST'])
@jwt_required()
def refresh_token(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 403

    ok = InstagramService.refresh_access_token(account_id)
    if ok:
        account = InstagramAccount.query.get(account_id)
        return jsonify({
            'message': 'Access token refreshed successfully.',
            'token_expires_at': account.token_expires_at.isoformat() if account.token_expires_at else None
        }), 200
    else:
        return jsonify({'error': 'Token refresh failed. Please reconnect your account.'}), 500


@instagram_bp.route('/status/<int:account_id>', methods=['GET'])
@jwt_required()
def status(account_id):
    user_id = int(get_jwt_identity())
    try:
        account = InstagramService.get_account_details(user_id, account_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 403

    token_ok = True
    token_message = "Token is valid"
    days_until_expiry = None

    if account.token_expires_at:
        delta = account.token_expires_at - datetime.utcnow()
        days_until_expiry = delta.days
        if delta.total_seconds() <= 0:
            token_ok = False
            token_message = "Token has expired. Please reconnect."
        elif delta.days < 7:
            token_message = f"Token expires soon ({delta.days} days left). Consider refreshing."

    return jsonify({
        'account_id': account_id,
        'username': account.username,
        'is_simulated': account.is_simulated,
        'token_ok': token_ok,
        'token_message': token_message,
        'days_until_expiry': days_until_expiry,
        'last_synced_at': account.last_synced_at.isoformat() if account.last_synced_at else None,
        'token_expires_at': account.token_expires_at.isoformat() if account.token_expires_at else None,
    }), 200
