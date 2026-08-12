from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

password_hasher = PasswordHasher()


def password_errors(password: str, username: str | None = None) -> list[str]:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Password must be at least 12 characters.")
    if len(password) > 1024:
        errors.append("Password is too long.")
    if username and username.lower() in password.lower():
        errors.append("Password must not contain the username.")
    if password.lower() in {"passwordpassword", "change-me-now", "billsonsforms"}:
        errors.append("Choose a less common password.")
    return errors


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False
