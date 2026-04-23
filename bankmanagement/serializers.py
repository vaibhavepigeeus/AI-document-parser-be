from rest_framework import serializers
from document.models import ProcessingResult


class ProcessingResultSerializer(serializers.ModelSerializer):
    """Serializer for ProcessingResult model"""
    
    class Meta:
        model = ProcessingResult
        fields = [
            'raw_json_data', 'structured_data', 'validation_results',
            'confidence_report', 'processing_time', 'processing_steps',
            'error_message', 'error_details', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class ProcessingSummarySerializer(serializers.Serializer):
    """Serializer for processing summary"""
    document_id = serializers.IntegerField()
    original_filename = serializers.CharField()
    file_type = serializers.CharField()
    status = serializers.CharField()
    uploaded_at = serializers.DateTimeField()
    processed_at = serializers.DateTimeField(allow_null=True)
    document_type = serializers.CharField(allow_null=True)
    confidence_score = serializers.FloatField(allow_null=True)
    processing_time = serializers.FloatField(allow_null=True)
    has_structured_data = serializers.BooleanField()
    validation_passed = serializers.BooleanField(allow_null=True)
    final_confidence_score = serializers.FloatField(allow_null=True)
    risk_level = serializers.CharField(allow_null=True)
