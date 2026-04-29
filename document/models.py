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


class Reconciliation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('matched', 'Matched'),
        ('failed', 'Failed'),
        ('manual_review', 'Manual Review'),
    ]
    
    invoice = models.ForeignKey('invoicemanagement.Invoice', on_delete=models.CASCADE, related_name='reconciliation_records')
    payment_advice = models.ForeignKey('paymentadvice.PaymentAdvice', on_delete=models.CASCADE)
    bank_transaction = models.ForeignKey('bankmanagement.BankTransaction', on_delete=models.CASCADE)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reconciliation_date = models.DateTimeField(auto_now_add=True)
    
    # Store matching results for audit
    amount_variance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    matching_confidence = models.FloatField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)


class SchedulerConfig(models.Model):
    """Model to store scheduler configuration and status persistently"""
    
    STATUS_CHOICES = [
        ('stopped', 'Stopped'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('error', 'Error'),
    ]
    
    # Scheduler status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='stopped')
    is_enabled = models.BooleanField(default=False, help_text="Enable/disable the entire scheduler")
    
    # Job configurations
    parser_enabled = models.BooleanField(default=True, help_text="Enable bank statement parsing job")
    parser_interval = models.PositiveIntegerField(default=60, help_text="Parser interval in seconds (10-3600)")
    
    reconciliation_enabled = models.BooleanField(default=False, help_text="Enable bank reconciliation job")
    reconciliation_interval = models.PositiveIntegerField(default=60, help_text="Reconciliation interval in seconds (10-3600)")
    
    email_parser_enabled = models.BooleanField(default=False, help_text="Enable email parsing job")
    email_parser_interval = models.PositiveIntegerField(default=300, help_text="Email parser interval in seconds (10-3600)")
    
    # Scheduler metadata
    last_run = models.DateTimeField(blank=True, null=True)
    next_run = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    job_count = models.PositiveIntegerField(default=0, help_text="Total jobs executed")
    
    # Process tracking
    process_id = models.PositiveIntegerField(blank=True, null=True, help_text="Current scheduler process ID")
    host_info = models.CharField(max_length=255, blank=True, null=True, help_text="Host where scheduler is running")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Scheduler Configuration"
        verbose_name_plural = "Scheduler Configurations"
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Scheduler Config - {self.get_status_display()}"
    
    def clean(self):
        """Validate interval values"""
        from django.core.exceptions import ValidationError
        if not (10 <= self.parser_interval <= 3600):
            raise ValidationError({'parser_interval': 'Interval must be between 10 and 3600 seconds'})
        if not (10 <= self.reconciliation_interval <= 3600):
            raise ValidationError({'reconciliation_interval': 'Interval must be between 10 and 3600 seconds'})
        if not (10 <= self.email_parser_interval <= 3600):
            raise ValidationError({'email_parser_interval': 'Interval must be between 10 and 3600 seconds'})
    
    @classmethod
    def get_config(cls):
        """Get or create the scheduler configuration"""
        config, created = cls.objects.get_or_create(
            pk=1,  # Always use ID=1 for singleton pattern
            defaults={
                'status': 'stopped',
                'is_enabled': False,
                'parser_enabled': True,
                'parser_interval': 60,
                'reconciliation_enabled': False,
                'reconciliation_interval': 60,
                'email_parser_enabled': False,
                'email_parser_interval': 300,
            }
        )
        return config
    
    def get_status_dict(self):
        """Get configuration as dictionary for scheduler service"""
        return {
            'is_running': self.status == 'running',
            'is_enabled': self.is_enabled,
            'parser_enabled': self.parser_enabled,
            'parser_interval': self.parser_interval,
            'reconciliation_enabled': self.reconciliation_enabled,
            'reconciliation_interval': self.reconciliation_interval,
            'email_parser_enabled': self.email_parser_enabled,
            'email_parser_interval': self.email_parser_interval,
            'last_run': self.last_run,
            'next_run': self.next_run,
            'error_message': self.error_message,
            'job_count': self.job_count,
            'process_id': self.process_id,
            'host_info': self.host_info,
        }