from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import logging

from .models import Invoice, InvoiceLineItem
from .serializers import InvoiceSerializer, InvoiceCreateSerializer, InvoiceSummarySerializer
from document.models import Document

logger = logging.getLogger(__name__)


class InvoiceListCreateView(generics.ListCreateAPIView):
    """View to list and create invoices"""
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InvoiceCreateSerializer
        return InvoiceSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class InvoiceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View to retrieve, update, and delete invoices"""
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def invoice_summary(request, document_id):
    """Get invoice summary for a document"""
    try:
        document = get_object_or_404(Document, id=document_id, user=request.user)
        invoice = get_object_or_404(Invoice, document=document, user=request.user)
        
        line_item_count = invoice.line_items.count()
        
        summary_data = {
            'invoice_id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'vendor_name': invoice.vendor_name,
            'total_amount': invoice.total_amount,
            'currency': invoice.currency,
            'status': invoice.status,
            'created_at': invoice.created_at,
            'line_item_count': line_item_count,
            'confidence_score': invoice.confidence_score
        }
        
        serializer = InvoiceSummarySerializer(summary_data)
        return Response(serializer.data)
        
    except Invoice.DoesNotExist:
        return Response(
            {'error': 'No invoice found for this document'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_invoice_from_document(request, document_id):
    """Create invoice from processed document"""
    try:
        document = get_object_or_404(Document, id=document_id, user=request.user)
        
        if document.document_type != 'invoice':
            return Response(
                {'error': 'Document is not an invoice'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if invoice already exists
        if hasattr(document, 'invoice'):
            return Response(
                {'error': 'Invoice already exists for this document'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract invoice data from processing result
        if not hasattr(document, 'processingresult'):
            return Response(
                {'error': 'Document has not been processed yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        processing_result = document.processingresult
        structured_data = processing_result.structured_data or {}
        
        # Create invoice with extracted data
        invoice_data = {
            'document': document,
            'invoice_number': structured_data.get('invoice_number'),
            'invoice_date': structured_data.get('invoice_date'),
            'due_date': structured_data.get('due_date'),
            'vendor_name': structured_data.get('vendor_name'),
            'vendor_address': structured_data.get('vendor_address'),
            'customer_name': structured_data.get('customer_name'),
            'customer_address': structured_data.get('customer_address'),
            'subtotal': structured_data.get('subtotal'),
            'tax_amount': structured_data.get('tax_amount'),
            'total_amount': structured_data.get('total_amount'),
            'currency': structured_data.get('currency', 'USD'),
            'confidence_score': processing_result.confidence_report.get('overall_confidence', 0.0),
            'extraction_method': 'automated'
        }
        
        invoice = Invoice.objects.create(user=request.user, **invoice_data)
        
        # Create line items if available
        line_items = structured_data.get('line_items', [])
        for item_data in line_items:
            InvoiceLineItem.objects.create(
                invoice=invoice,
                description=item_data.get('description', ''),
                quantity=item_data.get('quantity', 1),
                unit_price=item_data.get('unit_price', 0),
                total_price=item_data.get('total_price', 0),
                item_code=item_data.get('item_code'),
                tax_rate=item_data.get('tax_rate'),
                discount_amount=item_data.get('discount_amount')
            )
        
        serializer = InvoiceSerializer(invoice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error creating invoice from document {document_id}: {str(e)}")
        return Response(
            {'error': 'Failed to create invoice from document'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
