import os
import json
import unittest

from app import create_app, db
from app.security import encrypt_token, decrypt_token


class TokenEncryptionTestCase(unittest.TestCase):
    """Instagram tokens must be encrypted at rest and decrypt back cleanly."""

    def test_round_trip(self):
        enc = encrypt_token('IGQVJ_secret_token_123')
        self.assertNotEqual(enc, 'IGQVJ_secret_token_123')
        self.assertEqual(decrypt_token(enc), 'IGQVJ_secret_token_123')

    def test_legacy_plaintext_is_tolerated(self):
        # Values that aren't valid ciphertext (legacy plaintext) pass through.
        self.assertEqual(decrypt_token('legacy-plaintext-token'), 'legacy-plaintext-token')

    def test_empty_values(self):
        self.assertEqual(encrypt_token(''), '')
        self.assertIsNone(decrypt_token(None))


class AppInfraTestCase(unittest.TestCase):
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

    def test_healthz(self):
        res = self.client.get('/healthz')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['database'])
        self.assertIn('ai_enabled', data)

    def test_api_404_returns_json(self):
        res = self.client.get('/api/does-not-exist')
        self.assertEqual(res.status_code, 404)
        self.assertIn('error', json.loads(res.data))

    def test_jwt_refresh_flow(self):
        self.client.post('/api/auth/register', json={
            'email': 'refresh@example.com', 'password': 'testpassword'})
        # Login sets the refresh cookie on the test client's cookie jar.
        login = self.client.post('/api/auth/login', json={
            'email': 'refresh@example.com', 'password': 'testpassword'})
        self.assertEqual(login.status_code, 200)

        res = self.client.post('/api/auth/refresh')
        self.assertEqual(res.status_code, 200)
        self.assertIn('access_token', json.loads(res.data))


class AIFallbackTestCase(unittest.TestCase):
    """With no ANTHROPIC_API_KEY, AI helpers must fall back to heuristics."""

    def setUp(self):
        # Guarantee the LLM path is disabled for deterministic, free tests.
        self._saved_key = os.environ.pop('ANTHROPIC_API_KEY', None)
        from app.services import llm_service
        llm_service._client = None

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
        if self._saved_key is not None:
            os.environ['ANTHROPIC_API_KEY'] = self._saved_key

    def test_llm_disabled_without_key(self):
        from app.services import llm_service
        self.assertFalse(llm_service.is_enabled())
        self.assertIsNone(llm_service.generate_hashtags('tech'))
        self.assertIsNone(llm_service.generate_audience_insight({'a': 1}))

    def test_hashtag_fallback_returns_list(self):
        from app.services.ai_service import AIService
        tags = AIService.get_hashtag_suggestions('tech')
        self.assertIsInstance(tags, list)
        self.assertGreater(len(tags), 0)
        self.assertIn('hashtag', tags[0])

    def test_content_and_audience_fallback(self):
        from app.services.auth_service import AuthService
        from app.services.instagram_service import InstagramService
        from app.services.ai_service import AIService

        user = AuthService.register_user('aiuser@example.com', 'testpassword')
        account = InstagramService.connect_account(user.id, 'demo_creator', is_simulated=True)

        content = AIService.get_content_suggestions(account.id)
        self.assertIn('suggestions', content)
        self.assertGreater(len(content['suggestions']), 0)

        insight = AIService.get_audience_insights(account.id)
        self.assertIsInstance(insight, str)
        self.assertGreater(len(insight), 0)


if __name__ == '__main__':
    unittest.main()
