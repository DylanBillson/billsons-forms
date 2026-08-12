from app.db.session import SessionLocal
from app.services.retention import cleanup_expired_data


def main() -> None:
    with SessionLocal() as db:
        result = cleanup_expired_data(db)
    print(
        f"cleanup complete: delivery_logs={result.delivery_logs} audit_logs={result.audit_logs} "
        f"sessions={result.sessions} rate_buckets={result.rate_buckets} queue_jobs={result.queue_jobs}"
    )


if __name__ == "__main__":
    main()
