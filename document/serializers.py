from rest_framework import serializers
from .models import Document, ProcessingResult, ProcessingLog


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for Document model"""
    
    class Meta:
        model = Document
        fields = [
            'id', 'filename', 'document_type', 'file', 'file_path', 'status',
            'uploaded_at', 'updated_at', 'error_message', 'parsed_data'
        ]
        read_only_fields = [
            'id', 'status', 'uploaded_at', 'updated_at', 'error_message', 'parsed_data'
        ]


class DocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for document upload"""
    file = serializers.FileField()
    document_type = serializers.ChoiceField(choices=Document.DocumentType.choices)
    filename = serializers.CharField(read_only=True)
    
    class Meta:
        model = Document
        fields = ['file', 'document_type', 'filename']
    
    def validate_file(self, value):
        """Validate file type and size"""
        # Check file size (50MB limit)
        max_size = 50 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 50MB.")
        
        # Check file extension
        allowed_extensions = ['csv', 'xlsx', 'pdf', 'png', 'jpg', 'jpeg']
        extension = value.name.split('.')[-1].lower()
        if extension not in allowed_extensions:
            raise serializers.ValidationError(
                f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        return value
    
    def create(self, validated_data):
        """Create document with auto-extracted filename"""
        file = validated_data['file']
        validated_data['filename'] = file.name
        return super().create(validated_data)


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


class ProcessingLogSerializer(serializers.ModelSerializer):
    """Serializer for ProcessingLog model"""
    
    class Meta:
        model = ProcessingLog
        fields = [
            'step_name', 'step_description', 'status', 'started_at',
            'completed_at', 'duration', 'input_data', 'output_data',
            'error_message', 'error_traceback'
        ]
        read_only_fields = ['started_at', 'completed_at', 'duration']


class DocumentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Document with related data"""
    
    class Meta:
        model = Document
        fields = [
            'id', 'filename', 'document_type', 'file', 'file_path', 'status',
            'uploaded_at', 'updated_at', 'error_message', 'parsed_data'
        ]
