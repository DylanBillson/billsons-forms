import time

from app.db.session import SessionLocal
from app.services.retention import cleanup_expired_data
from app.core.config import settings


def main() -> None:
    while True:
        with SessionLocal() as db:
            cleanup_expired_data(db)
        time.sleep(settings.cleanup_interval_seconds)


if __name__ == "__main__":
    main()
