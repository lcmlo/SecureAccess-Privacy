import time
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models import AuditLog, AuthAttempt, DeletionRequest


def cleanup():
    def cutoff(days):
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    logs = db.session.execute(
        db.delete(AuditLog).where(
            AuditLog.event_timestamp < cutoff(current_app.config["LOG_RETENTION_DAYS"])
        )
    ).rowcount
    receipts = db.session.execute(
        db.delete(DeletionRequest).where(
            DeletionRequest.status == "concluído",
            DeletionRequest.completed_at < cutoff(current_app.config["RECEIPT_RETENTION_DAYS"]),
        )
    ).rowcount
    db.session.execute(db.delete(AuthAttempt).where(AuthAttempt.expires_at <= int(time.time())))
    db.session.commit()
    return logs, receipts
