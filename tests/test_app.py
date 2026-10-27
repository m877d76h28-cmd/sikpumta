"""Integration tests; run with: python -m unittest discover -s tests"""
import os
import tempfile
import unittest


class SikpumtaApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['DATABASE_PATH'] = os.path.join(cls.tmp.name, 'test.sqlite3')
        os.environ['SECRET_KEY'] = 'test-only-secret-key'
        from app import app
        cls.app = app
        cls.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()

    def test_register_state_roundtrip_and_login(self):
        r = self.client.post('/api/register', json={'email': 'student@example.com', 'password': 'strong-pass-123'})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json['is_new'])
        state = {'examRange': {'start': '2026-11-01', 'end': '2026-11-07'}, 'study': [{'m': 45, 't': 1}]}
        r = self.client.put('/api/state', json=state)
        self.assertEqual(r.status_code, 200)
        self.client.post('/api/logout')
        self.assertEqual(self.client.get('/api/state').status_code, 401)
        r = self.client.post('/api/login', json={'email': 'student@example.com', 'password': 'strong-pass-123'})
        self.assertEqual(r.status_code, 200)
        r = self.client.get('/api/state')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['state']['examRange']['start'], '2026-11-01')
        self.assertEqual(r.json['state']['examRange']['end'], '2026-11-07')

    def test_users_do_not_share_state(self):
        self.client.post('/api/register', json={'email': 'a@example.com', 'password': 'password-aaa'})
        self.client.put('/api/state', json={'secret': 'a-data'})
        self.client.post('/api/logout')
        self.client.post('/api/register', json={'email': 'b@example.com', 'password': 'password-bbb'})
        self.assertIsNone(self.client.get('/api/state').json['state'])

    def test_reject_short_password(self):
        r = self.client.post('/api/register', json={'email': 'bad@example.com', 'password': 'short'})
        self.assertEqual(r.status_code, 400)


if __name__ == '__main__':
    unittest.main()
