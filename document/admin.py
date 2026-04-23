from django.contrib import admin
from .models import Document, ProcessingResult, ProcessingLog


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'document_type', 'status', 'uploaded_at']
    list_filter = ['status', 'document_type', 'uploaded_at']
    search_fields = ['filename']
    readonly_fields = ['id', 'uploaded_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('filename', 'file', 'document_type')
        }),
        ('Processing Status', {
            'fields': ('status', 'error_message')
        }),
        ('Parsed Data', {
            'fields': ('parsed_data',)
        }),
    )


@admin.register(ProcessingResult)
class ProcessingResultAdmin(admin.ModelAdmin):
    list_display = ['document', 'processing_time', 'created_at']
    readonly_fields = ['document', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Document', {
            'fields': ('document',)
        }),
        ('Results', {
            'fields': ('raw_json_data', 'structured_data', 'validation_results', 'confidence_report')
        }),
        ('Metadata', {
            'fields': ('processing_time', 'processing_steps')
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_details')
        }),
    )


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ['document', 'step_name', 'status', 'duration', 'started_at']
    list_filter = ['status', 'step_name', 'started_at']
    search_fields = ['document__filename', 'step_name']
    readonly_fields = ['document', 'started_at', 'completed_at', 'duration']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('document', 'step_name', 'step_description', 'status')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration')
        }),
        ('Data', {
            'fields': ('input_data', 'output_data')
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_traceback')
        }),
    )
