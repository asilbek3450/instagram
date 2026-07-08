from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.instagram_service import InstagramService
from app.services.analytics_service import AnalyticsService

posts_bp = Blueprint('posts_api', __name__, url_prefix='/api/posts')

@posts_bp.route('/<int:account_id>', methods=['GET'])
@jwt_required()
def posts(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AnalyticsService.get_post_analytics(account_id)
        return jsonify({'posts': data['all_posts'], 'analytics': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@posts_bp.route('/comments/<int:account_id>', methods=['GET'])
@jwt_required()
def comments(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AnalyticsService.get_comment_sentiment(account_id)
        return jsonify({'comments': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
