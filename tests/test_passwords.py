import unittest
import tempfile

from recuperaai.bootstrap import create_engine
from recuperaai.security.passwords import hash_password, verify_password, validate_password_policy


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        stored = hash_password('Admin@12345')
        self.assertTrue(verify_password('Admin@12345', stored))
        self.assertFalse(verify_password('errada', stored))

    def test_policy(self):
        self.assertEqual(validate_password_policy('Admin@12345'), [])
        self.assertTrue(validate_password_policy('abc'))

    def test_initial_admin_requires_password_change_until_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()

            session = engine.auth.login('admin', 'Admin@12345')
            self.assertTrue(session.user.must_change_password)

            engine.auth.change_password(session, 'Admin@12345', 'NovaSenha@12345')
            session = engine.auth.login('admin', 'NovaSenha@12345')
            self.assertFalse(session.user.must_change_password)


if __name__ == '__main__':
    unittest.main()
