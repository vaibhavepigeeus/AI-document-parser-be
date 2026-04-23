from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import logging

from .models import BankStatement, BankTransaction
from .serializers_bank import BankStatementSerializer, BankStatementCreateSerializer, BankStatementSummarySerializer
from document.models import Document

logger = logging.getLogger(__name__)


class BankStatementListCreateView(generics.ListCreateAPIView):
    """View to list and create bank statements"""
    serializer_class = BankStatementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return BankStatement.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BankStatementCreateSerializer
        return BankStatementSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class BankStatementDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View to retrieve, update, and delete bank statements"""
    serializer_class = BankStatementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return BankStatement.objects.filter(user=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def bank_statement_summary(request, document_id):
    """Get bank statement summary for a document"""
    try:
        document = get_object_or_404(Document, id=document_id, user=request.user)
        bank_statement = get_object_or_404(BankStatement, document=document, user=request.user)
        
        transaction_count = bank_statement.transactions.count()
        
        summary_data = {
            'statement_id': bank_statement.id,
            'bank_name': bank_statement.bank_name,
            'statement_period': bank_statement.statement_period,
            'closing_balance': bank_statement.closing_balance,
            'currency': bank_statement.currency,
            'status': bank_statement.status,
            'created_at': bank_statement.created_at,
            'transaction_count': transaction_count,
            'confidence_score': bank_statement.confidence_score
        }
        
        serializer = BankStatementSummarySerializer(summary_data)
        return Response(serializer.data)
        
    except BankStatement.DoesNotExist:
        return Response(
            {'error': 'No bank statement found for this document'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_bank_statement_from_document(request, document_id):
    """Create bank statement from processed document"""
    try:
        document = get_object_or_404(Document, id=document_id, user=request.user)
        
        if document.document_type != 'bank_statement':
            return Response(
                {'error': 'Document is not a bank statement'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if bank statement already exists
        if hasattr(document, 'bank_statement'):
            return Response(
                {'error': 'Bank statement already exists for this document'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract bank statement data from processing result
        if not hasattr(document, 'processingresult'):
            return Response(
                {'error': 'Document has not been processed yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        processing_result = document.processingresult
        structured_data = processing_result.structured_data or {}
        
        # Create bank statement with extracted data
        bank_statement_data = {
            'document': document,
            'bank_name': structured_data.get('bank_name'),
            'statement_period': structured_data.get('statement_period'),
            'statement_date': structured_data.get('statement_date'),
            'account_number': structured_data.get('account_number'),
            'account_type': structured_data.get('account_type'),
            'opening_balance': structured_data.get('opening_balance'),
            'closing_balance': structured_data.get('closing_balance'),
            'currency': structured_data.get('currency', 'USD'),
            'confidence_score': processing_result.confidence_report.get('overall_confidence', 0.0),
            'extraction_method': 'automated'
        }
        
        bank_statement = BankStatement.objects.create(user=request.user, **bank_statement_data)
        
        # Create transactions if available
        transactions = structured_data.get('transactions', [])
        for transaction_data in transactions:
            BankTransaction.objects.create(
                bank_statement=bank_statement,
                transaction_date=transaction_data.get('transaction_date'),
                description=transaction_data.get('description', ''),
                amount=transaction_data.get('amount', 0),
                transaction_type=transaction_data.get('transaction_type', 'other'),
                reference_number=transaction_data.get('reference_number'),
                balance_after_transaction=transaction_data.get('balance_after_transaction'),
                category=transaction_data.get('category'),
                payee=transaction_data.get('payee'),
                confidence_score=transaction_data.get('confidence_score')
            )
        
        serializer = BankStatementSerializer(bank_statement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error creating bank statement from document {document_id}: {str(e)}")
        return Response(
            {'error': 'Failed to create bank statement from document'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
