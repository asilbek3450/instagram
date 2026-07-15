from app import db
from app.models.instagram import Post, Story, Comment, InstagramAccount
from app.models.analytics import FollowersHistory, AnalyticsSnapshot
from sqlalchemy import func
from datetime import datetime, timedelta

class AnalyticsService:

    @staticmethod
    def get_dashboard_overview(account_id):
        account = InstagramAccount.query.get(account_id)
        if not account:
            raise ValueError("Account not found")

        # 1. Post metrics — single SQL aggregate instead of loading every row
        post_count, total_likes, total_comments, total_reach, total_impressions = (
            db.session.query(
                func.count(Post.id),
                func.coalesce(func.sum(Post.likes_count), 0),
                func.coalesce(func.sum(Post.comments_count), 0),
                func.coalesce(func.sum(Post.reach_count), 0),
                func.coalesce(func.sum(Post.impressions_count), 0),
            ).filter(Post.instagram_account_id == account_id).one()
        )

        # Engagement rate = average (likes + comments) / followers * 100
        avg_engagement = 0.0
        if post_count and account.followers_count > 0:
            total_engagements = total_likes + total_comments
            avg_engagement = round((total_engagements / post_count) / account.followers_count * 100, 2)

        # 2. Story views
        total_story_views = db.session.query(
            func.coalesce(func.sum(Story.views_count), 0)
        ).filter(Story.instagram_account_id == account_id).scalar()

        # 4. Growth percentage (30-day window)
        growth_30d = 0.0
        history_30d = FollowersHistory.query.filter_by(instagram_account_id=account_id)\
            .order_by(FollowersHistory.date.asc()).all()
        
        if len(history_30d) >= 2:
            first_val = history_30d[0].followers_count
            last_val = history_30d[-1].followers_count
            if first_val > 0:
                growth_30d = round(((last_val - first_val) / first_val) * 100, 2)

        return {
            'username': account.username,
            'followers_count': account.followers_count,
            'followers': account.followers_count,
            'following_count': account.following_count,
            'posts_count': account.posts_count,
            'total_likes': total_likes,
            'total_comments': total_comments,
            'total_story_views': total_story_views,
            'engagement_rate': avg_engagement,
            'reach': total_reach,
            'impressions': total_impressions,
            'growth_percentage': growth_30d,
            'followers_change': growth_30d,
            'biography': account.biography,
            'profile_picture_url': account.profile_picture_url,
            'full_name': account.full_name
        }

    @staticmethod
    def get_growth_data(account_id, days=30):
        start_date = datetime.utcnow().date() - timedelta(days=days)
        history = FollowersHistory.query.filter(
            FollowersHistory.instagram_account_id == account_id,
            FollowersHistory.date >= start_date
        ).order_by(FollowersHistory.date.asc()).all()

        return [h.to_dict() for h in history[-days:]]

    @staticmethod
    def get_post_analytics(account_id):
        posts = Post.query.filter_by(instagram_account_id=account_id)\
            .order_by(Post.posted_at.desc()).all()

        # Sort posts for top stats
        top_liked = sorted(posts, key=lambda p: p.likes_count, reverse=True)[:5]
        top_commented = sorted(posts, key=lambda p: p.comments_count, reverse=True)[:5]

        # Hashtag analysis
        hashtag_stats = {}
        for p in posts:
            # Real accounts can have posts with no caption (NULL in DB)
            words = (p.caption or '').split()
            tags = [w.strip("#").lower() for w in words if w.startswith("#")]
            for tag in tags:
                if tag not in hashtag_stats:
                    hashtag_stats[tag] = {
                        'count': 0,
                        'likes': 0,
                        'comments': 0
                    }
                hashtag_stats[tag]['count'] += 1
                hashtag_stats[tag]['likes'] += p.likes_count
                hashtag_stats[tag]['comments'] += p.comments_count

        # Compute average engagement per hashtag
        processed_hashtags = []
        for tag, stats in hashtag_stats.items():
            avg_likes = stats['likes'] / stats['count']
            avg_comments = stats['comments'] / stats['count']
            processed_hashtags.append({
                'tag': tag,
                'use_count': stats['count'],
                'avg_likes': round(avg_likes, 1),
                'avg_comments': round(avg_comments, 1),
                'engagement_index': round(avg_likes + avg_comments, 1)
            })

        # Sort by engagement
        processed_hashtags = sorted(processed_hashtags, key=lambda x: x['engagement_index'], reverse=True)

        return {
            'all_posts': [p.to_dict() for p in posts],
            'top_liked_posts': [p.to_dict() for p in top_liked],
            'top_commented_posts': [p.to_dict() for p in top_commented],
            'hashtags': processed_hashtags[:15]
        }

    @staticmethod
    def get_story_analytics(account_id):
        stories = Story.query.filter_by(instagram_account_id=account_id)\
            .order_by(Story.posted_at.desc()).all()
        return [s.to_dict() for s in stories]

    @staticmethod
    def get_audience_analytics(account_id):
        account = InstagramAccount.query.get(account_id)
        latest_snap = AnalyticsSnapshot.query.filter_by(instagram_account_id=account_id)\
            .order_by(AnalyticsSnapshot.date.desc()).first()

        # ── Follower gain/loss stats ─────────────────────────────────────
        history = FollowersHistory.query.filter_by(instagram_account_id=account_id)\
            .order_by(FollowersHistory.date.desc()).limit(30).all()

        daily_change = net_7d = net_30d = 0
        if history:
            daily_change = history[0].gain_loss
            net_7d = sum(h.gain_loss for h in history[:7])
            net_30d = sum(h.gain_loss for h in history)

        # ── Demographics from snapshot ───────────────────────────────────
        if not latest_snap:
            base = {
                'gender_distribution': {},
                'age_distribution': {},
                'country_distribution': {},
                'city_distribution': {},
                'active_hours': {},
                'active_days': {},
            }
        else:
            base = latest_snap.to_dict()

        # Aliases that followers.html currently uses
        base['gender_split'] = base.get('gender_distribution', {})
        base['age_groups'] = base.get('age_distribution', {})
        base['top_countries'] = base.get('country_distribution', {})
        base['top_cities'] = base.get('city_distribution', {})

        # Follower change stats
        base['followers_count'] = account.followers_count if account else 0
        base['following_count'] = account.following_count if account else 0
        base['daily_change'] = daily_change
        base['net_7d'] = net_7d
        base['net_30d'] = net_30d
        base['history'] = [h.to_dict() for h in reversed(history)]

        return base

    @staticmethod
    def get_comment_sentiment(account_id):
        # Join post comments for this account (newest first, so the returned
        # 30-item preview shows the latest activity)
        comments = Comment.query.join(Post)\
            .filter(Post.instagram_account_id == account_id)\
            .order_by(Comment.posted_at.desc()).all()
        
        pos_count = sum(1 for c in comments if c.sentiment == 'positive')
        neu_count = sum(1 for c in comments if c.sentiment == 'neutral')
        neg_count = sum(1 for c in comments if c.sentiment == 'negative')
        spam_count = sum(1 for c in comments if c.is_spam)

        # Find top commenters
        commenter_freq = {}
        for c in comments:
            commenter_freq[c.username] = commenter_freq.get(c.username, 0) + 1
        
        top_commenters = sorted(commenter_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        formatted_commenters = [{'username': item[0], 'count': item[1]} for item in top_commenters]

        return {
            'sentiment': {
                'positive': pos_count,
                'neutral': neu_count,
                'negative': neg_count
            },
            'spam_count': spam_count,
            'total_comments': len(comments),
            'top_commenters': formatted_commenters,
            'comments': [c.to_dict() for c in comments[:30]] # Return top 30 comments
        }
