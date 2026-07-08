from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.instagram_service import InstagramService
from app.services.ai_service import AIService

ai_bp = Blueprint('ai_api', __name__, url_prefix='/api/ai')

@ai_bp.route('/predictions/<int:account_id>', methods=['GET'])
@jwt_required()
def predictions(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AIService.get_growth_prediction(account_id)
        return jsonify({'predictions': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@ai_bp.route('/posting-times/<int:account_id>', methods=['GET'])
@jwt_required()
def posting_times(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AIService.get_best_posting_times(account_id)
        return jsonify({'times': data}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@ai_bp.route('/suggestions/<int:account_id>', methods=['GET'])
@jwt_required()
def content_suggestions(account_id):
    user_id = int(get_jwt_identity())
    try:
        InstagramService.get_account_details(user_id, account_id)
        data = AIService.get_content_suggestions(account_id)
        insights = AIService.get_audience_insights(account_id)
        return jsonify({
            'suggestions': data,
            'insights': insights
        }), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@ai_bp.route('/hashtags', methods=['POST'])
@jwt_required()
def hashtags():
    data = request.get_json() or {}
    keyword = data.get('keyword', '').strip()
    
    if not keyword:
        return jsonify({'error': 'Keyword is required'}), 400
        
    tags = AIService.get_hashtag_suggestions(keyword)
    return jsonify({'hashtags': tags}), 200
