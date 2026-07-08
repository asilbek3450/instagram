import os
import random
import requests
from datetime import datetime, timedelta, date
from app import db
from app.models.instagram import InstagramAccount, Post, Story, Comment
from app.models.analytics import FollowersHistory, AnalyticsSnapshot
from app.security import encrypt_token, decrypt_token


# ── Graph API base ───────────────────────────────────────────────────────────
# Pin the Graph API version so field/metric behaviour is stable. Override with
# the INSTAGRAM_API_VERSION env var if Instagram deprecates the default.
API_VERSION = os.environ.get('INSTAGRAM_API_VERSION', 'v23.0')
GRAPH = f"https://graph.instagram.com/{API_VERSION}"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ig_get(url, params, label="request"):
    """Safe GET against the Graph API with error logging."""
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[InstagramService] {label} failed ({resp.status_code}): {resp.text[:300]}")
            return None
    except Exception as exc:
        print(f"[InstagramService] {label} exception: {exc}")
        return None


def _parse_ts(raw):
    """Parse Instagram timestamp string to datetime (handles +00:00 suffix)."""
    if not raw:
        return datetime.utcnow()
    clean = raw.split('+')[0].split('Z')[0]
    try:
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return datetime.utcnow()


def _metric_value(entry):
    """
    Extract a scalar value from a Graph API insights metric entry, tolerating
    both response shapes: the newer `total_value` aggregate and the older
    `values` time-series list.
    """
    if entry.get("total_value") is not None:
        return entry["total_value"].get("value", 0) or 0
    values = entry.get("values")
    if values:
        return values[0].get("value", 0) or 0
    return 0


def _parse_insights_breakdown(data):
    """
    Parse any insights response that uses `total_value` + `breakdowns` (e.g.
    `follower_demographics`, story `navigation`) into {dimension_value: count}.
    Returns {} if absent.
    """
    out = {}
    if not data or "data" not in data:
        return out
    for item in data["data"]:
        total_value = item.get("total_value") or {}
        for breakdown in total_value.get("breakdowns", []):
            for result in breakdown.get("results", []):
                dims = result.get("dimension_values", [])
                if dims:
                    out[dims[0]] = result.get("value", 0)
    return out


# ── Main Service ──────────────────────────────────────────────────────────────

