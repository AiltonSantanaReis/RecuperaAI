from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from recuperaai.core.paths import AppPaths


class BackupService:
    """Gera backup local completo dos dados operacionais do RecuperaAI.

    O backup inclui banco/configuração e os arquivos guardados em storage
    (XML, PDF, documentos de cliente e relatórios). A própria pasta de backups
    é excluída para evitar recursão e crescimento desnecessário.
    """

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def create_backup(self) -> Path:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output = self.paths.backups / f'recuperaai_backup_{stamp}.zip'
        output.parent.mkdir(parents=True, exist_ok=True)

        backup_root = self.paths.backups.resolve()
        include_roots = [self.paths.data, self.paths.storage]

        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for root in include_roots:
                if not root.exists():
                    continue
                for path in root.rglob('*'):
                    resolved = path.resolve()
                    if resolved == output.resolve():
                        continue
                    if backup_root in resolved.parents or resolved == backup_root:
                        continue
                    if path.is_file():
                        zf.write(path, path.relative_to(self.paths.base))

        return output
