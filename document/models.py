from django.db import models
from django.contrib.auth.models import User
import os


class Document(models.Model):

    class DocumentType(models.TextChoices):
        BANK_STATEMENT = "bank_statement", "Bank Statement"
        INVOICE = "invoice", "Invoice"

    class StatusChoices(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Failed"

    file = models.FileField(upload_to="uploads/")  # better than raw file_path
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, blank=True)  # optional backup
    document_type = models.CharField(max_length=50, choices=DocumentType.choices)

    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.UPLOADED
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # optional but useful
    error_message = models.TextField(blank=True, null=True)  # if parsing fails
    parsed_data = models.JSONField(blank=True, null=True)   # quick storage (optional)

    def __str__(self):
        return f"{self.filename} ({self.document_type})"


class ProcessingResult(models.Model):
    """Model for storing processing results"""
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='processing_result')
    
    # Raw extracted data
    raw_json_data = models.JSONField(null=True, blank=True)
    
    # Processed/structured data
    structured_data = models.JSONField(null=True, blank=True)
    
    # Validation results
    validation_results = models.JSONField(null=True, blank=True)
    
    # Confidence scoring
    confidence_report = models.JSONField(null=True, blank=True)
    
    # Processing metadata
    processing_time = models.FloatField(null=True, blank=True, help_text="Processing time in seconds")
    processing_steps = models.JSONField(null=True, blank=True, help_text="Log of processing steps")
    
    # Error handling
    error_message = models.TextField(null=True, blank=True)
    error_details = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Processing result for {self.document.filename}"


class ProcessingLog(models.Model):
    """Model for logging processing steps and debugging"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='processing_logs')
    
    # Log details
    step_name = models.CharField(max_length=100)
    step_description = models.TextField()
    status = models.CharField(max_length=20)  # started, completed, failed
    
    # Timing
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True, help_text="Duration in seconds")
    
    # Data at this step
    input_data = models.JSONField(null=True, blank=True)
    output_data = models.JSONField(null=True, blank=True)
    
    # Error information
    error_message = models.TextField(null=True, blank=True)
    error_traceback = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['started_at']
        
    def __str__(self):
        return f"{self.step_name} for {self.document.filename}"
