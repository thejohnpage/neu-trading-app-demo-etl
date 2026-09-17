import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from config import settings
from pipeline import run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("trading-etl")


def safe_run():
    try:
        run_once()
    except Exception:
        log.exception("ETL run failed; watermark was not advanced")


if __name__ == "__main__":
    log.info("Starting trade warehouse ETL every %d seconds", settings.interval_seconds)
    safe_run()
    scheduler = BlockingScheduler()
    scheduler.add_job(safe_run, "interval", seconds=settings.interval_seconds, max_instances=1, coalesce=True)
    scheduler.start()
