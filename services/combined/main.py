"""Single combined Render service: runs the MCP HTTP server and the
ingestion + wiki_writer schedulers in one process, sharing one disk.

Why combined: Render disks are 1:1 with a single service, but ingestion,
wiki_writer, and mcp_server all need to read/write the same vault/, raw/,
and state.db. Rather than introduce object storage or a managed DB (more
moving parts than a single-user system needs), all three run here as
in-process components on one shared disk. See MANUAL_SETUP.md Section 5 for
the reasoning.

ingestion and wiki_writer keep their own bounded-batch + lock discipline
(see SPEC.md Section 7) exactly as when run standalone -- this wrapper only
adds the scheduling loop and error isolation so one component's exception
never takes down the HTTP server.
"""
import logging
import os
import sys
from pathlib import Path

SERVICES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICES_DIR))

from apscheduler.schedulers.background import BackgroundScheduler

from common.paths import bootstrap_git_repo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("combined")

# Must run before mcp_server/ingestion/wiki_writer touch the disk -- ensures
# DATA_ROOT is a real git working tree before the HTTP server starts serving
# vault/raw reads or the scheduler fires its first job.
bootstrap_git_repo()

from ingestion import main as ingestion_main
from wiki_writer import main as wiki_writer_main
from mcp_server.main import build_app

INGESTION_INTERVAL_MINUTES = int(os.environ.get("INGESTION_INTERVAL_MINUTES", "240"))  # 4h
WIKI_WRITER_INTERVAL_MINUTES = int(os.environ.get("WIKI_WRITER_INTERVAL_MINUTES", "240"))  # 4h
WIKI_WRITER_OFFSET_MINUTES = int(os.environ.get("WIKI_WRITER_OFFSET_MINUTES", "30"))


def run_ingestion_safely():
    try:
        ingestion_main.run()
    except Exception:
        log.exception("ingestion run raised unexpectedly (already logged to state.db by run())")


def run_wiki_writer_safely():
    try:
        wiki_writer_main.run()
    except Exception:
        log.exception("wiki_writer run raised unexpectedly (already logged to state.db by run())")


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_ingestion_safely,
        "interval",
        minutes=INGESTION_INTERVAL_MINUTES,
        id="ingestion",
        next_run_time=None,  # set below, staggered
    )
    scheduler.add_job(
        run_wiki_writer_safely,
        "interval",
        minutes=WIKI_WRITER_INTERVAL_MINUTES,
        id="wiki_writer",
        next_run_time=None,
    )
    scheduler.start()

    import datetime
    now = datetime.datetime.now()
    scheduler.reschedule_job(
        "ingestion", trigger="interval", minutes=INGESTION_INTERVAL_MINUTES,
        start_date=now + datetime.timedelta(seconds=10),
    )
    scheduler.reschedule_job(
        "wiki_writer", trigger="interval", minutes=WIKI_WRITER_INTERVAL_MINUTES,
        start_date=now + datetime.timedelta(minutes=WIKI_WRITER_OFFSET_MINUTES),
    )
    return scheduler


app = build_app()
scheduler = start_scheduler()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
