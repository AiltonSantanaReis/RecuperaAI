from __future__ import annotations

import base64
import hashlib
import hmac
import os

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 240_000


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "$".join([
        ALGORITHM,
        str(ITERATIONS),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    ])


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def validate_password_policy(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 8:
        errors.append("mínimo de 8 caracteres")
    if not any(ch.isupper() for ch in password):
        errors.append("ao menos uma letra maiúscula")
    if not any(ch.islower() for ch in password):
        errors.append("ao menos uma letra minúscula")
    if not any(ch.isdigit() for ch in password):
        errors.append("ao menos um número")
    if not any(not ch.isalnum() for ch in password):
        errors.append("ao menos um caractere especial")
    return errors
