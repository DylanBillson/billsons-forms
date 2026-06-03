from cryptography.fernet import Fernet

from app.core.config import settings


fernet = Fernet(settings.app_encryption_key.encode("utf-8"))


def encrypt_value(value: str | None) -> str | None:
    if not value:
        return None

    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str | None) -> str | None:
    if not value:
        return None

    return fernet.decrypt(value.encode("utf-8")).decode("utf-8")