class InstagramService:

    # ── Account management ─────────────────────────────────────────────────

    @staticmethod
    def connect_account(user_id, username, is_simulated=True):
        existing = InstagramAccount.query.filter_by(username=username).first()
        if existing:
            raise ValueError(f"Instagram account '{username}' is already connected.")

        account = InstagramAccount(
            user_id=user_id,
            username=username,
            full_name=f"{username.replace('_', ' ').title()} | Analytics Pro",
            profile_picture_url="https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=150&h=150&fit=crop",
            biography="Digital creator. Testing modern tools and engineering analytics data frameworks.",
            followers_count=random.randint(12000, 85000) if is_simulated else 0,
            following_count=random.randint(400, 1200) if is_simulated else 0,
            posts_count=24 if is_simulated else 0,
            is_simulated=is_simulated
        )
        db.session.add(account)
        db.session.commit()

        if is_simulated:
            InstagramService._generate_simulated_data(account)

        return account

    @staticmethod
    def disconnect_account(user_id, account_id):
        account = InstagramAccount.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            raise ValueError("Account not found")
        db.session.delete(account)
        db.session.commit()
        return True

    @staticmethod
    def get_accounts(user_id):
        return InstagramAccount.query.filter_by(user_id=user_id).all()

    @staticmethod
    def get_account_details(user_id, account_id):
        account = InstagramAccount.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            raise ValueError("Account not found")
        return account

    # ── Real account helpers ────────────────────────────────────────────────

    @staticmethod
    def save_real_account(user_id, username, full_name, biography,
                          followers_count, following_count, posts_count,
                          profile_picture_url, access_token, token_expires_at=None):
        account = InstagramAccount.query.filter_by(username=username).first()
        if not account:
            account = InstagramAccount(user_id=user_id, username=username, is_simulated=False)
            db.session.add(account)

        account.full_name = full_name
        account.biography = biography
        account.followers_count = followers_count
        account.following_count = following_count
        account.posts_count = posts_count
        account.profile_picture_url = (
            profile_picture_url
            or "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=150&h=150&fit=crop"
        )
        account.access_token = encrypt_token(access_token)
        account.token_expires_at = token_expires_at
        account.is_simulated = False
        db.session.commit()
        return account

    @staticmethod
    def refresh_access_token(account_id):
        """
        Exchange the current long-lived token for a new one.
        Long-lived tokens can be refreshed as long as they are at least 24 h old
        and have not yet expired.
        Returns True on success, False on failure.
        """
        account = InstagramAccount.query.get(account_id)
        if not account or not account.access_token:
            return False

        data = _ig_get(
            "https://graph.instagram.com/refresh_access_token",
            {
                "grant_type": "ig_refresh_token",
                "access_token": decrypt_token(account.access_token),
            },
            label="token refresh",
        )
        if not data:
            return False

        new_token = data.get("access_token")
        expires_in = data.get("expires_in", 5184000)  # default 60 days
        if new_token:
            account.access_token = encrypt_token(new_token)
            account.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            db.session.commit()
            return True
        return False

    # ── Full sync from real API ─────────────────────────────────────────────

    @staticmethod
    def sync_real_account_data(account_id):
        account = InstagramAccount.query.get(account_id)
        if not account or account.is_simulated or not account.access_token:
            return False

        token = decrypt_token(account.access_token)

        # ── 1. Profile refresh ──────────────────────────────────────────────
        profile_data = _ig_get(
            f"{GRAPH}/me",
            {
                "fields": "id,name,biography,followers_count,follows_count,media_count,profile_picture_url",
                "access_token": token,
            },
            label="profile fetch",
        )
        if profile_data:
            account.full_name = profile_data.get("name", account.full_name)
            account.biography = profile_data.get("biography", account.biography)
            account.followers_count = profile_data.get("followers_count", account.followers_count)
            account.following_count = profile_data.get("follows_count", account.following_count)
            account.posts_count = profile_data.get("media_count", account.posts_count)
            if profile_data.get("profile_picture_url"):
                account.profile_picture_url = profile_data["profile_picture_url"]
            db.session.commit()

        # ── 2. Followers history (daily snapshot) ───────────────────────────
        today_date = date.today()
        history = FollowersHistory.query.filter_by(
            instagram_account_id=account.id, date=today_date
        ).first()
        if not history:
            yesterday_history = FollowersHistory.query.filter_by(
                instagram_account_id=account.id,
                date=today_date - timedelta(days=1),
            ).first()
            gain = 0
            if yesterday_history:
                gain = account.followers_count - yesterday_history.followers_count

            history = FollowersHistory(
                instagram_account_id=account.id,
                date=today_date,
                followers_count=account.followers_count,
                following_count=account.following_count,
                gain_loss=gain,
            )
            db.session.add(history)
            db.session.commit()
        else:
            # Update today's snapshot if it already exists (re-sync)
            gain = 0
            yesterday_history = FollowersHistory.query.filter_by(
                instagram_account_id=account.id,
                date=today_date - timedelta(days=1),
            ).first()
            if yesterday_history:
                gain = account.followers_count - yesterday_history.followers_count
            history.followers_count = account.followers_count
            history.following_count = account.following_count
            history.gain_loss = gain
            db.session.commit()

        # ── 3. Account-level insights (reach, profile_views per day) ────────
        InstagramService._sync_account_insights(account, token)

        # ── 4. Media (posts) + per-media insights + comments ────────────────
        InstagramService._sync_media(account, token)

        # ── 5. Stories ───────────────────────────────────────────────────────
        InstagramService._sync_stories(account, token)

        # ── 6. Mark sync timestamp ──────────────────────────────────────────
        account.last_synced_at = datetime.utcnow()
        db.session.commit()

        return True

    # ── Account-level insights ─────────────────────────────────────────────

    @staticmethod
    def _sync_account_insights(account, token):
        """
        Pulls daily account-level metrics for the past 30 days using the
        Instagram Business Insights API. Stores into AnalyticsSnapshot.
        """
        try:
            since = int((datetime.utcnow() - timedelta(days=30)).timestamp())
            until = int(datetime.utcnow().timestamp())

            # Day-level time series. `reach` and `follower_count` reliably return
            # a per-day `values` array; most other metrics now require
            # metric_type=total_value (handled by the aggregate call below).
            data = _ig_get(
                f"{GRAPH}/me/insights",
                {
                    "metric": "reach,follower_count",
                    "period": "day",
                    "since": since,
                    "until": until,
                    "access_token": token,
                },
                label="account insights",
            )

            metrics_map = {}
            if data and "data" in data:
                for metric_obj in data["data"]:
                    name = metric_obj.get("name")
                    metrics_map[name] = {
                        _parse_ts(v.get("end_time", "")).date(): v.get("value", 0)
                        for v in metric_obj.get("values", [])
                    }

            # Aggregate-only metrics (require metric_type=total_value). These
            # return a single total rather than a daily series, so they are
            # applied to today's snapshot.
            agg = _ig_get(
                f"{GRAPH}/me/insights",
                {
                    "metric": "profile_views,accounts_engaged",
                    "period": "day",
                    "metric_type": "total_value",
                    "access_token": token,
                },
                label="account insights (aggregate)",
            )
            agg_values = {}
            if agg and "data" in agg:
                for entry in agg["data"]:
                    agg_values[entry.get("name")] = _metric_value(entry)

            # Demographic breakdowns (separate calls per dimension).
            demographic_data = InstagramService._fetch_demographics(account, token)

            reach_map = metrics_map.get("reach", {})
            if not reach_map and not agg_values and not demographic_data:
                # Nothing usable came back — fall back to post-derived totals.
                InstagramService._build_snapshot_from_posts(account)
                return

            today = date.today()
            all_dates = set(reach_map.keys())
            all_dates.add(today)

            for snap_date in sorted(all_dates):
                snap = AnalyticsSnapshot.query.filter_by(
                    instagram_account_id=account.id, date=snap_date
                ).first()
                if not snap:
                    snap = AnalyticsSnapshot(instagram_account_id=account.id, date=snap_date)
                    db.session.add(snap)

                if snap_date in reach_map:
                    snap.reach = reach_map[snap_date]

                if snap_date == today:
                    snap.profile_views = agg_values.get("profile_views", snap.profile_views or 0)
                    snap.impressions = agg_values.get("accounts_engaged", snap.impressions or 0)

                if demographic_data:
                    snap.gender_distribution = demographic_data.get("gender_distribution", snap.gender_distribution)
                    snap.age_distribution = demographic_data.get("age_distribution", snap.age_distribution)
                    snap.country_distribution = demographic_data.get("country_distribution", snap.country_distribution)
                    snap.city_distribution = demographic_data.get("city_distribution", snap.city_distribution)

            db.session.commit()

        except Exception as exc:
            print(f"[InstagramService] Account insights error: {exc}")
            InstagramService._build_snapshot_from_posts(account)

    @staticmethod
    def _fetch_demographics(account, token):
        """
        Fetch audience demographics via the current `follower_demographics`
        metric (the legacy `audience_gender_age` / `audience_country` /
        `audience_city` lifetime metrics are deprecated). One call per breakdown
        dimension; returns percentages keyed for AnalyticsSnapshot JSON columns.
        """
        result = {}
        breakdowns = {
            "age": "age_distribution",
            "gender": "gender_distribution",
            "country": "country_distribution",
            "city": "city_distribution",
        }
        try:
            for breakdown, target_key in breakdowns.items():
                d = _ig_get(
                    f"{GRAPH}/me/insights",
                    {
                        "metric": "follower_demographics",
                        "period": "lifetime",
                        "metric_type": "total_value",
                        "breakdown": breakdown,
                        "access_token": token,
                    },
                    label=f"follower demographics ({breakdown})",
                )
                counts = _parse_insights_breakdown(d)
                if not counts:
                    continue

                total = sum(counts.values()) or 1
                if breakdown in ("country", "city"):
                    items = sorted(counts.items(), key=lambda x: -x[1])[:10]
                else:
                    items = sorted(counts.items())  # natural order for age/gender

                result[target_key] = {
                    k: round(v / total * 100, 1) for k, v in items
                }
        except Exception as exc:
            print(f"[InstagramService] Demographics error: {exc}")

        return result

    @staticmethod
    def _build_snapshot_from_posts(account):
        """Fallback: build today's snapshot from aggregated post metrics."""
        try:
            posts = Post.query.filter_by(instagram_account_id=account.id).all()
            total_reach = sum(p.reach_count for p in posts)
            total_views = sum(p.impressions_count for p in posts)

            snap = AnalyticsSnapshot.query.filter_by(
                instagram_account_id=account.id, date=date.today()
            ).first()
            if not snap:
                snap = AnalyticsSnapshot(instagram_account_id=account.id, date=date.today())
                db.session.add(snap)

            snap.reach = total_reach
            snap.impressions = total_views
            snap.profile_views = int(total_reach * 0.05)
            snap.website_clicks = int(total_reach * 0.01)

            # Defaults for real accounts (Uzbekistan-centric)
            if not snap.gender_distribution:
                snap.gender_distribution = {"M": 50.0, "F": 48.0, "U": 2.0}
            if not snap.age_distribution:
                snap.age_distribution = {"18-24": 30.0, "25-34": 42.0, "35-44": 18.0, "45-54": 7.0, "55+": 3.0}
            if not snap.country_distribution:
                snap.country_distribution = {"UZ": 65.0, "RU": 12.0, "US": 10.0, "KZ": 6.0, "Other": 7.0}
            if not snap.city_distribution:
                snap.city_distribution = {"Tashkent": 48.0, "Samarkand": 14.0, "Bukhara": 9.0, "Namangan": 8.0, "Other": 21.0}
            if not snap.active_hours:
                snap.active_hours = {str(h): round(50 + 40 * (1.0 if 9 <= h <= 21 else 0.2), 1) for h in range(24)}
            if not snap.active_days:
                snap.active_days = {"Monday": 80, "Tuesday": 85, "Wednesday": 90, "Thursday": 88, "Friday": 82, "Saturday": 65, "Sunday": 70}

            db.session.commit()
        except Exception as exc:
            print(f"[InstagramService] Snapshot fallback error: {exc}")

    # ── Media (posts) sync ─────────────────────────────────────────────────

    @staticmethod
    def _sync_media(account, token):
        """Fetch all media, their metrics, and comments from the Graph API."""
        try:
            media_data = _ig_get(
                f"{GRAPH}/me/media",
                {
                    "fields": "id,caption,like_count,comments_count,timestamp,media_type,media_url,permalink,thumbnail_url",
                    "limit": 50,
                    "access_token": token,
                },
                label="media list",
            )
            if not media_data:
                return

            media_list = media_data.get("data", [])

            # Handle pagination
            next_url = media_data.get("paging", {}).get("next")
            while next_url and len(media_list) < 200:
                paged = _ig_get(next_url, {}, label="media page")
                if not paged:
                    break
                media_list.extend(paged.get("data", []))
                next_url = paged.get("paging", {}).get("next")

            for m in media_list:
                InstagramService._upsert_post(account, token, m)

        except Exception as exc:
            print(f"[InstagramService] Media sync error: {exc}")

    @staticmethod
    def _upsert_post(account, token, m):
        """Create or update a Post record and fetch its insights + comments."""
        media_id = m.get("id")
        if not media_id:
            return

        media_type = m.get("media_type", "IMAGE")
        caption = m.get("caption", "")
        url = m.get("media_url") or m.get("thumbnail_url") or m.get("permalink", "")
        likes = m.get("like_count", 0)
        comments_count = m.get("comments_count", 0)
        posted_at = _parse_ts(m.get("timestamp"))

        # ── Fetch per-media insights ────────────────────────────────────────
        # Metric availability differs per media_product_type (FEED, REEL, STORY)
        # v22+: use 'views' instead of 'impressions'/'plays'
        reach_val = saved_val = share_val = views_val = total_interactions = 0

        # Primary metric set (works for most FEED + REELS in v22+)
        primary_metrics = "reach,saved,shares,views,total_interactions"
        ins_data = _ig_get(
            f"{GRAPH}/{media_id}/insights",
            {"metric": primary_metrics, "access_token": token},
            label=f"post insights {media_id}",
        )

        if ins_data and "data" in ins_data:
            for entry in ins_data["data"]:
                name = entry.get("name")
                val = _metric_value(entry)

                if name == "reach":
                    reach_val = val
                elif name == "saved":
                    saved_val = val
                elif name == "shares":
                    share_val = val
                elif name == "views":
                    views_val = val
                elif name == "total_interactions":
                    total_interactions = val
        else:
            # Fallback for older media or different product types
            fallback = _ig_get(
                f"{GRAPH}/{media_id}/insights",
                {"metric": "reach,saved", "access_token": token},
                label=f"post insights fallback {media_id}",
            )
            if fallback and "data" in fallback:
                for entry in fallback["data"]:
                    name = entry.get("name")
                    val = entry.get("values", [{}])[0].get("value", 0) if entry.get("values") else 0
                    if name == "reach":
                        reach_val = val
                    elif name == "saved":
                        saved_val = val

        # ── Upsert Post record ──────────────────────────────────────────────
        post = Post.query.filter_by(media_id=media_id).first()
        if not post:
            post = Post(
                instagram_account_id=account.id,
                media_id=media_id,
                media_type=media_type,
                posted_at=posted_at,
            )
            db.session.add(post)

        post.caption = caption or post.caption
        post.url = url or post.url
        post.media_type = media_type
        post.posted_at = posted_at
        post.likes_count = likes
        post.comments_count = comments_count
        post.reach_count = reach_val
        post.saved_count = saved_val
        post.share_count = share_val
        post.impressions_count = views_val if views_val > 0 else (int(reach_val * 1.3) if reach_val else 0)

        db.session.commit()

        # ── Fetch comments ──────────────────────────────────────────────────
        InstagramService._sync_post_comments(post, token)

    @staticmethod
    def _sync_post_comments(post, token):
        """Fetch and upsert comments for a single post."""
        try:
            c_data = _ig_get(
                f"{GRAPH}/{post.media_id}/comments",
                {
                    "fields": "id,text,username,timestamp,like_count,replies{id,text,username,timestamp}",
                    "access_token": token,
                },
                label=f"comments {post.media_id}",
            )
            if not c_data:
                return

            positive_kw = ["wow", "stunning", "great", "nice", "love", "beautiful", "super",
                           "omg", "best", "zo'r", "ajoyib", "gap yo'q", "klass", "класс", "красиво", "отлично",
                           "yaxshi", "super", "a'lo", "bravo", "perfect", "amazing", "excellent"]
            negative_kw = ["bad", "cluttered", "expensive", "error", "broken", "worst",
                           "yomon", "xato", "плохо", "ужасно", "дорого", "terrible", "horrible", "awful"]
            spam_kw = ["click link", "make money", "followers", "earn money", "boost profile", "dm us",
                       "free followers", "get rich", "casino", "crypto gains", "10k followers"]

            for c in c_data.get("data", []):
                c_id = c.get("id")
                c_text = c.get("text", "")
                c_username = c.get("username", "anonymous")
                c_time = _parse_ts(c.get("timestamp"))
                text_lower = c_text.lower()

                is_spam = any(kw in text_lower for kw in spam_kw)
                if is_spam:
                    sentiment = "neutral"
                elif any(kw in text_lower for kw in positive_kw):
                    sentiment = "positive"
                elif any(kw in text_lower for kw in negative_kw):
                    sentiment = "negative"
                else:
                    sentiment = "neutral"

                comment = Comment.query.filter_by(comment_id=c_id).first()
                if not comment:
                    comment = Comment(post_id=post.id, comment_id=c_id, posted_at=c_time)
                    db.session.add(comment)

                comment.text = c_text
                comment.username = c_username
                comment.sentiment = sentiment
                comment.is_spam = is_spam

            db.session.commit()
        except Exception as exc:
            print(f"[InstagramService] Comments sync error: {exc}")

    # ── Stories sync ───────────────────────────────────────────────────────

    @staticmethod
    def _sync_stories(account, token):
        """Fetch active stories and their metrics."""
        try:
            s_data = _ig_get(
                f"{GRAPH}/me/stories",
                {
                    "fields": "id,media_type,media_url,timestamp",
                    "access_token": token,
                },
                label="stories list",
            )
            if not s_data or "data" not in s_data:
                return

            for s in s_data["data"]:
                story_id = s.get("id")
                if not story_id:
                    continue

                url = s.get("media_url", "")
                posted_at = _parse_ts(s.get("timestamp"))

                # Fetch story insights. v22+ removed `taps_forward`, `taps_back`
                # and `exits` as standalone metrics — requesting them fails the
                # whole call. They now come from `navigation` with a breakdown.
                si = _ig_get(
                    f"{GRAPH}/{story_id}/insights",
                    {
                        "metric": "views,reach,replies,shares,total_interactions",
                        "access_token": token,
                    },
                    label=f"story insights {story_id}",
                )
                if not si or "data" not in si:
                    # Minimal metric set for older media / API versions
                    si = _ig_get(
                        f"{GRAPH}/{story_id}/insights",
                        {"metric": "reach,replies,views", "access_token": token},
                        label=f"story insights fallback {story_id}",
                    )

                views = replies = exits = taps_forward = taps_back = reach = 0
                if si and "data" in si:
                    for entry in si["data"]:
                        name = entry.get("name")
                        val = _metric_value(entry)

                        if name == "views":
                            views = val
                        elif name == "reach":
                            reach = val
                        elif name == "replies":
                            replies = val

                # Navigation breakdown → tap_forward / tap_back / tap_exit
                nav = _ig_get(
                    f"{GRAPH}/{story_id}/insights",
                    {
                        "metric": "navigation",
                        "breakdown": "story_navigation_action_type",
                        "access_token": token,
                    },
                    label=f"story navigation {story_id}",
                )
                nav_counts = {k.lower(): v for k, v in _parse_insights_breakdown(nav).items()}
                taps_forward = nav_counts.get("tap_forward", 0)
                taps_back = nav_counts.get("tap_back", 0)
                exits = nav_counts.get("tap_exit", 0) + nav_counts.get("swipe_forward", 0)

                completion = round((1 - (exits / max(views, 1))) * 100, 1) if views > 0 else 0.0

                story = Story.query.filter_by(media_id=story_id).first()
                if not story:
                    story = Story(
                        instagram_account_id=account.id,
                        media_id=story_id,
                        posted_at=posted_at,
                    )
                    db.session.add(story)

                story.url = url or story.url
                story.views_count = views or reach
                story.replies_count = replies
                story.exits_count = exits
                story.taps_forward = taps_forward
                story.taps_back = taps_back
                story.completion_rate = completion

            db.session.commit()
        except Exception as exc:
            print(f"[InstagramService] Stories sync error: {exc}")

    # ── Simulated data generation ──────────────────────────────────────────

    @staticmethod
    def _generate_simulated_data(account):
        start_date = date.today() - timedelta(days=30)
        current_followers = account.followers_count - 1200
        current_following = account.following_count

        history_records = []
        for i in range(31):
            record_date = start_date + timedelta(days=i)
            gain_loss = random.randint(-15, 120)
            current_followers += gain_loss
            current_following += random.randint(-2, 3)
            history_records.append(FollowersHistory(
                instagram_account_id=account.id,
                date=record_date,
                followers_count=current_followers,
                following_count=current_following,
                gain_loss=gain_loss,
            ))

        account.followers_count = current_followers
        account.following_count = current_following

        captions = [
            "Launching our brand new glassmorphism dashboard today! Check the link in bio #saas #design #uiux",
            "Consistency is key in design. What do you think of this color palette? #colors #aesthetic",
            "Weekend vibes. Working on coding backend systems #python #flask #webdev",
            "Behind the scenes of our analytics system development #engineering #systems",
            "Aesthetic grids and fluid layouts. Mobile-first design is not optional anymore #frontend #responsive",
            "Automating insights with Celery and Redis! Scaling background jobs #devops #redis",
            "What metrics do you track daily? Engagement, reach, or follow rate? Let's discuss! #metrics #marketing",
            "New office setup, ready for some serious product developments! #developer #setup #tech",
            "Building robust REST APIs. SQLAlchemy models look so elegant. #sqlalchemy #database",
            "Our user interface dark mode is now live! Smooth transitions and high contrast #css #darkmode",
            "Collaborating with standard APIs. The journey of fullstack engineering #productivity",
            "Analytics don't lie. Data drives development. #dataengineer #stats",
            "Monday motivation: Keep coding, keep scaling. #developer #programming",
            "How we achieved 99.9% uptime with Redis caching #caching #performance",
            "Simulating Instagram metrics with custom engines #simulation #python",
        ]

        post_records = []
        for i in range(15):
            days_ago = 29 - (i * 2)
            posted_at = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(1, 23))
            likes = random.randint(150, 1800)
            comments_count = random.randint(10, 80)
            saves = random.randint(5, 150)
            shares = random.randint(2, 60)
            reach = int(likes * random.uniform(2.5, 5.0))
            impressions = int(reach * random.uniform(1.1, 1.6))
            post_records.append(Post(
                instagram_account_id=account.id,
                media_id=f"media_post_{account.id}_{i}",
                media_type=random.choice(["IMAGE", "VIDEO", "CAROUSEL_ALBUM"]),
                caption=captions[i % len(captions)],
                url=f"https://images.unsplash.com/photo-{1600000000000 + i * 100000}?w=600&fit=crop",
                likes_count=likes,
                comments_count=comments_count,
                saved_count=saves,
                share_count=shares,
                reach_count=reach,
                impressions_count=impressions,
                posted_at=posted_at,
            ))

        db.session.add_all(history_records)
        db.session.add_all(post_records)
        db.session.commit()

        story_records = []
        for i in range(6):
            posted_at = datetime.utcnow() - timedelta(days=i, hours=random.randint(2, 10))
            views = random.randint(800, 4500)
            exits = random.randint(5, 80)
            story_records.append(Story(
                instagram_account_id=account.id,
                media_id=f"media_story_{account.id}_{i}",
                url=f"https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=400&h=800&fit=crop",
                views_count=views,
                completion_rate=round(random.uniform(70.0, 94.0), 2),
                replies_count=random.randint(1, 25),
                exits_count=exits,
                taps_forward=int(views * random.uniform(0.4, 0.7)),
                taps_back=int(views * random.uniform(0.05, 0.15)),
                posted_at=posted_at,
            ))

        comment_users = ["mike_codes", "design_guru", "lucy_seo", "alex_dev", "growth_hacker",
                         "cryptoprincess", "spam_bot_99", "serene_mind", "tech_junkie", "bella_visuals"]
        positive_comments = [
            "Wow, this looks absolutely stunning! Love the glassmorphic aesthetics.",
            "Incredible layout! Exactly what I was looking for.",
            "Keep up the amazing work! So clean and professional.",
            "This dark mode is everything. Super premium feel.",
            "Great tips, definitely saving this post for later reference!",
        ]
        neutral_comments = [
            "Nice post.", "What library did you use for the charts?",
            "Are you deploying this on AWS or Render?",
            "Interesting approach. How does it handle scale?",
        ]
        negative_comments = [
            "The text contrast on light mode seems slightly off.",
            "Not sure about this layout, feels a bit cluttered.",
        ]
        spam_comments = [
            "GET 10K FOLLOWERS INSTANTLY! Click link in bio!!!",
            "Earn $500/day working from home. Join us now!",
        ]

        comment_records = []
        for post in post_records:
            for j in range(min(post.comments_count, 12)):
                posted_at = post.posted_at + timedelta(minutes=random.randint(10, 300))
                user = random.choice(comment_users)
                choice = random.random()
                if choice < 0.45:
                    text, sentiment, is_spam = random.choice(positive_comments), "positive", False
                elif choice < 0.70:
                    text, sentiment, is_spam = random.choice(neutral_comments), "neutral", False
                elif choice < 0.85:
                    text, sentiment, is_spam = random.choice(negative_comments), "negative", False
                else:
                    text, sentiment, is_spam = random.choice(spam_comments), "neutral", True
                    user = random.choice(["spam_bot_99", "crypto_gainz", "reach_boost_expert"])

                comment_records.append(Comment(
                    post_id=post.id,
                    comment_id=f"comment_{post.id}_{j}",
                    text=text,
                    username=user,
                    sentiment=sentiment,
                    is_spam=is_spam,
                    posted_at=posted_at,
                ))

        snapshots = []
        for i in range(30):
            snap_date = start_date + timedelta(days=i)
            reach = random.randint(2000, 15000)
            impressions = int(reach * random.uniform(1.2, 1.7))
            snapshots.append(AnalyticsSnapshot(
                instagram_account_id=account.id,
                date=snap_date,
                reach=reach,
                impressions=impressions,
                profile_views=random.randint(150, 900),
                website_clicks=random.randint(10, 80),
                email_clicks=random.randint(2, 20),
                get_directions_clicks=random.randint(0, 5),
                gender_distribution={"male": 46.5, "female": 51.2, "other": 2.3},
                age_distribution={"13-17": 4.1, "18-24": 28.5, "25-34": 42.3, "35-44": 15.2, "45-54": 6.8, "55+": 3.1},
                country_distribution={"United States": 35.4, "United Kingdom": 12.1, "Germany": 9.3, "Canada": 8.5, "India": 7.2, "Others": 27.5},
                city_distribution={"New York": 10.5, "London": 8.1, "Berlin": 5.4, "Toronto": 4.8, "Mumbai": 3.5, "Others": 67.7},
                active_hours={str(h): round(random.uniform(5, 95) if 8 <= h <= 22 else random.uniform(1, 15), 1) for h in range(24)},
                active_days={"Monday": 78, "Tuesday": 82, "Wednesday": 85, "Thursday": 88, "Friday": 72, "Saturday": 60, "Sunday": 65},
            ))

        db.session.add_all(story_records)
        db.session.add_all(comment_records)
        db.session.add_all(snapshots)
        db.session.commit()
