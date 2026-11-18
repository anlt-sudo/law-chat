"""Vòng lặp worker: lấy job → chạy handler → DONE / retry / FAILED."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import job_id_var
from app.jobs import queue
from app.jobs.registry import PermanentJobError, get_handler, registered_steps

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        steps: Sequence[str] | None = None,
        poll_interval_s: float = 1.0,
    ) -> None:
        self.engine = engine
        # Chỉ nhận các bước có handler trong process này (vd worker-ocr chỉ nhận normalize)
        self.steps = list(steps) if steps else registered_steps()
        self.poll_interval_s = poll_interval_s

    async def run_once(self) -> bool:
        """Xử lý tối đa một job. Trả True nếu đã lấy được job."""
        async with self.engine.begin() as conn:
            job = await queue.claim_next(conn, self.steps)
        if job is None:
            return False

        token = job_id_var.set(str(job.id))
        try:
            fn = get_handler(job.step)
            try:
                if fn is None:
                    raise PermanentJobError(f"Không có handler cho bước {job.step!r}")
                await fn(job)
            except asyncio.CancelledError:
                # Dừng giữa chừng: trả job về hàng đợi để worker sau chạy lại
                async with self.engine.begin() as conn:
                    await queue.fail(conn, job, "Worker dừng khi đang chạy job")
                raise
            except Exception as exc:
                permanent = isinstance(exc, PermanentJobError)
                async with self.engine.begin() as conn:
                    status = await queue.fail(
                        conn, job, f"{type(exc).__name__}: {exc}", permanent=permanent
                    )
                log = logger.error if status == "FAILED" else logger.warning
                log(
                    "Job lỗi",
                    extra={"step": job.step, "attempts": job.attempts, "status": status},
                    exc_info=exc,
                )
            else:
                async with self.engine.begin() as conn:
                    await queue.complete(conn, job.id)
                logger.info("Job xong", extra={"step": job.step, "attempts": job.attempts})
        finally:
            job_id_var.reset(token)
        return True

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("Worker bắt đầu", extra={"steps": self.steps})
        while not stop.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                # Lỗi hạ tầng (mất kết nối DB…): chờ rồi thử lại, không thoát worker
                logger.exception("Lỗi vòng lặp worker")
                processed = False
            if not processed:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_interval_s)
        logger.info("Worker dừng")
