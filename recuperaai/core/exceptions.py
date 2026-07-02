class RecuperaAIError(Exception):
    """Erro base do sistema."""


class ValidationError(RecuperaAIError):
    """Dados inválidos informados por uma tela/ferramenta."""


class PermissionDenied(RecuperaAIError):
    """Usuário sem permissão."""


class ImportErrorRecoverable(RecuperaAIError):
    """Falha de importação tratável por arquivo."""
