import secrets
from hashlib import sha256


SESSION_TOKEN_LENGTH = 32


def generate_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_LENGTH)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    return secrets.compare_digest(
        hash_token(token),
        token_hash,
    )