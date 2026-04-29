import logging
from document.models import Document
from bankmanagement.services.bank_statement_parser import process_bank_statement
from bankmanagement.services.invoice_parsing import process_invoice
logger = logging.getLogger(__name__)


def run_parser():
    """
    Determine which parser to run based on document type and process pending files.
    This function is called by the scheduler at regular intervals.
    """
    try:
        # Get all documents that are in UPLOADED status
        pending_documents = Document.objects.filter(
            status=Document.StatusChoices.UPLOADED
        ).order_by('uploaded_at')
        
        if not pending_documents:
            logger.info("No new files to process")
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'message': 'No pending files found'
            }
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for document in pending_documents:
            logger.info(f"Processing file: {document.filename}")
            
            try:
                # Determine which parser to use based on document type
                if document.document_type == Document.DocumentType.BANK_STATEMENT:
                    logger.info(f"Running bank statement parser for: {document.filename}")
                    result = process_bank_statement(document)
                elif document.document_type == Document.DocumentType.INVOICE:
                    logger.info(f"Running invoice parser for: {document.filename}")
                    
                    # Check if invoice already exists for this document
                    if hasattr(document, 'invoice'):
                        logger.info(f"Invoice already exists for document: {document.filename}")
                        result = {
                            'success': False, 
                            'error': 'Invoice already exists for this document',
                            'message': 'Skipping - invoice already created'
                        }
                    else:
                        try:
                            invoice_result = process_invoice(document)
                            
                            if invoice_result.get('success'):
                                result = {
                                    'success': True, 
                                    'message': 'Invoice processed successfully',
                                    'data': invoice_result.get('data'),
                                    'invoice_id': invoice_result.get('invoice_id')
                                }
                            else:
                                result = {'success': False, 'error': invoice_result.get('error')}
                        except Exception as e:
                            logger.error(f"Invoice parsing failed for {document.filename}: {e}")
                            document.status = Document.StatusChoices.FAILED
                            document.error_message = str(e)
                            document.save()
                            result = {'success': False, 'error': str(e)}
                else:
                    logger.warning(f"Unknown document type: {document.document_type}")
                    document.status = Document.StatusChoices.FAILED
                    document.error_message = f"Unknown document type: {document.document_type}"
                    document.save()
                    result = {'success': False, 'error': 'Unknown document type'}
                
                results['processed'] += 1
                
                if result.get('success'):
                    results['successful'] += 1
                    logger.info(f"Successfully processed: {document.filename}")
                else:
                    results['failed'] += 1
                    logger.error(f"Failed to process: {document.filename} - {result.get('error')}")
                
                results['details'].append({
                    'filename': document.filename,
                    'document_type': document.document_type,
                    'success': result.get('success'),
                    'error': result.get('error'),
                    'message': result.get('message')
                })
                
            except Exception as e:
                results['processed'] += 1
                results['failed'] += 1
                error_msg = f"Error processing {document.filename}: {str(e)}"
                logger.error(error_msg)
                
                # Mark document as failed
                document.status = Document.StatusChoices.FAILED
                document.error_message = str(e)
                document.save()
                
                results['details'].append({
                    'filename': document.filename,
                    'document_type': document.document_type,
                    'success': False,
                    'error': str(e)
                })
        
        logger.info(f"File processing completed: {results['successful']}/{results['processed']} successful")
        return results
        
    except Exception as e:
        logger.error(f"Error in run_parser: {str(e)}")
        return {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'error': str(e)
        }