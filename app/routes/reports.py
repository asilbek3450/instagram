from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.report_service import ReportService
from app.models.analytics import Report
from app import db
import os

reports_bp = Blueprint('reports_api', __name__, url_prefix='/api/reports')

@reports_bp.route('', methods=['GET'])
@jwt_required()
def get_reports():
    user_id = int(get_jwt_identity())
    reps = ReportService.get_reports_by_user(user_id)
    return jsonify({'reports': [r.to_dict() for r in reps]}), 200


@reports_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_report():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    account_id = data.get('account_id')
    report_type = data.get('report_type', 'weekly')  # 'weekly', 'monthly', 'custom'

    if not account_id:
        return jsonify({'error': 'Instagram account ID is required'}), 400

    try:
        report = ReportService.create_report_request(user_id, account_id, report_type)
        
        # Trigger report generation.
        # We will attempt to trigger Celery task in a real setup.
        # For direct availability and fallback stability, we call it synchronously
        # or defer via Celery if configured.
        # To support both Docker/Celery and local run.py without Celery, 
        # we check config and run compilation:
        from flask import current_app
        use_celery = current_app.config.get('CELERY_BROKER_URL') is not None and os.environ.get('USE_CELERY', 'False') == 'True'
        
        if use_celery:
            # We import here to prevent circular loops
            from app.tasks import generate_report_task
            generate_report_task.delay(report.id)
            message = "Report generation has started in the background."
        else:
            # Fallback compile synchronously
            ReportService.generate_report_file(report.id)
            message = "Report generated successfully."

        # Fetch updated record
        updated_report = Report.query.get(report.id)
        return jsonify({
            'message': message,
            'report': updated_report.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f"Failed to queue report: {str(e)}"}), 500


@reports_bp.route('/download/<int:report_id>', methods=['GET'])
@jwt_required()
def download_report(report_id):
    user_id = int(get_jwt_identity())
    report = Report.query.filter_by(id=report_id, user_id=user_id).first()
    
    if not report:
        return jsonify({'error': 'Report not found'}), 404
        
    if report.status != 'COMPLETED' or not report.file_path:
        return jsonify({'error': 'Report is not ready yet'}), 400

    # Retrieve physical file path
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    full_path = os.path.join(base_dir, report.file_path.lstrip('/'))
    
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found on server'}), 404
        
    return send_file(full_path, as_attachment=True, download_name=os.path.basename(full_path))
