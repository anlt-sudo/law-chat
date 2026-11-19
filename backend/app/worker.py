"""Entrypoint worker: `python -m app.worker`."""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.pg import dispose_engine, get_engine
from app.jobs import queue
from app.jobs.worker import Worker
from app.llm import close_gateway

logger = logging.getLogger("app.worker")


def _register_handlers() -> None:
    """Import các module có @handler để đăng ký. Module sau thêm vào đây."""
    import app.jobs.builtin  # noqa: F401


async def _main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    _register_handlers()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    engine = get_engine()
    async with engine.begin() as conn:
        recovered = await queue.recover_stale(conn, settings.job_stale_minutes)
    if recovered:
        logger.warning("Hồi phục job RUNNING quá hạn", extra={"count": recovered})

    try:
        await Worker(engine, poll_interval_s=settings.worker_poll_interval_s).run(stop)
    finally:
        await close_gateway()
        await dispose_engine()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
