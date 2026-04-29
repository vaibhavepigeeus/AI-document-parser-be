"""
Scheduler service for automated processing of bank statements and invoices.
This service handles periodic processing of uploaded documents.
"""

import logging
import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from bankmanagement.services.parser import run_parser
from bankmanagement.services.reconcilation import run_reconcilation
from bankmanagement.services.email_parser import email_parser_job

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def get_config():
    """Get scheduler configuration from database"""
    from document.models import SchedulerConfig
    return SchedulerConfig.get_config()


def update_config_status(**kwargs):
    """Update configuration status in database"""
    from document.models import SchedulerConfig
    config = SchedulerConfig.get_config()
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    config.save()


def start_scheduler():
    """Start the background scheduler"""
    global scheduler
    
    config = get_config()
    
    if scheduler and scheduler.running:
        logger.warning("Scheduler is already running")
        return False
    
    if not config.is_enabled:
        logger.info("Scheduler is disabled in configuration")
        return False
    
    try:
        scheduler = BackgroundScheduler()
        
        # Add parser job if enabled
        if config.parser_enabled:
            scheduler.add_job(
                run_parser, 
                "interval", 
                seconds=config.parser_interval,
                id='parser_job',
                name='Bank Statement Parser'
            )
            logger.info(f"Parser job added with {config.parser_interval}s interval")
        
        # Add reconciliation job if enabled
        if config.reconciliation_enabled:
            scheduler.add_job(
                run_reconcilation, 
                "interval", 
                seconds=config.reconciliation_interval,
                id='reconciliation_job',
                name='Bank Reconciliation'
            )
            logger.info(f"Reconciliation job added with {config.reconciliation_interval}s interval")
        
        # Add email parser job if enabled
        if config.email_parser_enabled:
            scheduler.add_job(
                email_parser_job, 
                "interval", 
                seconds=config.email_parser_interval,
                id='email_parser_job',
                name='Email Parser'
            )
            logger.info(f"Email parser job added with {config.email_parser_interval}s interval")
        
        scheduler.start()
        
        # Update database status
        update_config_status(
            status='running',
            process_id=os.getpid(),
            host_info=os.uname().nodename if hasattr(os, 'uname') else 'unknown',
            error_message=None
        )
        
        logger.info("Background scheduler started successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {str(e)}")
        update_config_status(
            status='error',
            error_message=str(e)
        )
        return False


def stop_scheduler():
    """Stop the background scheduler"""
    global scheduler
    
    if not scheduler or not scheduler.running:
        logger.warning("Scheduler is not running")
        return False
    
    try:
        scheduler.shutdown(wait=True)
        
        # Update database status
        update_config_status(
            status='stopped',
            process_id=None,
            host_info=None
        )
        
        logger.info("Background scheduler stopped successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {str(e)}")
        update_config_status(
            status='error',
            error_message=str(e)
        )
        return False


def restart_scheduler():
    """Restart the scheduler with current configuration"""
    stop_scheduler()
    return start_scheduler()


def update_job_intervals():
    """Update job intervals if scheduler is running"""
    global scheduler
    
    if not scheduler or not scheduler.running:
        return False
    
    config = get_config()
    
    try:
        # Update parser job interval
        if config.parser_enabled:
            if scheduler.get_job('parser_job'):
                scheduler.remove_job('parser_job')
            scheduler.add_job(
                run_parser, 
                "interval", 
                seconds=config.parser_interval,
                id='parser_job',
                name='Bank Statement Parser'
            )
        
        # Update reconciliation job interval
        if config.reconciliation_enabled:
            if scheduler.get_job('reconciliation_job'):
                scheduler.remove_job('reconciliation_job')
            scheduler.add_job(
                run_reconcilation, 
                "interval", 
                seconds=config.reconciliation_interval,
                id='reconciliation_job',
                name='Bank Reconciliation'
            )
        
        # Update email parser job interval
        if config.email_parser_enabled:
            if scheduler.get_job('email_parser_job'):
                scheduler.remove_job('email_parser_job')
            scheduler.add_job(
                email_parser_job, 
                "interval", 
                seconds=config.email_parser_interval,
                id='email_parser_job',
                name='Email Parser'
            )
        
        logger.info("Job intervals updated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update job intervals: {str(e)}")
        update_config_status(error_message=str(e))
        return False


def increment_job_count():
    """Increment the job execution counter"""
    try:
        config = get_config()
        config.job_count += 1
        config.last_run = datetime.now()
        config.save()
    except Exception as e:
        logger.error(f"Failed to update job count: {str(e)}")


def run():
    """Initialize and start the background scheduler (legacy function)"""
    return start_scheduler()

