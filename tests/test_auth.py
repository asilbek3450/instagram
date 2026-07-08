import unittest
import json
from app import create_app, db
from app.models.user import User

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        self.app = create_app('config.Config')
        self.app.config['TESTING'] = True
        # Use an in-memory SQLite database for test runs
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_user_registration(self):
        # Register a new user
        response = self.client.post('/api/auth/register', json={
            'email': 'tester@example.com',
            'password': 'testpassword',
            'role': 'user'
        })
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], 'tester@example.com')

    def test_user_registration_duplicate(self):
        # Register first
        self.client.post('/api/auth/register', json={
            'email': 'tester@example.com',
            'password': 'testpassword'
        })
        # Register second time
        response = self.client.post('/api/auth/register', json={
            'email': 'tester@example.com',
            'password': 'testpassword2'
        })
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)

    def test_user_login(self):
        # Register
        self.client.post('/api/auth/register', json={
            'email': 'tester@example.com',
            'password': 'testpassword'
        })
        # Login
        response = self.client.post('/api/auth/login', json={
            'email': 'tester@example.com',
            'password': 'testpassword'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('access_token', data)
        self.assertIn('user', data)

    def test_user_login_invalid(self):
        # Try login non-existent user
        response = self.client.post('/api/auth/login', json={
            'email': 'nonexistent@example.com',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertIn('error', data)

if __name__ == '__main__':
    unittest.main()
