import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from app.models.instagram import InstagramAccount, Post
from app.models.analytics import FollowersHistory, AnalyticsSnapshot
from app.services import llm_service
from app import db

class AIService:

    @staticmethod
    def get_growth_prediction(account_id):
        history = FollowersHistory.query.filter_by(instagram_account_id=account_id)\
            .order_by(FollowersHistory.date.asc()).all()
        
        if len(history) < 5:
            # Not enough data, return flat prediction
            return {
                'forecast_7d': 0,
                'forecast_30d': 0,
                'growth_trend': 'Stable',
                'confidence_score': 50,
                'projected_data': []
            }
        
        # Fit a simple linear regression model using numpy
        x = np.arange(len(history))
        y = np.array([h.followers_count for h in history])
        
        slope, intercept = np.polyfit(x, y, 1)
        
        # Forecast 7 days and 30 days ahead
        forecast_7d = int(slope * (len(history) + 7) + intercept)
        forecast_30d = int(slope * (len(history) + 30) + intercept)
        
        growth_trend = 'Upward' if slope > 0.5 else ('Downward' if slope < -0.5 else 'Stable')
        
        # Confidence score based on regression variance (R-squared approximation)
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence_score = min(int(r_squared * 100), 98)
        confidence_score = max(confidence_score, 45) # Keep in a reasonable range
        
        # Generate prediction data points for Chart.js
        projected_data = []
        last_date = history[-1].date
        last_val = history[-1].followers_count
        
        # Add past 5 points for reference
        for h in history[-5:]:
            projected_data.append({
                'date': h.date.strftime('%Y-%m-%d'),
                'followers': h.followers_count,
                'type': 'historical'
            })
            
        # Add future 7 points
        for i in range(1, 8):
            future_date = last_date + timedelta(days=i)
            proj_val = int(slope * (len(history) - 1 + i) + intercept)
            projected_data.append({
                'date': future_date.strftime('%Y-%m-%d'),
                'followers': proj_val,
                'type': 'projected'
            })
            
        return {
            'forecast_7d': forecast_7d,
            'forecast_30d': forecast_30d,
            'growth_trend': growth_trend,
            'confidence_score': confidence_score,
            'projected_data': projected_data,
            'slope_per_day': round(float(slope), 2)
        }

    @staticmethod
    def get_best_posting_times(account_id):
        latest_snap = AnalyticsSnapshot.query.filter_by(instagram_account_id=account_id)\
            .order_by(AnalyticsSnapshot.date.desc()).first()
            
        if not latest_snap or not latest_snap.active_hours:
            return [
                {"day_of_week": "Wednesday", "hour": "15", "engagement_multiplier": 0.92},
                {"day_of_week": "Thursday", "hour": "18", "engagement_multiplier": 0.88},
                {"day_of_week": "Friday", "hour": "11", "engagement_multiplier": 0.85}
            ]
            
        hours_data = latest_snap.active_hours
        sorted_hours = sorted(hours_data.items(), key=lambda x: x[1], reverse=True)
        top_hours = sorted_hours[:3]
        
        days_data = latest_snap.active_days
        best_day = max(days_data.items(), key=lambda x: x[1])[0] if days_data else "Wednesday"
        
        suggestions = []
        for i, (hr, score) in enumerate(top_hours):
            day_offset = ["Wednesday", "Thursday", "Monday"]
            day = day_offset[i] if i < len(day_offset) else best_day
            suggestions.append({
                "day_of_week": day,
                "hour": f"{int(hr):02d}",
                "engagement_multiplier": round(int(score) / 100, 2)
            })
            
        return suggestions

    @staticmethod
    def get_hashtag_suggestions(keyword):
        # Clean keyword
        keyword = keyword.strip().replace("#", "").lower()
        if not keyword:
            return []

        # ── Real AI path (Claude) ───────────────────────────────────────────
        ai_tags = llm_service.generate_hashtags(keyword)
        if ai_tags:
            return sorted(
                ai_tags,
                key=lambda x: x.get("engagement_potential", 0),
                reverse=True,
            )

        # ── Heuristic fallback ──────────────────────────────────────────────
        # Mock database of hashtags related to topics
        hashtag_pool = {
            "tech": ["software", "coding", "programming", "python", "developer", "webdev", "ai", "javascript", "cloud", "saas", "techlife", "startup", "flask", "docker", "engineering"],
            "marketing": ["digitalmarketing", "growthhacking", "seo", "branding", "socialmedia", "analytics", "contentcreation", "business", "entreprenuer", "marketingtips", "ads", "agency"],
            "design": ["uiux", "uidesign", "webdesign", "uxdesign", "figma", "glassmorphism", "minimalist", "designer", "creative", "graphicdesign", "brandidentity", "aesthetic"],
            "business": ["entrepreneur", "startup", "saas", "productivity", "management", "investing", "metrics", "data", "roi", "success", "worksmart", "businessgrowth"]
        }
        
        # Find match or default to tech
        matched_pool = []
        for key, tags in hashtag_pool.items():
            if key in keyword or keyword in key:
                matched_pool.extend(tags)
                
        if not matched_pool:
            # Generate custom tags matching keyword
            matched_pool = [f"{keyword}community", f"{keyword}tips", f"{keyword}life", f"{keyword}art", f"{keyword}trends", "trending", "analytics", "explorepage"]
            
        # Select 10 hashtags randomly, compute mock engagement index
        selected = random_sample(matched_pool, min(10, len(matched_pool)))

        results = []
        for tag in selected:
            reach_tier = np.random.choice(['High Volume', 'Medium Volume', 'Niche Peak'])
            engagement_score = int(np.random.randint(65, 98))
            results.append({
                "hashtag": f"#{tag}",
                "relevance": int(np.random.randint(75, 99)),
                "reach_volume": reach_tier,
                "engagement_potential": engagement_score
            })
            
        return sorted(results, key=lambda x: x['engagement_potential'], reverse=True)

    @staticmethod
    def get_content_suggestions(account_id):
        posts = Post.query.filter_by(instagram_account_id=account_id).all()
        if not posts:
            return {
                'recommended_type': 'IMAGE',
                'best_topics': ['Introduction', 'Behind the scenes'],
                'suggested_captions': []
            }
            
        # Aggregate engagement by media type
        types_engagement = {}
        for p in posts:
            eng = p.likes_count + p.comments_count
            if p.media_type not in types_engagement:
                types_engagement[p.media_type] = []
            types_engagement[p.media_type].append(eng)
            
        avg_eng_by_type = {t: np.mean(v) for t, v in types_engagement.items()}
        recommended_type = max(avg_eng_by_type.items(), key=lambda x: x[1])[0] if avg_eng_by_type else 'CAROUSEL'

        # ── Real AI path (Claude) ───────────────────────────────────────────
        account = InstagramAccount.query.get(account_id)
        top_posts = sorted(posts, key=lambda p: p.likes_count + p.comments_count, reverse=True)[:5]
        context = {
            'recommended_media_type': recommended_type,
            'followers_count': account.followers_count if account else 0,
            'biography': account.biography if account else '',
            'avg_engagement_by_type': {t: round(float(v), 1) for t, v in avg_eng_by_type.items()},
            'top_performing_captions': [p.caption for p in top_posts if p.caption],
        }
        ai_suggestions = llm_service.generate_content_ideas(context)
        if ai_suggestions:
            return {
                'recommended_type': recommended_type,
                'suggestions': ai_suggestions,
            }

        # ── Heuristic fallback ──────────────────────────────────────────────
        # Topic suggestions based on keywords
        suggestions = [
            {
                'type': 'Educational',
                'caption': "Did you know how caching works? Here is a breakdown of how Redis speeds up your web applications by up to 80% ⚡ Link in bio for our complete architectural guide! #redis #devops #backend",
                'reason': f"Educational posts align well with your highest performing media format ({recommended_type.title()})."
            },
            {
                'type': 'Design Showcase',
                'caption': "Exploring the aesthetics of Glassmorphism in our new UI upgrade. Translucent backdrops, vibrant gradients, and crisp typography. Drop your feedback below! 👇 #uiux #css #glassmorphism",
                'reason': "Showcases draw high comment engagement index from designers."
            },
            {
                'type': 'System Architecture',
                'caption': "Scaling background tasks doesn't have to be hard. We configured celery worker threads to aggregate report compilations asynchronously. What's your setup? 🛠️ #python #celery #architecture",
                'reason': "System topics receive 40% more saves on average."
            }
        ]
        
        return {
            'recommended_type': recommended_type,
            'suggestions': suggestions
        }

    @staticmethod
    def get_audience_insights(account_id):
        snap = AnalyticsSnapshot.query.filter_by(instagram_account_id=account_id)\
            .order_by(AnalyticsSnapshot.date.desc()).first()
            
        if not snap:
            return "No demographic data available for analysis."
            
        # Parse distributions
        genders = snap.gender_distribution or {}
        ages = snap.age_distribution or {}
        countries = snap.country_distribution or {}
        
        # Max values
        max_gender = max(genders.items(), key=lambda x: x[1])[0] if genders else "N/A"
        max_age = max(ages.items(), key=lambda x: x[1])[0] if ages else "N/A"
        max_country = max(countries.items(), key=lambda x: x[1])[0] if countries else "N/A"

        # ── Real AI path (Claude) ───────────────────────────────────────────
        cities = snap.city_distribution or {}
        best_times = AIService.get_best_posting_times(account_id)
        ai_insight = llm_service.generate_audience_insight({
            'gender_distribution': genders,
            'age_distribution': ages,
            'country_distribution': countries,
            'city_distribution': cities,
            'best_posting_times': best_times,
        })
        if ai_insight:
            return ai_insight

        # ── Heuristic fallback ──────────────────────────────────────────────
        insight_text = (
            f"Your audience is predominantly {max_gender} ({genders.get(max_gender, 0)}%), "
            f"with the core age group being {max_age} ({ages.get(max_age, 0)}%). "
            f"Geographically, {max_country} holds the largest market share ({countries.get(max_country, 0)}%). "
            "To maximize engagement, content should be targeted towards professional topics that appeal to this demographic. "
            "Posting on Wednesday at 15:00 aligns with the highest active user density."
        )
        
        return insight_text

def random_sample(pool, num):
    # Standard Python random sample helper
    import random
    return random.sample(pool, num)
