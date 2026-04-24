"""
Scheduler service for automated processing of bank statements and invoices.
This service handles periodic processing of uploaded documents.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from document.models import Document, ProcessingLog
from bankmanagement.services.bank_statement_parser import process_bank_statement
from invoicemanagement.services.invoice_parser import process_invoice_document

logger = logging.getLogger(__name__)


class DocumentScheduler:
    """
    Scheduler for processing uploaded documents automatically.
    Handles both bank statements and invoices.
    """
    
    def __init__(self):
        self.max_retry_attempts = 3
        self.processing_timeout = 300  # 5 minutes
        self.batch_size = 10
        
    def get_pending_documents(self, document_type: Optional[str] = None) -> List[Document]:
        """
        Get documents that are pending processing.
        
        Args:
            document_type: Filter by document type ('bank_statement' or 'invoice')
            
        Returns:
            List of pending documents
        """
        queryset = Document.objects.filter(
            status=Document.StatusChoices.UPLOADED
        ).order_by('uploaded_at')
        
        if document_type:
            queryset = queryset.filter(document_type=document_type)
            
        return list(queryset[:self.batch_size])
    
    def get_failed_documents_for_retry(self) -> List[Document]:
        """
        Get failed documents that can be retried.
        
        Returns:
            List of failed documents eligible for retry
        """
        retry_cutoff = timezone.now() - timedelta(hours=1)
        
        return Document.objects.filter(
            status=Document.StatusChoices.FAILED,
            updated_at__lt=retry_cutoff
        ).exclude(
            processing_logs__step_name='extraction_failed',
            processing_logs__step_description__contains='retry_count'
        ).order_by('updated_at')[:self.batch_size]
    
    def process_document(self, document: Document) -> Dict:
        """
        Process a single document based on its type.
        
        Args:
            document: Document instance to process
            
        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing document: {document.filename} (ID: {document.id})")
        
        # Update status to processing
        document.status = Document.StatusChoices.PROCESSING
        document.save()
        
        try:
            if document.document_type == Document.DocumentType.BANK_STATEMENT:
                result = process_bank_statement(document)
            elif document.document_type == Document.DocumentType.INVOICE:
                result = process_invoice_document(document)
            else:
                result = {
                    'success': False,
                    'error': f"Unknown document type: {document.document_type}"
                }
                document.status = Document.StatusChoices.FAILED
                document.error_message = result['error']
                document.save()
                
            logger.info(f"Document processing completed: {document.filename} - Success: {result.get('success')}")
            return result
            
        except Exception as e:
            error_msg = f"Unexpected error processing document: {str(e)}"
            logger.error(f"{error_msg} - Document: {document.filename}")
            
            document.status = Document.StatusChoices.FAILED
            document.error_message = error_msg
            document.save()
            
            return {
                'success': False,
                'error': error_msg
            }
    
    def process_pending_documents(self, document_type: Optional[str] = None) -> Dict:
        """
        Process all pending documents of a specific type or all types.
        
        Args:
            document_type: Filter by document type ('bank_statement' or 'invoice')
            
        Returns:
            Summary of processing results
        """
        pending_docs = self.get_pending_documents(document_type)
        
        if not pending_docs:
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'message': 'No pending documents found'
            }
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for document in pending_docs:
            result = self.process_document(document)
            results['processed'] += 1
            
            if result.get('success'):
                results['successful'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append({
                'document_id': document.id,
                'filename': document.filename,
                'success': result.get('success'),
                'error': result.get('error')
            })
        
        logger.info(f"Batch processing completed: {results['successful']}/{results['processed']} successful")
        return results
    
    def retry_failed_documents(self) -> Dict:
        """
        Retry processing failed documents.
        
        Returns:
            Summary of retry results
        """
        failed_docs = self.get_failed_documents_for_retry()
        
        if not failed_docs:
            return {
                'retried': 0,
                'successful': 0,
                'failed': 0,
                'message': 'No failed documents eligible for retry'
            }
        
        results = {
            'retried': 0,
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for document in failed_docs:
            # Clear previous error and reset status
            document.error_message = None
            document.status = Document.StatusChoices.UPLOADED
            document.save()
            
            # Log retry attempt
            ProcessingLog.objects.create(
                document=document,
                step_name='retry_attempt',
                step_description='Automated retry of failed document',
                status='started',
                started_at=timezone.now()
            )
            
            result = self.process_document(document)
            results['retried'] += 1
            
            if result.get('success'):
                results['successful'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append({
                'document_id': document.id,
                'filename': document.filename,
                'success': result.get('success'),
                'error': result.get('error')
            })
        
        logger.info(f"Retry processing completed: {results['successful']}/{results['retried']} successful")
        return results
    
    def cleanup_old_processing_logs(self, days: int = 30) -> Dict:
        """
        Clean up old processing logs to prevent database bloat.
        
        Args:
            days: Number of days to keep logs
            
        Returns:
            Cleanup result summary
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        
        deleted_count = ProcessingLog.objects.filter(
            started_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old processing logs")
        
        return {
            'deleted_logs': deleted_count,
            'cutoff_date': cutoff_date.isoformat()
        }
    
    def get_processing_statistics(self) -> Dict:
        """
        Get current processing statistics.
        
        Returns:
            Statistics dictionary
        """
        stats = {
            'total_documents': Document.objects.count(),
            'uploaded': Document.objects.filter(status=Document.StatusChoices.UPLOADED).count(),
            'processing': Document.objects.filter(status=Document.StatusChoices.PROCESSING).count(),
            'parsed': Document.objects.filter(status=Document.StatusChoices.PARSED).count(),
            'failed': Document.objects.filter(status=Document.StatusChoices.FAILED).count(),
            'by_type': {
                'bank_statements': {
                    'total': Document.objects.filter(document_type=Document.DocumentType.BANK_STATEMENT).count(),
                    'uploaded': Document.objects.filter(
                        document_type=Document.DocumentType.BANK_STATEMENT,
                        status=Document.StatusChoices.UPLOADED
                    ).count(),
                    'parsed': Document.objects.filter(
                        document_type=Document.DocumentType.BANK_STATEMENT,
                        status=Document.StatusChoices.PARSED
                    ).count(),
                    'failed': Document.objects.filter(
                        document_type=Document.DocumentType.BANK_STATEMENT,
                        status=Document.StatusChoices.FAILED
                    ).count(),
                },
                'invoices': {
                    'total': Document.objects.filter(document_type=Document.DocumentType.INVOICE).count(),
                    'uploaded': Document.objects.filter(
                        document_type=Document.DocumentType.INVOICE,
                        status=Document.StatusChoices.UPLOADED
                    ).count(),
                    'parsed': Document.objects.filter(
                        document_type=Document.DocumentType.INVOICE,
                        status=Document.StatusChoices.PARSED
                    ).count(),
                    'failed': Document.objects.filter(
                        document_type=Document.DocumentType.INVOICE,
                        status=Document.StatusChoices.FAILED
                    ).count(),
                }
            },
            'recent_activity': {
                'last_24h': {
                    'uploaded': Document.objects.filter(
                        uploaded_at__gte=timezone.now() - timedelta(hours=24)
                    ).count(),
                    'processed': Document.objects.filter(
                        updated_at__gte=timezone.now() - timedelta(hours=24),
                        status=Document.StatusChoices.PARSED
                    ).count(),
                }
            }
        }
        
        return stats


# Global scheduler instance
scheduler = DocumentScheduler()


def run_scheduled_processing():
    """
    Main function to run scheduled processing.
    This can be called by cron jobs or task schedulers.
    """
    logger.info("Starting scheduled document processing")
    
    try:
        # Process pending bank statements
        bank_results = scheduler.process_pending_documents(Document.DocumentType.BANK_STATEMENT)
        logger.info(f"Bank statement processing: {bank_results}")
        
        # Process pending invoices
        invoice_results = scheduler.process_pending_documents(Document.DocumentType.INVOICE)
        logger.info(f"Invoice processing: {invoice_results}")
        
        # Retry failed documents
        retry_results = scheduler.retry_failed_documents()
        logger.info(f"Retry processing: {retry_results}")
        
        # Get statistics
        stats = scheduler.get_processing_statistics()
        logger.info(f"Current statistics: {stats}")
        
        # Cleanup old logs (run weekly)
        if timezone.now().weekday() == 0:  # Monday
            cleanup_results = scheduler.cleanup_old_processing_logs()
            logger.info(f"Cleanup results: {cleanup_results}")
        
        logger.info("Scheduled processing completed successfully")
        
        return {
            'bank_results': bank_results,
            'invoice_results': invoice_results,
            'retry_results': retry_results,
            'statistics': stats
        }
        
    except Exception as e:
        logger.error(f"Scheduled processing failed: {str(e)}")
        raise


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the scheduler
    results = run_scheduled_processing()
    print("Scheduler execution completed:")
    print(f"Bank statements: {results['bank_results']}")
    print(f"Invoices: {results['invoice_results']}")
    print(f"Retries: {results['retry_results']}")
