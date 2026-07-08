import os
import csv
from datetime import datetime
from app import db
from app.models.analytics import Report, FollowersHistory, AnalyticsSnapshot
from app.models.instagram import InstagramAccount, Post
from app.services.analytics_service import AnalyticsService

class ReportService:

    @staticmethod
    def create_report_request(user_id, account_id, report_type):
        account = InstagramAccount.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            raise ValueError("Instagram account not found")

        report = Report(
            user_id=user_id,
            instagram_account_id=account_id,
            title=f"{account.username.upper()} - {report_type.title()} Analytics Report",
            status='PENDING',
            report_type=report_type
        )
        db.session.add(report)
        db.session.commit()

        return report

    @staticmethod
    def generate_report_file(report_id):
        report = Report.query.get(report_id)
        if not report:
            return False

        try:
            # Create reports directory if it doesn't exist
            # We'll save inside app/static/reports/
            base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
            reports_dir = os.path.join(base_dir, 'static', 'reports')
            os.makedirs(reports_dir, exist_ok=True)

            filename = f"report_{report.id}_{int(datetime.utcnow().timestamp())}.csv"
            file_path = os.path.join(reports_dir, filename)

            # Gather data
            overview = AnalyticsService.get_dashboard_overview(report.instagram_account_id)
            posts_data = AnalyticsService.get_post_analytics(report.instagram_account_id)
            growth_data = AnalyticsService.get_growth_data(report.instagram_account_id)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write Section 1: Overview
                writer.writerow(["INSTAGRAM ANALYTICS PRO REPORT"])
                writer.writerow(["Report Title", report.title])
                writer.writerow(["Generated At", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
                writer.writerow(["Username", overview['username']])
                writer.writerow(["Full Name", overview['full_name']])
                writer.writerow(["Followers", overview['followers_count']])
                writer.writerow(["Following", overview['following_count']])
                writer.writerow(["Total Posts", overview['posts_count']])
                writer.writerow(["Engagement Rate (%)", f"{overview['engagement_rate']}%"])
                writer.writerow(["Total Likes", overview['total_likes']])
                writer.writerow(["Total Comments", overview['total_comments']])
                writer.writerow(["Total Reach", overview['reach']])
                writer.writerow(["Total Impressions", overview['impressions']])
                writer.writerow([])

                # Write Section 2: Posts Performance
                writer.writerow(["POST PERFORMANCE INDEX"])
                writer.writerow(["Post ID", "Type", "Posted At", "Likes", "Comments", "Reach", "Impressions", "Saves", "Shares"])
                for p in posts_data['all_posts']:
                    writer.writerow([
                        p['media_id'],
                        p['media_type'],
                        p['posted_at'],
                        p['likes_count'],
                        p['comments_count'],
                        p['reach_count'],
                        p['impressions_count'],
                        p['saved_count'],
                        p['share_count']
                    ])
                writer.writerow([])

                # Write Section 3: Growth History
                writer.writerow(["FOLLOWER GROWTH RECORDS (Last 30 Days)"])
                writer.writerow(["Date", "Followers Count", "Gain/Loss"])
                for record in growth_data:
                    writer.writerow([
                        record['date'],
                        record['followers'],
                        record['gain_loss']
                    ])

            # Update report status
            report.file_path = f"/static/reports/{filename}"
            report.status = 'COMPLETED'
            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            report.status = 'FAILED'
            db.session.commit()
            print(f"Error compiling report: {str(e)}")
            return False

    @staticmethod
    def get_reports_by_user(user_id):
        return Report.query.filter_by(user_id=user_id).order_by(Report.created_at.desc()).all()
