from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
import logging

from .models import Document, ProcessingResult
from .serializers import (
    DocumentSerializer, DocumentUploadSerializer, 
    DocumentDetailSerializer, ProcessingResultSerializer
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
