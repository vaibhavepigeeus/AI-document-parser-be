"""
Main processing tasks that orchestrate the document parsing pipeline
"""
import time
import logging
from datetime import datetime
from django.utils import timezone
from django.db import transaction

from document.models import Document, ProcessingResult, ProcessingLog
from .services.extraction import extract_text_from_document
from .services.classification import classify_document
from .services.invoice_parsing import parse_invoice

logger = logging.getLogger(__name__)


def process_document_task(document_id: str) -> dict:
    """
    Main task to process a document through the complete pipeline
    This replaces the main.py logic with Django integration
    """
    start_time = time.time()
    
    try:
        # Get document
        document = Document.objects.get(id=document_id)
        logger.info(f"Starting processing for document {document_id}")
        
        # Update document status
        document.status = 'processing'
        document.save()
        
        # Create processing result record
        processing_result = ProcessingResult.objects.create(document=document)
        
        # Step 1: Text Extraction
        logger.info(f"Step 1: Extracting text from {document.file_type}")
        extracted_text = extract_text_from_document(document)
        
        # Update document with extracted text
        document.extracted_text = extracted_text
        document.save()
        
        # Step 2: Document Classification
        logger.info("Step 2: Classifying document")
        classification_result = classify_document(document)
        
        # Update document with classification results
        document.document_type = classification_result.get('document_type')
        document.confidence_score = classification_result.get('confidence_score')
        document.save()
        
        # Store classification in processing result
        processing_result.raw_json_data = classification_result
        
        # Step 3: Route based on document type
        if document.document_type == 'invoice':
            logger.info("Step 3: Processing invoice")
            invoice_data = parse_invoice(document)
            
            # Store invoice data
            processing_result.structured_data = invoice_data
            
            # Validate invoice data
            validation_result = validate_invoice_data(invoice_data)
            processing_result.validation_results = validation_result
            
            # Generate confidence report
            confidence_report = generate_confidence_report(
                classification_result, invoice_data, validation_result
            )
            processing_result.confidence_report = confidence_report
            
        elif document.document_type == 'bank_statement':
            logger.info("Step 3: Processing bank statement")
            # TODO: Implement bank statement processing
            processing_result.structured_data = {
                'message': 'Bank statement processing not yet implemented',
                'document_type': 'bank_statement'
            }
            
        elif document.document_type == 'manual_review':
            logger.info("Step 3: Flagged for manual review")
            processing_result.structured_data = {
                'message': 'Document flagged for manual review',
                'document_type': 'manual_review'
            }
            
        else:
            logger.warning(f"Step 3: Unknown document type {document.document_type}")
            processing_result.structured_data = {
                'message': f'Unknown document type: {document.document_type}',
                'document_type': document.document_type
            }
        
        # Calculate processing time
        processing_time = time.time() - start_time
        processing_result.processing_time = processing_time
        
        # Save processing result
        processing_result.save()
        
        # Update document status
        document.status = 'completed'
        document.processed_at = timezone.now()
        document.save()
        
        logger.info(f"Document processing completed in {processing_time:.2f} seconds")
        
        return {
            'status': 'success',
            'document_id': str(document.id),
            'document_type': document.document_type,
            'confidence_score': document.confidence_score,
            'processing_time': processing_time
        }
        
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        return {
            'status': 'error',
            'message': 'Document not found'
        }
        
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        
        # Update document status to failed
        try:
            document = Document.objects.get(id=document_id)
            document.status = 'failed'
            document.save()
            
            # Store error information
            if hasattr(document, 'processing_result'):
                processing_result = document.processing_result
                processing_result.error_message = str(e)
                processing_result.save()
                
        except Document.DoesNotExist:
            pass
        
        return {
            'status': 'error',
            'message': str(e)
        }


