import asyncio

from app.core.config import settings
from app.services.worker import run_worker


if __name__ == "__main__":
    asyncio.run(run_worker(settings.queue_poll_seconds))
