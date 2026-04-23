from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import logging

from .serializers import ProcessingResultSerializer
from .tasks import process_document_task
from document.models import Document, ProcessingResult

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def process_document(request, document_id):
    """
    API endpoint to manually trigger document processing
    """
    try:
        document = get_object_or_404(Document, id=document_id, uploaded_by=request.user)
        
        # Start processing
        result = process_document_task(str(document.id))
        
        if result['status'] == 'success':
            return Response(result)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Manual processing failed: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class ProcessingResultView(generics.RetrieveAPIView):
    """
    API endpoint to retrieve processing results for a document
    """
    serializer_class = ProcessingResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        document_id = self.kwargs['document_id']
        document = get_object_or_404(Document, id=document_id, uploaded_by=self.request.user)
        
        try:
            return document.processing_result
        except ProcessingResult.DoesNotExist:
            return None


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def processing_summary(request, document_id):
    """
    API endpoint to get a summary of processing results
    """
    try:
        document = get_object_or_404(Document, id=document_id, uploaded_by=request.user)
        
        summary = {
            'document_id': str(document.id),
            'original_filename': document.filename,
            'file_type': document.file_type,
            'status': document.status,
            'uploaded_at': document.uploaded_at,
            'processed_at': document.processed_at,
            'document_type': document.document_type,
            'confidence_score': document.confidence_score,
        }
        
        # Add processing result if available
        if hasattr(document, 'processing_result'):
            result = document.processing_result
            summary.update({
                'processing_time': result.processing_time,
                'has_structured_data': result.structured_data is not None,
                'validation_passed': result.validation_results.get('is_valid', False) if result.validation_results else None,
                'final_confidence_score': result.confidence_report.get('final_score', 0) if result.confidence_report else 0,
                'risk_level': result.confidence_report.get('risk_level', 'unknown') if result.confidence_report else 'unknown',
            })
        
        return Response(summary)
        
    except Exception as e:
        logger.error(f"Failed to get processing summary: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
