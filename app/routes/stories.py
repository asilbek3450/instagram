from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.instagram_service import InstagramService
from app.services.analytics_service import AnalyticsService

stories_bp = Blueprint('stories_api', __name__, url_prefix='/api/stories')

@stories_bp.route('/<int:account_id>', methods=['GET'])
@jwt_required()
def stories(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AnalyticsService.get_story_analytics(account_id)
        return jsonify({'stories': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
