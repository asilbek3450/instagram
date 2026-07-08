from datetime import datetime
from app import db

class FollowersHistory(db.Model):
    __tablename__ = 'followers_history'
    __table_args__ = (
        db.Index('ix_followers_history_account_date', 'instagram_account_id', 'date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    instagram_account_id = db.Column(db.Integer, db.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    followers_count = db.Column(db.Integer, default=0)
    following_count = db.Column(db.Integer, default=0)
    gain_loss = db.Column(db.Integer, default=0)  # Follower change compared to previous record

    def to_dict(self):
        return {
            'id': self.id,
            'instagram_account_id': self.instagram_account_id,
            'date': self.date.strftime('%Y-%m-%d'),
            'followers_count': self.followers_count,
            'followers': self.followers_count,
            'following_count': self.following_count,
            'gain_loss': self.gain_loss
        }


class AnalyticsSnapshot(db.Model):
    __tablename__ = 'analytics_snapshots'
    __table_args__ = (
        db.Index('ix_analytics_snapshots_account_date', 'instagram_account_id', 'date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    instagram_account_id = db.Column(db.Integer, db.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    reach = db.Column(db.Integer, default=0)
    impressions = db.Column(db.Integer, default=0)
    profile_views = db.Column(db.Integer, default=0)
    website_clicks = db.Column(db.Integer, default=0)
    email_clicks = db.Column(db.Integer, default=0)
    get_directions_clicks = db.Column(db.Integer, default=0)
    gender_distribution = db.Column(db.JSON)  # e.g. {"male": 45, "female": 53, "other": 2}
    age_distribution = db.Column(db.JSON)     # e.g. {"18-24": 30, "25-34": 50, ...}
    country_distribution = db.Column(db.JSON) # e.g. {"USA": 40, "Germany": 15, ...}
    city_distribution = db.Column(db.JSON)    # e.g. {"New York": 10, "Berlin": 5, ...}
    active_hours = db.Column(db.JSON)          # e.g. {"0": 5, "1": 2, ..., "23": 8} hourly activity weights
    active_days = db.Column(db.JSON)           # e.g. {"Monday": 80, "Tuesday": 85, ...}

    def to_dict(self):
        return {
            'id': self.id,
            'instagram_account_id': self.instagram_account_id,
            'date': self.date.strftime('%Y-%m-%d'),
            'reach': self.reach,
            'impressions': self.impressions,
            'profile_views': self.profile_views,
            'website_clicks': self.website_clicks,
            'email_clicks': self.email_clicks,
            'get_directions_clicks': self.get_directions_clicks,
            'gender_distribution': self.gender_distribution,
            'age_distribution': self.age_distribution,
            'country_distribution': self.country_distribution,
            'city_distribution': self.city_distribution,
            'active_hours': self.active_hours,
            'active_days': self.active_days
        }


class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    instagram_account_id = db.Column(db.Integer, db.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    file_path = db.Column(db.String(500))  # Relative path or URL
    status = db.Column(db.String(30), default='PENDING')  # 'PENDING', 'COMPLETED', 'FAILED'
    report_type = db.Column(db.String(30), default='weekly')  # 'weekly', 'monthly', 'custom'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'instagram_account_id': self.instagram_account_id,
            'title': self.title,
            'file_path': self.file_path,
            'status': self.status,
            'report_type': self.report_type,
            'created_at': self.created_at.isoformat()
        }
