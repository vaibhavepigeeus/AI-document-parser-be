"""
Scheduler service for automated processing of bank statements and invoices.
This service handles periodic processing of uploaded documents.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler

from bankmanagement.services.parser import run_parser

logger = logging.getLogger(__name__)


def run():
    """
    Initialize and start the background scheduler.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_parser, "interval", seconds=60)
    scheduler.start()
    logger.info("Background scheduler started with 60-second interval")
    return scheduler

