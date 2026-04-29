from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
import logging

from .models import BankStatement, BankTransaction
from .serializers import BankStatementDetailsSerializer, BankStatementSerializer, BankTransactionSerializer
from document.models import Document

logger = logging.getLogger(__name__)


class BankStatementPagination(PageNumberPagination):
    """Custom pagination for bank statements with scroll-based loading"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'has_next': self.page.has_next(),
            'has_previous': self.page.has_previous(),
            'results': data
        })


class BankStatementListCreateView(generics.ListCreateAPIView):
    """View to list and create bank statements"""
    queryset = BankStatement.objects.all()
    serializer_class = BankStatementSerializer
    permission_classes = [permissions.IsAuthenticated]


class BankStatementDetailsListView(generics.ListAPIView):
    """View to list bank statements with all related transactions in flattened format"""
    queryset = BankStatement.objects.select_related('document').prefetch_related('transactions').all()
    serializer_class = BankStatementDetailsSerializer
    pagination_class = BankStatementPagination
    # permission_classes = [permissions.IsAuthenticated]
    
        
    def list(self, request, *args, **kwargs):
        """
        Override list method to create flattened response with statement and transaction data
        """
        # Get base queryset - only statements with transactions
        queryset = BankStatement.objects.prefetch_related('transactions').filter(transactions__isnull=False).distinct()
        
        # Apply filters
        search = request.query_params.get('search', None)
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        if search:
            # Search in both account number and transaction details
            queryset = queryset.filter(
                account_number__icontains=search
            ) | queryset.filter(
                transactions__txn_no__icontains=search
            )
        
        if start_date:
            queryset = queryset.filter(statement_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(statement_date__lte=end_date)
        
        # Create flattened data structure first
        flattened_data = []
        for statement in queryset:
            # Add statement-level record
            statement_record = {
                'Account': statement.account_number,
                'Transaction': None,
                'Date': statement.statement_date,
                'Amount': None,
                'Total': statement.total_receivable_amt,
                'Ageing': None,
                'statement_id': statement.id,
                'bank_name': statement.bank_name,
                'statement_period': statement.statement_period,
                'transaction_type': None
            }
            
            # Add transaction-level records
            transaction_records = []
            for transaction in statement.transactions.all():
                from datetime import date
                ageing = None
                if transaction.transaction_date:
                    delta = date.today() - transaction.transaction_date
                    ageing = delta.days
                
                transaction_record = {
                    'Account': statement.account_number,
                    'Transaction': transaction.txn_no,
                    'Date': transaction.transaction_date,
                    'Amount': transaction.amount,
                    'Total': statement.total_receivable_amt,
                    'Ageing': ageing,
                    'statement_id': statement.id,
                    'bank_name': statement.bank_name,
                    'statement_period': statement.statement_period,
                    'transaction_type': transaction.transaction_type
                }
                transaction_records.append(transaction_record)
            
            # Apply search filter at flattened level
            if search:
                # Check if statement matches
                statement_matches = search.lower() in str(statement.account_number).lower() if statement.account_number else False
                
                # Check if any transaction matches
                matching_transactions = [t for t in transaction_records if t['Transaction'] and search.lower() in str(t['Transaction']).lower()]
                
                if statement_matches:
                    flattened_data.append(statement_record)
                    flattened_data.extend(transaction_records)
                elif matching_transactions:
                    flattened_data.append(statement_record)
                    flattened_data.extend(matching_transactions)
            else:
                # No search filter, add everything
                flattened_data.append(statement_record)
                flattened_data.extend(transaction_records)
        
        # Now paginate the flattened data
        page_size = int(request.query_params.get('page_size', self.pagination_class.page_size))
        page_number = int(request.query_params.get('page', 1))
        
        start_index = (page_number - 1) * page_size
        end_index = start_index + page_size
        
        paginated_data = flattened_data[start_index:end_index]
        
        # Create pagination response manually
        total_count = len(flattened_data)
        total_pages = (total_count + page_size - 1) // page_size
        
        return Response({
            'next': f"http://localhost:8000/api/bankmanagement/statements/details/?page={page_number + 1}&page_size={page_size}" if page_number < total_pages else None,
            'previous': f"http://localhost:8000/api/bankmanagement/statements/details/?page={page_number - 1}&page_size={page_size}" if page_number > 1 else None,
            'count': total_count,
            'total_pages': total_pages,
            'current_page': page_number,
            'has_next': page_number < total_pages,
            'has_previous': page_number > 1,
            'results': paginated_data
        })



