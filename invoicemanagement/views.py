from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
import logging

from .models import Invoice, InvoiceLineItem
from .serializers import InvoiceSerializer, InvoiceCreateSerializer, InvoiceSummarySerializer
from document.models import Document

logger = logging.getLogger(__name__)


class InvoicePagination(PageNumberPagination):
    """Custom pagination for invoices with scroll-based loading"""
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


class InvoiceListView(generics.ListAPIView):
    """View to list invoices with pagination and filtering"""
    serializer_class = InvoiceSerializer
    # permission_classes = [permissions.IsAuthenticated]
    pagination_class = InvoicePagination
    
    def get_queryset(self):
        """
        Override to apply search and date filters
        """
        queryset = Invoice.objects.all()
        
        # Apply filters
        search = self.request.query_params.get('search', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        status = self.request.query_params.get('status', None)
        reconciliation_status = self.request.query_params.get('reconciliation_status', None)
        
        if search:
            # Search in invoice number
            queryset = queryset.filter(invoiceNo__icontains=search)
        
        if start_date:
            queryset = queryset.filter(invoicedate__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(invoicedate__lte=end_date)
            
        if status:
            queryset = queryset.filter(status=status)
            
        if reconciliation_status:
            queryset = queryset.filter(reconciliation_status=reconciliation_status)
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """
        Override list method to handle filter behavior and nested data structure
        """
        # Check if any filter is applied
        search = request.query_params.get('search', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        status = self.request.query_params.get('status', None)
        reconciliation_status = self.request.query_params.get('reconciliation_status', None)
        
        has_filters = bool(search or start_date or end_date or status or reconciliation_status)
        
        if has_filters:
            # Return all results without pagination when filters are applied
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            
            return Response({
                'next': None,
                'previous': None,
                'count': len(serializer.data),
                'total_pages': 1,
                'current_page': 1,
                'has_next': False,
                'has_previous': False,
                'results': serializer.data
            })
        else:
            # Use default pagination when no filters
            response = super().list(request, *args, **kwargs)
            return response
