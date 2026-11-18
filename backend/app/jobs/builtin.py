"""Handler có sẵn của hạ tầng – chỉ để kiểm tra hàng đợi hoạt động."""

from __future__ import annotations

import logging

from app.jobs import steps
from app.jobs.queue import Job
from app.jobs.registry import PermanentJobError, handler

logger = logging.getLogger(__name__)


@handler(steps.NOOP)
async def noop(job: Job) -> None:
    """payload: {"fail": "retry" | "permanent"} để giả lập lỗi."""
    mode = job.payload.get("fail")
    if mode == "permanent":
        raise PermanentJobError("noop: lỗi vĩnh viễn giả lập")
    if mode == "retry":
        raise RuntimeError("noop: lỗi tạm thời giả lập")
    logger.info("noop job done", extra={"payload": job.payload})
