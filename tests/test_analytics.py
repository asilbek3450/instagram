import unittest
import json
from app import create_app, db
from app.models.user import User

class AnalyticsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('config.Config')
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            
            # Setup a mock user and login to get JWT
            response = self.client.post('/api/auth/register', json={
                'email': 'tester@example.com',
                'password': 'testpassword',
                'role': 'user'
            })
            login_res = self.client.post('/api/auth/login', json={
                'email': 'tester@example.com',
                'password': 'testpassword'
            })
            login_data = json.loads(login_res.data)
            self.token = login_data['access_token']
            self.headers = {
                'Authorization': f'Bearer {self.token}'
            }

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_connect_instagram_account(self):
        # Connect simulated Instagram profile
        response = self.client.post('/api/analytics/accounts', json={
            'username': 'therock',
            'is_simulated': True
        }, headers=self.headers)
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertIn('account', data)
        self.assertEqual(data['account']['username'], 'therock')

    def test_fetch_account_overview_data(self):
        # Connect account first
        connect_res = self.client.post('/api/analytics/accounts', json={
            'username': 'therock',
            'is_simulated': True
        }, headers=self.headers)
        acc_data = json.loads(connect_res.data)
        account_id = acc_data['account']['id']
        
        # Get dashboard overview metrics
        response = self.client.get(f'/api/analytics/overview/{account_id}', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('overview', data)
        self.assertEqual(data['overview']['username'], 'therock')
        self.assertGreater(data['overview']['followers'], 0)

    def test_fetch_growth_data(self):
        connect_res = self.client.post('/api/analytics/accounts', json={
            'username': 'therock',
            'is_simulated': True
        }, headers=self.headers)
        acc_data = json.loads(connect_res.data)
        account_id = acc_data['account']['id']
        
        response = self.client.get(f'/api/analytics/growth/{account_id}?days=7', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('growth', data)
        self.assertEqual(len(data['growth']), 7)

if __name__ == '__main__':
    unittest.main()
