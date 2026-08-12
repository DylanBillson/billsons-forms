from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.core.client_ip import get_client_ip


def create_audit_log(
    db: Session,
    *,
    action: str,
    user: User | None = None,
    username: str | None = None,
    request: Request | None = None,
    details: str | None = None,
) -> None:
    ip_address = None

    if request:
        ip_address = get_client_ip(request)

    audit_log = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else username,
        action=action,
        details=details,
        ip_address=ip_address,
    )

    db.add(audit_log)
