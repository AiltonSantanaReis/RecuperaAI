import json
import tempfile
import unittest
from pathlib import Path

from recuperaai.bootstrap import create_engine


class ConfigSecurityTests(unittest.TestCase):
    def test_api_token_is_encrypted_on_disk_and_loaded_in_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')

            cfg = engine.tool('settings').update_api(session, True, 'https://api.exemplo.local', 'segredo-super-secreto')
            self.assertEqual(cfg.api_token, 'segredo-super-secreto')

            raw_text = engine.paths.config.read_text(encoding='utf-8')
            self.assertNotIn('segredo-super-secreto', raw_text)
            data = json.loads(raw_text)
            self.assertIn('api_token_encrypted', data)
            self.assertNotIn('api_token', data)

            reloaded = create_engine(tmp)
            self.assertEqual(reloaded.config_store.config.api_token, 'segredo-super-secreto')

    def test_legacy_plain_token_is_migrated_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            engine.paths.config.write_text(json.dumps({
                'api_enabled': True,
                'api_base_url': 'https://api.exemplo.local',
                'api_token': 'token-legado'
            }), encoding='utf-8')

            reloaded = create_engine(tmp)
            self.assertEqual(reloaded.config_store.config.api_token, 'token-legado')
            reloaded.config_store.save()
            raw_text = reloaded.paths.config.read_text(encoding='utf-8')
            self.assertNotIn('token-legado', raw_text)
            self.assertIn('api_token_encrypted', json.loads(raw_text))


if __name__ == '__main__':
    unittest.main()
