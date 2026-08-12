from sqlalchemy.orm import Session

from app.db.models.setting import Setting


def get_setting(
    db: Session,
    key: str,
    default: str | None = None,
) -> str | None:
    setting = (
        db.query(Setting)
        .filter(Setting.key == key)
        .first()
    )

    if not setting:
        return default

    return setting.value


def set_setting(
    db: Session,
    key: str,
    value: str,
) -> Setting:
    setting = (
        db.query(Setting)
        .filter(Setting.key == key)
        .first()
    )

    if setting:
        setting.value = value
        return setting

    setting = Setting(
        key=key,
        value=value,
    )

    db.add(setting)
    return setting


def get_settings_dict(
    db: Session,
) -> dict[str, str]:
    settings = db.query(Setting).all()

    return {
        setting.key: setting.value
        for setting in settings
    }


def ensure_setting(
    db: Session,
    key: str,
    default_value: str,
) -> Setting:
    setting = (
        db.query(Setting)
        .filter(Setting.key == key)
        .first()
    )

    if setting:
        return setting

    setting = Setting(
        key=key,
        value=default_value,
    )

    db.add(setting)

    return setting


def ensure_default_settings(
    db: Session,
) -> None:
    defaults = {
        "site_name": "Billson's Forms",
        "default_timezone": "Europe/London",
        "public_base_url": "https://test.billson.xyz",
        "delivery_log_retention_days": "365",
        "audit_log_retention_days": "730",
        "expired_session_retention_days": "30",
        "rate_limit_retention_hours": "0",
        "queue_terminal_retention_days": "7",
    }

    changed = False

    for key, value in defaults.items():
        existing = (
            db.query(Setting)
            .filter(Setting.key == key)
            .first()
        )

        if not existing:
            db.add(
                Setting(
                    key=key,
                    value=value,
                )
            )
            changed = True

    if changed:
        db.commit()