def validate_invoice_data(invoice_data: dict) -> dict:
    """
    Validate invoice data and return validation results
    """
    validation_result = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'checks': {}
    }
    
    try:
        # Check required fields
        required_fields = ['invoice_number', 'total_amount']
        for field in required_fields:
            if field not in invoice_data or invoice_data[field] is None:
                validation_result['errors'].append(f"Missing required field: {field}")
                validation_result['is_valid'] = False
        
        # Check financial consistency
        if all(invoice_data.get(field) is not None for field in ['subtotal', 'tax_amount', 'shipping_amount', 'discount_amount', 'total_amount']):
            calculated_total = (
                (invoice_data['subtotal'] or 0) +
                (invoice_data['tax_amount'] or 0) +
                (invoice_data['shipping_amount'] or 0) -
                (invoice_data['discount_amount'] or 0)
            )
            
            tolerance = 0.01  # Allow small rounding differences
            if abs(calculated_total - invoice_data['total_amount']) > tolerance:
                validation_result['errors'].append(
                    f"Financial inconsistency: calculated total ({calculated_total}) != total_amount ({invoice_data['total_amount']})"
                )
                validation_result['is_valid'] = False
            
            validation_result['checks']['financial_consistency'] = {
                'passed': abs(calculated_total - invoice_data['total_amount']) <= tolerance,
                'calculated_total': calculated_total,
                'provided_total': invoice_data['total_amount']
            }
        
        # Validate line items if present
        if 'line_items' in invoice_data and isinstance(invoice_data['line_items'], list):
            line_items_total = 0
            for item in invoice_data['line_items']:
                if isinstance(item, dict) and item.get('total') is not None:
                    line_items_total += item['total']
            
            tolerance = 0.01
            if 'subtotal' in invoice_data and invoice_data['subtotal'] is not None:
                if abs(line_items_total - invoice_data['subtotal']) > tolerance:
                    validation_result['warnings'].append(
                        f"Line items total ({line_items_total}) != subtotal ({invoice_data['subtotal']})"
                    )
            
            validation_result['checks']['line_items_consistency'] = {
                'passed': abs(line_items_total - invoice_data.get('subtotal', 0)) <= tolerance,
                'line_items_total': line_items_total,
                'subtotal': invoice_data.get('subtotal')
            }
        
        # Validate charges array if present
        if 'charges' in invoice_data and isinstance(invoice_data['charges'], list):
            charges_total = sum(charge.get('amount', 0) for charge in invoice_data['charges'] if isinstance(charge, dict))
            
            if 'total_amount' in invoice_data and invoice_data['total_amount'] is not None:
                tolerance = 0.01
                if abs(charges_total - invoice_data['total_amount']) > tolerance:
                    validation_result['warnings'].append(
                        f"Charges total ({charges_total}) != total_amount ({invoice_data['total_amount']})"
                    )
            
            validation_result['checks']['charges_consistency'] = {
                'passed': abs(charges_total - invoice_data.get('total_amount', 0)) <= tolerance,
                'charges_total': charges_total,
                'total_amount': invoice_data.get('total_amount')
            }
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return {
            'is_valid': False,
            'errors': [f"Validation error: {str(e)}"],
            'warnings': [],
            'checks': {}
        }


def generate_confidence_report(classification_result: dict, structured_data: dict, validation_result: dict) -> dict:
    """
    Generate a comprehensive confidence report
    """
    confidence_report = {
        'final_score': 0.0,
        'components': {
            'classification': {
                'score': 0.0,
                'weight': 0.3,
                'details': {}
            },
            'extraction': {
                'score': 0.0,
                'weight': 0.4,
                'details': {}
            },
            'validation': {
                'score': 0.0,
                'weight': 0.3,
                'details': {}
            }
        },
        'recommendations': [],
        'risk_level': 'low'
    }
    
    try:
        # Classification confidence
        classification_score = classification_result.get('confidence_score', 0.0)
        confidence_report['components']['classification']['score'] = classification_score * 100
        confidence_report['components']['classification']['details'] = {
            'method': classification_result.get('method', 'unknown'),
            'document_type': classification_result.get('document_type', 'unknown')
        }
        
        # Extraction confidence (based on data completeness)
        extraction_score = 0.0
        if isinstance(structured_data, dict):
            total_fields = len(structured_data)
            non_null_fields = len([k for k, v in structured_data.items() if v is not None])
            extraction_score = (non_null_fields / max(total_fields, 1)) * 100
        
        confidence_report['components']['extraction']['score'] = extraction_score
        confidence_report['components']['extraction']['details'] = {
            'total_fields': total_fields,
            'non_null_fields': non_null_fields,
            'completeness': extraction_score
        }
        
        # Validation confidence
        validation_score = 100.0 if validation_result.get('is_valid', False) else 50.0
        if validation_result.get('errors'):
            validation_score -= len(validation_result['errors']) * 10
        if validation_result.get('warnings'):
            validation_score -= len(validation_result['warnings']) * 5
        
        validation_score = max(0, validation_score)
        confidence_report['components']['validation']['score'] = validation_score
        confidence_report['components']['validation']['details'] = {
            'is_valid': validation_result.get('is_valid', False),
            'error_count': len(validation_result.get('errors', [])),
            'warning_count': len(validation_result.get('warnings', []))
        }
        
        # Calculate final weighted score
        final_score = (
            confidence_report['components']['classification']['score'] * 0.3 +
            confidence_report['components']['extraction']['score'] * 0.4 +
            confidence_report['components']['validation']['score'] * 0.3
        )
        confidence_report['final_score'] = round(final_score, 2)
        
        # Determine risk level and recommendations
        if final_score >= 80:
            confidence_report['risk_level'] = 'low'
            confidence_report['recommendations'] = ['Processing completed successfully']
        elif final_score >= 60:
            confidence_report['risk_level'] = 'medium'
            confidence_report['recommendations'] = ['Review results for accuracy']
        else:
            confidence_report['risk_level'] = 'high'
            confidence_report['recommendations'] = ['Manual review recommended']
        
        return confidence_report
        
    except Exception as e:
        logger.error(f"Confidence report generation failed: {e}")
        return {
            'final_score': 0.0,
            'error': str(e),
            'risk_level': 'high'
        }
