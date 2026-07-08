from datetime import datetime
from app import db

class InstagramAccount(db.Model):
    __tablename__ = 'instagram_accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150))
    profile_picture_url = db.Column(db.String(500))
    biography = db.Column(db.Text)
    followers_count = db.Column(db.Integer, default=0)
    following_count = db.Column(db.Integer, default=0)
    posts_count = db.Column(db.Integer, default=0)
    is_simulated = db.Column(db.Boolean, default=True)
    access_token = db.Column(db.String(500), nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    posts = db.relationship('Post', backref='account', lazy=True, cascade='all, delete-orphan')
    stories = db.relationship('Story', backref='account', lazy=True, cascade='all, delete-orphan')
    followers_history = db.relationship('FollowersHistory', backref='account', lazy=True, cascade='all, delete-orphan')
    analytics_snapshots = db.relationship('AnalyticsSnapshot', backref='account', lazy=True, cascade='all, delete-orphan')
    reports = db.relationship('Report', backref='account', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'full_name': self.full_name,
            'profile_picture_url': self.profile_picture_url,
            'biography': self.biography,
            'followers_count': self.followers_count,
            'following_count': self.following_count,
            'posts_count': self.posts_count,
            'is_simulated': self.is_simulated,
            'connected_at': self.connected_at.isoformat(),
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
            'token_expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None
        }


class Post(db.Model):
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)
    instagram_account_id = db.Column(db.Integer, db.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    media_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    media_type = db.Column(db.String(30), default='IMAGE')  # 'IMAGE', 'VIDEO', 'CAROUSEL'
    caption = db.Column(db.Text)
    url = db.Column(db.String(500))
    likes_count = db.Column(db.Integer, default=0)
    comments_count = db.Column(db.Integer, default=0)
    saved_count = db.Column(db.Integer, default=0)
    share_count = db.Column(db.Integer, default=0)
    reach_count = db.Column(db.Integer, default=0)
    impressions_count = db.Column(db.Integer, default=0)
    posted_at = db.Column(db.DateTime, nullable=False)

    # Relationships
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        followers = self.account.followers_count if self.account else 0
        er = 0.0
        if followers > 0:
            er = round(((self.likes_count + self.comments_count) / followers) * 100, 2)
            
        return {
            'id': self.id,
            'instagram_account_id': self.instagram_account_id,
            'media_id': self.media_id,
            'media_type': self.media_type,
            'caption': self.caption,
            'url': self.url,
            'likes_count': self.likes_count,
            'comments_count': self.comments_count,
            'saved_count': self.saved_count,
            'share_count': self.share_count,
            'reach_count': self.reach_count,
            'impressions_count': self.impressions_count,
            'posted_at': self.posted_at.isoformat(),
            # Frontend compatibility aliases
            'likes': self.likes_count,
            'comments': self.comments_count,
            'saved': self.saved_count,
            'shares': self.share_count,
            'reach': self.reach_count,
            'impressions': self.impressions_count,
            'engagement_rate': er
        }


class Story(db.Model):
    __tablename__ = 'stories'

    id = db.Column(db.Integer, primary_key=True)
    instagram_account_id = db.Column(db.Integer, db.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    media_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    url = db.Column(db.String(500))
    views_count = db.Column(db.Integer, default=0)
    completion_rate = db.Column(db.Float, default=0.0)  # percentage (e.g. 85.5)
    replies_count = db.Column(db.Integer, default=0)
    exits_count = db.Column(db.Integer, default=0)
    taps_forward = db.Column(db.Integer, default=0)
    taps_back = db.Column(db.Integer, default=0)
    posted_at = db.Column(db.DateTime, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'instagram_account_id': self.instagram_account_id,
            'media_id': self.media_id,
            'url': self.url,
            'views_count': self.views_count,
            'completion_rate': self.completion_rate,
            'replies_count': self.replies_count,
            'exits_count': self.exits_count,
            'taps_forward': self.taps_forward,
            'taps_back': self.taps_back,
            'posted_at': self.posted_at.isoformat()
        }


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'), nullable=False, index=True)
    comment_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    username = db.Column(db.String(100), nullable=False)
    sentiment = db.Column(db.String(20), default='neutral')  # 'positive', 'neutral', 'negative'
    is_spam = db.Column(db.Boolean, default=False)
    posted_at = db.Column(db.DateTime, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'comment_id': self.comment_id,
            'text': self.text,
            'username': self.username,
            'sentiment': self.sentiment,
            'is_spam': self.is_spam,
            'posted_at': self.posted_at.isoformat()
        }
