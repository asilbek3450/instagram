"""
Tests for the real Instagram Graph API integration.

We can't hit the live API in CI (it needs a reviewed Meta app + real business
token), so we mock `requests.get` with representative Graph API payloads and
assert the sync logic populates the database correctly. We also verify the
OAuth authorize URL uses the correct host.
"""
import unittest
from unittest.mock import patch

from app import create_app, db
from app.security import encrypt_token
from app.models.instagram import InstagramAccount, Post, Story, Comment
from app.models.analytics import FollowersHistory, AnalyticsSnapshot
from app.services.auth_service import AuthService
from app.services.instagram_service import InstagramService


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def _demographics(breakdown):
    samples = {
        "age": [(["18-24"], 300), (["25-34"], 700)],
        "gender": [(["M"], 600), (["F"], 400)],
        "country": [(["UZ"], 800), (["RU"], 200)],
        "city": [(["Tashkent"], 500), (["Samarkand"], 100)],
    }
    results = [{"dimension_values": dv, "value": v} for dv, v in samples[breakdown]]
    return {"data": [{
        "name": "follower_demographics",
        "total_value": {"breakdowns": [{"dimension_keys": [breakdown], "results": results}]},
    }]}


def fake_get(url, params=None, timeout=None):
    params = params or {}
    if '/comments' in url:
        return FakeResp({"data": [
            {"id": "cmt_1", "text": "Wow this is great!", "username": "fan1",
             "timestamp": "2024-06-01T10:00:00+0000", "like_count": 4},
        ]})
    if url.endswith('/me/insights'):
        if params.get('breakdown'):
            return FakeResp(_demographics(params['breakdown']))
        if params.get('metric_type') == 'total_value':
            return FakeResp({"data": [
                {"name": "profile_views", "total_value": {"value": 250}},
                {"name": "accounts_engaged", "total_value": {"value": 400}},
            ]})
        return FakeResp({"data": [
            {"name": "reach", "period": "day", "values": [
                {"value": 900, "end_time": "2024-06-01T07:00:00+0000"},
                {"value": 1100, "end_time": "2024-06-02T07:00:00+0000"},
            ]},
            {"name": "follower_count", "period": "day", "values": [
                {"value": 10, "end_time": "2024-06-02T07:00:00+0000"},
            ]},
        ]})
    if url.endswith('/me/media'):
        return FakeResp({"data": [
            {"id": "media_1", "caption": "Launch day #saas #design", "like_count": 200,
             "comments_count": 1, "timestamp": "2024-06-01T09:00:00+0000",
             "media_type": "IMAGE", "media_url": "http://img/1", "permalink": "http://p/1"},
            {"id": "media_2", "caption": "Behind the scenes #dev", "like_count": 150,
             "comments_count": 0, "timestamp": "2024-05-28T09:00:00+0000",
             "media_type": "VIDEO", "media_url": "http://img/2", "permalink": "http://p/2"},
        ]})
    if url.endswith('/me/stories'):
        return FakeResp({"data": [
            {"id": "story_1", "media_type": "IMAGE", "media_url": "http://s/1",
             "timestamp": "2024-06-02T08:00:00+0000"},
        ]})
    if url.endswith('/me'):
        return FakeResp({
            "id": "123", "username": "realbiz", "name": "Real Biz",
            "biography": "We build things.", "followers_count": 5000,
            "follows_count": 300, "media_count": 2, "profile_picture_url": "http://pic",
        })
    if url.endswith('/insights'):
        if 'story_' in url:
            # v22+: taps/exits come from the `navigation` metric breakdown
            if params.get('metric') == 'navigation':
                results = [
                    {"dimension_values": ["tap_forward"], "value": 600},
                    {"dimension_values": ["tap_back"], "value": 90},
                    {"dimension_values": ["tap_exit"], "value": 40},
                ]
                return FakeResp({"data": [{
                    "name": "navigation",
                    "total_value": {"breakdowns": [{
                        "dimension_keys": ["story_navigation_action_type"],
                        "results": results,
                    }]},
                }]})
            return FakeResp({"data": [
                {"name": "views", "total_value": {"value": 1200}},
                {"name": "reach", "total_value": {"value": 1100}},
                {"name": "replies", "total_value": {"value": 8}},
                {"name": "shares", "total_value": {"value": 3}},
                {"name": "total_interactions", "total_value": {"value": 60}},
            ]})
        return FakeResp({"data": [
            {"name": "reach", "total_value": {"value": 1000}},
            {"name": "saved", "total_value": {"value": 20}},
            {"name": "shares", "total_value": {"value": 5}},
            {"name": "views", "total_value": {"value": 1500}},
            {"name": "total_interactions", "total_value": {"value": 300}},
        ]})
    return FakeResp({}, status=404)


class InstagramSyncTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('config.Config')
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _make_real_account(self):
        user = AuthService.register_user('biz@example.com', 'testpassword')
        account = InstagramAccount(
            user_id=user.id, username='realbiz', is_simulated=False,
            access_token=encrypt_token('FAKE_LONG_TOKEN'),
        )
        db.session.add(account)
        db.session.commit()
        return account

    @patch('app.services.instagram_service.requests.get', side_effect=fake_get)
    def test_full_sync_populates_db(self, _mock_get):
        account = self._make_real_account()
        ok = InstagramService.sync_real_account_data(account.id)
        self.assertTrue(ok)

        refreshed = InstagramAccount.query.get(account.id)
        self.assertEqual(refreshed.full_name, 'Real Biz')
        self.assertEqual(refreshed.followers_count, 5000)
        self.assertEqual(refreshed.posts_count, 2)
        self.assertIsNotNone(refreshed.last_synced_at)

        # Posts + per-media insights
        posts = Post.query.filter_by(instagram_account_id=account.id).all()
        self.assertEqual(len(posts), 2)
        p1 = Post.query.filter_by(media_id='media_1').first()
        self.assertEqual(p1.reach_count, 1000)
        self.assertEqual(p1.saved_count, 20)
        self.assertEqual(p1.share_count, 5)
        self.assertEqual(p1.impressions_count, 1500)  # 'views'

        # Comments + sentiment
        comment = Comment.query.filter_by(comment_id='cmt_1').first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.sentiment, 'positive')

        # Stories (navigation breakdown → taps/exits)
        story = Story.query.filter_by(media_id='story_1').first()
        self.assertIsNotNone(story)
        self.assertEqual(story.views_count, 1200)
        self.assertEqual(story.taps_forward, 600)
        self.assertEqual(story.taps_back, 90)
        self.assertEqual(story.exits_count, 40)

        # Followers history snapshot for today
        history = FollowersHistory.query.filter_by(instagram_account_id=account.id).all()
        self.assertTrue(any(h.followers_count == 5000 for h in history))

        # Account insights: a day snapshot with reach + today's aggregate + demographics
        snaps = AnalyticsSnapshot.query.filter_by(instagram_account_id=account.id).all()
        self.assertTrue(any(s.reach == 1100 for s in snaps))
        today_snap = max(snaps, key=lambda s: s.date)
        self.assertEqual(today_snap.profile_views, 250)
        self.assertEqual(today_snap.impressions, 400)
        self.assertTrue(today_snap.gender_distribution)
        self.assertIn('UZ', today_snap.country_distribution)


class InstagramOAuthUrlTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('config.Config')
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_login_redirects_to_correct_host(self):
        self.client.post('/api/auth/register', json={
            'email': 'oauth@example.com', 'password': 'testpassword'})
        login = self.client.post('/api/auth/login', json={
            'email': 'oauth@example.com', 'password': 'testpassword'})
        token = login.get_json()['access_token']

        res = self.client.get('/api/auth/instagram/login',
                              headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 302)
        location = res.headers['Location']
        # Must use the Instagram Login (Business) host, not the deprecated one.
        self.assertIn('www.instagram.com/oauth/authorize', location)
        self.assertNotIn('api.instagram.com', location)

    def test_login_accepts_jwt_query_string(self):
        # The popup window can't send an Authorization header, so the JWT must be
        # accepted via the `jwt` query-string param.
        self.client.post('/api/auth/register', json={
            'email': 'qs@example.com', 'password': 'testpassword'})
        login = self.client.post('/api/auth/login', json={
            'email': 'qs@example.com', 'password': 'testpassword'})
        token = login.get_json()['access_token']

        res = self.client.get(f'/api/auth/instagram/login?jwt={token}')
        self.assertEqual(res.status_code, 302)
        self.assertIn('www.instagram.com/oauth/authorize', res.headers['Location'])


if __name__ == '__main__':
    unittest.main()
