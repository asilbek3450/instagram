from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.instagram_service import InstagramService
from app.services.analytics_service import AnalyticsService

analytics_bp = Blueprint('analytics_api', __name__, url_prefix='/api/analytics')

@analytics_bp.route('/accounts', methods=['GET', 'POST'])
@jwt_required()
def accounts():
    user_id = int(get_jwt_identity())
    
    if request.method == 'GET':
        accs = InstagramService.get_accounts(user_id)
        return jsonify({'accounts': [a.to_dict() for a in accs]}), 200
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        username = data.get('username', '').strip().lower()
        is_simulated = data.get('is_simulated', True)
        
        if not username:
            return jsonify({'error': 'Instagram username is required'}), 400
            
        try:
            acc = InstagramService.connect_account(user_id, username, is_simulated=is_simulated)
            return jsonify({
                'message': f"Account @{username} connected successfully.",
                'account': acc.to_dict()
            }), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 400


@analytics_bp.route('/accounts/<int:account_id>', methods=['DELETE'])
@jwt_required()
def disconnect_account(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.disconnect_account(user_id, account_id)
        return jsonify({'message': 'Account disconnected successfully'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@analytics_bp.route('/overview/<int:account_id>', methods=['GET'])
@jwt_required()
def overview(account_id):
    user_id = int(get_jwt_identity())
    try:
        # Validate that user owns this account
        InstagramService.get_account_details(user_id, account_id)
        data = AnalyticsService.get_dashboard_overview(account_id)
        return jsonify({'overview': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@analytics_bp.route('/growth/<int:account_id>', methods=['GET'])
@jwt_required()
def growth(account_id):
    user_id = int(get_jwt_identity())
    days = request.args.get('days', default=30, type=int)
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AnalyticsService.get_growth_data(account_id, days=days)
        return jsonify({'growth': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@analytics_bp.route('/audience/<int:account_id>', methods=['GET'])
@jwt_required()
def audience(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AnalyticsService.get_audience_analytics(account_id)
        return jsonify({'audience': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
