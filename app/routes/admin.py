from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import User
from app.models.instagram import InstagramAccount
from app.models.analytics import Report
from app import db
import sys
import os
import platform

admin_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')

def admin_required(fn):
    # A custom decorator helper inside admin route to verify admin privileges
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403
        return fn(*args, **kwargs)
    return wrapper

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def get_users():
    users = User.query.all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_user_role(user_id):
    data = request.get_json() or {}
    new_role = data.get('role')
    
    if new_role not in ['admin', 'user']:
        return jsonify({'error': 'Invalid role specify either admin or user'}), 400
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    user.role = new_role
    db.session.commit()
    return jsonify({
        'message': 'User role updated successfully',
        'user': user.to_dict()
    }), 200


@admin_bp.route('/system-status', methods=['GET'])
@jwt_required()
@admin_required
def system_status():
    # Return basic host details, python environment, and count stats
    total_users = User.query.count()
    total_accounts = InstagramAccount.query.count()
    total_reports = Report.query.count()
    
    status = {
        'platform': platform.system(),
        'platform_release': platform.release(),
        'python_version': sys.version,
        'database': 'PostgreSQL/SQLite via SQLAlchemy',
        'redis_status': 'Configured',
        'counts': {
            'users': total_users,
            'instagram_accounts': total_accounts,
            'reports': total_reports
        }
    }
    return jsonify({'status': status}), 200


@admin_bp.route('/logs', methods=['GET'])
@jwt_required()
@admin_required
def get_logs():
    # Simulated system audit logs for administrative overview
    mock_logs = [
        {"timestamp": "2026-06-23 09:10:02", "level": "INFO", "message": "Celery beat scheduled weekly report compilation."},
        {"timestamp": "2026-06-23 09:05:12", "level": "INFO", "message": "Database migration schema validated successfully."},
        {"timestamp": "2026-06-23 08:55:00", "level": "INFO", "message": "User login session initiated from IP 192.168.1.52."},
        {"timestamp": "2026-06-23 07:12:45", "level": "WARNING", "message": "Rate limit threshold approached on connection pool."},
        {"timestamp": "2026-06-23 06:00:00", "level": "INFO", "message": "Follower counts synchronized with meta simulator."}
    ]
    return jsonify({'logs': mock_logs}), 200
