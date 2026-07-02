import tempfile
import unittest
import zipfile
from pathlib import Path

from recuperaai.bootstrap import create_engine


class BackupServiceTests(unittest.TestCase):
    def test_backup_includes_data_and_storage_but_not_existing_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            (engine.paths.imports / "1").mkdir(parents=True, exist_ok=True)
            (engine.paths.imports / "1" / "nota.xml").write_text("<xml/>", encoding="utf-8")
            engine.paths.backups.mkdir(parents=True, exist_ok=True)
            (engine.paths.backups / "old_backup.zip").write_text("old", encoding="utf-8")

            backup = engine.backups.create_backup()

            with zipfile.ZipFile(backup) as zf:
                names = set(zf.namelist())
            self.assertIn("data/recuperaai.sqlite3", names)
            self.assertIn("storage/imports/1/nota.xml", names)
            self.assertNotIn("storage/backups/old_backup.zip", names)


if __name__ == '__main__':
    unittest.main()
