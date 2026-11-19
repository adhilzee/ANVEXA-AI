from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.database.session import SessionLocal
from backend.app.services.verification_engine.pipeline import run_verification_pipeline

logger = logging.getLogger(__name__)


def run_verification_job_task(document_id: UUID, user_id: UUID) -> None:
    """Execute verification pipeline as an asynchronous / worker task."""
    with SessionLocal() as db:
        try:
            logger.info("Worker task starting verification for doc %s", document_id)
            run_verification_pipeline(document_id=document_id, user_id=user_id, db=db)
            logger.info("Worker task finished verification for doc %s", document_id)
        except Exception as exc:
            logger.exception("Worker task verification failed for doc %s: %s", document_id, exc)
