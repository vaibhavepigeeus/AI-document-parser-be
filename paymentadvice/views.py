from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
import logging

from .models import PaymentAdvice
from .serializers import PaymentAdviceSerializer

logger = logging.getLogger(__name__)


class PaymentAdvicePagination(PageNumberPagination):
    """Custom pagination for payment advice with scroll-based loading"""
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


class PaymentAdviceListCreateView(generics.ListCreateAPIView):
    """View to list and create payment advice records"""
    queryset = PaymentAdvice.objects.all()
    serializer_class = PaymentAdviceSerializer
    # permission_classes = [permissions.IsAuthenticated]
    pagination_class = PaymentAdvicePagination
    
    def get_queryset(self):
        """
        Override to apply search and date filters
        """
        queryset = PaymentAdvice.objects.all()
        
        # Apply filters
        search = self.request.query_params.get('search', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        is_matched = self.request.query_params.get('is_matched', None)
        
        if search:
            # Search in invoice number and currency
            queryset = queryset.filter(
                payment_invoice_no__icontains=search
            ) | queryset.filter(
                payment_currency__icontains=search
            )
        
        if start_date:
            queryset = queryset.filter(payment_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(payment_date__lte=end_date)
            
        if is_matched is not None:
            queryset = queryset.filter(is_matched=is_matched.lower() == 'true')
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """
        Override list method to handle filter behavior
        """
        # Check if any filter is applied
        search = request.query_params.get('search', None)
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        is_matched = request.query_params.get('is_matched', None)
        
        has_filters = bool(search or start_date or end_date or is_matched)
        
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
            return super().list(request, *args, **kwargs)
