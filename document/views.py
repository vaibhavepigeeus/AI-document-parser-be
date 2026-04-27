from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
import logging

from .models import Document, ProcessingResult, Reconciliation
from invoicemanagement.models import Invoice
from bankmanagement.models import BankTransaction
from .serializers import (
    DocumentSerializer, DocumentUploadSerializer, 
    DocumentDetailSerializer, ProcessingResultSerializer,
    ReconciliationListSerializer, UnreconciledInvoiceSerializer,
    UnreconciledBankTransactionSerializer
)

logger = logging.getLogger(__name__)


class DocumentUploadView(generics.CreateAPIView):
    """API endpoint for uploading documents"""
    queryset = Document.objects.all()
    serializer_class = DocumentUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    # permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        """Create document - background scheduler will handle processing"""
        with transaction.atomic():
            # Create the document with basic info
            document = serializer.save()
            
            # Set status to uploaded - background scheduler will pick this up
            document.status = Document.StatusChoices.UPLOADED
            document.save()
        
        return document


class DocumentListView(generics.ListAPIView):
    """API endpoint for listing documents"""
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    # permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return all documents for testing"""
        return Document.objects.all()


class DocumentDetailView(generics.RetrieveAPIView):
    """API endpoint for retrieving document details"""
    queryset = Document.objects.all()
    serializer_class = DocumentDetailSerializer
    # permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return all documents for testing"""
        return Document.objects.all()


@api_view(['POST'])
# @permission_classes([permissions.IsAuthenticated])
def reprocess_document(request, document_id):
    """API endpoint to reprocess a document"""
    document = get_object_or_404(Document, id=document_id)
    
    try:
        # Reset document status
        document.status = 'processing'
        document.save()
        
        # Clear previous results
        ProcessingResult.objects.filter(document=document).delete()
        
        # Trigger reprocessing
        from backend.bankmanagement.tasks import process_document_task
        # process_document_task.delay(document.id)
        
        # For development, process synchronously
        process_document_task(document.id)
        
        return Response({
            'message': 'Document reprocessing started',
            'document_id': str(document.id)
        })
        
    except Exception as e:
        logger.error(f"Failed to reprocess document {document_id}: {e}")
        return Response(
            {'error': 'Failed to start reprocessing'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
# @permission_classes([permissions.IsAuthenticated])
def delete_document(request, document_id):
    """API endpoint to delete a document"""
    document = get_object_or_404(Document, id=document_id)
    
    try:
        # Delete document and related data
        document.delete()
        
        return Response({
            'message': 'Document deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to delete document {document_id}: {e}")
        return Response(
            {'error': 'Failed to delete document'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
# @permission_classes([permissions.IsAuthenticated])
def processing_status(request, document_id):
    """API endpoint to check processing status"""
    document = get_object_or_404(Document, id=document_id)
    
    response_data = {
        'document_id': document.id,
        'status': document.status,
        'uploaded_at': document.uploaded_at,
        'document_type': document.document_type,
    }
    
    # Add processing logs if available
    if hasattr(document, 'processing_logs'):
        response_data['processing_logs'] = [
            {
                'step_name': log.step_name,
                'status': log.status,
                'duration': log.duration,
                'started_at': log.started_at
            }
            for log in document.processing_logs.all()
        ]
    
    return Response(response_data)


@api_view(['GET'])
# @permission_classes([permissions.IsAuthenticated])
def reconciliation_list(request):
    """API endpoint for comprehensive reconciliation list"""
    
    result = []
    
    # Get reconciled items (invoice + transaction combined)
    reconciled_records = Reconciliation.objects.select_related(
        'invoice', 'payment_advice', 'bank_transaction'
    ).all()
    
    for record in reconciled_records:
        combined_item = {
            # Invoice details
            "Invoice": record.invoice.invoiceNo if record.invoice else None,
            "InvoiceDate": record.invoice.invoicedate if record.invoice else None,
            "invoiceAmt": float(record.invoice.totalAmount) if record.invoice and record.invoice.totalAmount else None,
            "invoiceAging": 0,  # Static aging for invoice
            
            # Reconciliation details
            "reconciliation_status": record.status,
            "reconciliation_date": record.reconciliation_date.isoformat() if record.reconciliation_date else None,
            "amount_variance": float(record.amount_variance) if record.amount_variance else None,
            "matching_confidence": record.matching_confidence,
            "notes": record.notes,
            
            # Transaction details (only if matched)
            "TransactionID": record.bank_transaction.id if record.bank_transaction else None,
            "TransactionDate": record.bank_transaction.transaction_date if record.bank_transaction else None,
            "txn_no": record.bank_transaction.txn_no if record.bank_transaction else None,
            "transaction_amount": float(record.bank_transaction.amount) if record.bank_transaction and record.bank_transaction.amount else None,
            "transaction_type": record.bank_transaction.transaction_type if record.bank_transaction else None,
            "description": record.bank_transaction.description if record.bank_transaction else None,
            "account_number": record.bank_transaction.bank_statement.account_number if record.bank_transaction and record.bank_transaction.bank_statement else None,
            "txnAging": 0,  # Static aging for transaction
        }
        result.append(combined_item)
    
    # Get unreconciled invoices (invoice only)
    reconciled_invoice_ids = reconciled_records.values_list('invoice__id', flat=True)
    unreconciled_invoices = Invoice.objects.filter(
        reconciliation_status='unreconciled'
    ).exclude(
        id__in=reconciled_invoice_ids
    )
    
    for invoice in unreconciled_invoices:
        invoice_item = {
            # Invoice details only
            "Invoice": invoice.invoiceNo,
            "InvoiceDate": invoice.invoicedate,
            "invoiceAmt": float(invoice.totalAmount) if invoice.totalAmount else None,
            "invoiceAging": 0,  # Static aging for invoice
            "reconciliation_status": invoice.reconciliation_status,
            
            # No transaction details (null values)
            "reconciliation_date": None,
            "amount_variance": None,
            "matching_confidence": None,
            "notes": None,
            "TransactionID": None,
            "TransactionDate": None,
            "txn_no": None,
            "transaction_amount": None,
            "transaction_type": None,
            "description": None,
            "account_number": None,
            "txnAging": 0,  # Static aging for transaction
        }
        result.append(invoice_item)
    
    # Get unreconciled bank transactions (transaction only)
    reconciled_transaction_ids = reconciled_records.values_list('bank_transaction__id', flat=True)
    unreconciled_transactions = BankTransaction.objects.select_related(
        'bank_statement'
    ).exclude(
        id__in=reconciled_transaction_ids
    )
    
    for transaction in unreconciled_transactions:
        transaction_item = {
            # Transaction details only
            "TransactionID": transaction.id,
            "TransactionDate": transaction.transaction_date,
            "txn_no": transaction.txn_no,
            "transaction_amount": float(transaction.amount) if transaction.amount else None,
            "transaction_type": transaction.transaction_type,
            "description": transaction.description,
            "account_number": transaction.bank_statement.account_number if transaction.bank_statement else None,
            "txnAging": 0,  # Static aging for transaction
            
            # No invoice details (null values)
            "Invoice": None,
            "InvoiceDate": None,
            "invoiceAmt": None,
            "invoiceAging": 0,  # Static aging for invoice
            "reconciliation_status": None,
            "reconciliation_date": None,
            "amount_variance": None,
            "matching_confidence": None,
            "notes": None,
        }
        result.append(transaction_item)
    
    return Response(result)