from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import redirect
from django.http import HttpResponseRedirect

from .models import Document, ProcessingResult, ProcessingLog, Reconciliation, SchedulerConfig


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


@admin.register(Reconciliation)
class ReconciliationAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'payment_advice', 'bank_transaction', 'status', 'reconciliation_date', 'amount_variance']
    list_filter = ['status', 'reconciliation_date']
    search_fields = ['invoice__invoiceNo', 'payment_advice__payment_invoice_no', 'notes']
    readonly_fields = ['id', 'reconciliation_date']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('invoice', 'payment_advice', 'bank_transaction', 'status')
        }),
        ('Reconciliation Details', {
            'fields': ('reconciliation_date', 'amount_variance', 'matching_confidence')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'invoice', 'payment_advice', 'bank_transaction'
        )


@admin.register(SchedulerConfig)
class SchedulerConfigAdmin(admin.ModelAdmin):
    list_display = ['status_display', 'is_enabled', 'parser_enabled', 'reconciliation_enabled', 'email_parser_enabled', 'last_run', 'updated_at']
    list_filter = ['status', 'is_enabled', 'parser_enabled', 'reconciliation_enabled', 'email_parser_enabled']
    search_fields = ['host_info', 'error_message']
    readonly_fields = ['id', 'created_at', 'updated_at', 'job_count', 'process_id', 'host_info']
    
    # Only allow one record (singleton pattern)
    def has_add_permission(self, request):
        # Only allow adding if no config exists
        return not SchedulerConfig.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Never allow deletion
        return False
    
    def changelist_view(self, request, extra_context=None):
        # Redirect to the single object if it exists
        config = SchedulerConfig.get_config()
        return HttpResponseRedirect(f'/admin/document/schedulerconfig/{config.pk}/change/')
    
    def status_display(self, obj):
        colors = {
            'running': 'green',
            'stopped': 'red',
            'paused': 'orange',
            'error': 'red'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    fieldsets = (
        ('Scheduler Control', {
            'fields': ('status', 'is_enabled'),
            'description': 'Control the overall scheduler status and enable/disable it.'
        }),
        ('Job Configuration', {
            'fields': (
                'parser_enabled', 'parser_interval',
                'reconciliation_enabled', 'reconciliation_interval',
                'email_parser_enabled', 'email_parser_interval'
            ),
            'description': 'Configure individual jobs and their execution intervals.'
        }),
        ('Runtime Information', {
            'fields': ('last_run', 'next_run', 'job_count', 'process_id', 'host_info'),
            'classes': ('collapse',),
            'description': 'Information about scheduler execution and performance.'
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',),
            'description': 'Error details if scheduler encounters issues.'
        }),
        ('System Information', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    actions = ['start_scheduler', 'stop_scheduler', 'restart_scheduler', 'clear_errors']
    
    def start_scheduler(self, request, queryset):
        """Start the scheduler"""
        try:
            from bankmanagement.services.scheduler import start_scheduler
            config = SchedulerConfig.get_config()
            success = start_scheduler()
            if success:
                config.status = 'running'
                config.save()
                self.message_user(request, 'Scheduler started successfully', messages.SUCCESS)
            else:
                self.message_user(request, 'Failed to start scheduler', messages.ERROR)
        except Exception as e:
            self.message_user(request, f'Error starting scheduler: {str(e)}', messages.ERROR)
    start_scheduler.short_description = 'Start Scheduler'
    
    def stop_scheduler(self, request, queryset):
        """Stop the scheduler"""
        try:
            from bankmanagement.services.scheduler import stop_scheduler
            config = SchedulerConfig.get_config()
            success = stop_scheduler()
            if success:
                config.status = 'stopped'
                config.save()
                self.message_user(request, 'Scheduler stopped successfully', messages.SUCCESS)
            else:
                self.message_user(request, 'Failed to stop scheduler', messages.ERROR)
        except Exception as e:
            self.message_user(request, f'Error stopping scheduler: {str(e)}', messages.ERROR)
    stop_scheduler.short_description = 'Stop Scheduler'
    
    def restart_scheduler(self, request, queryset):
        """Restart the scheduler"""
        try:
            from bankmanagement.services.scheduler import restart_scheduler
            config = SchedulerConfig.get_config()
            success = restart_scheduler()
            if success:
                config.status = 'running'
                config.save()
                self.message_user(request, 'Scheduler restarted successfully', messages.SUCCESS)
            else:
                self.message_user(request, 'Failed to restart scheduler', messages.ERROR)
        except Exception as e:
            self.message_user(request, f'Error restarting scheduler: {str(e)}', messages.ERROR)
    restart_scheduler.short_description = 'Restart Scheduler'
    
    def clear_errors(self, request, queryset):
        """Clear error messages"""
        updated = queryset.update(error_message='')
        self.message_user(request, f'Cleared errors from {updated} scheduler configuration(s)', messages.SUCCESS)
    clear_errors.short_description = 'Clear Error Messages'
    
    def save_model(self, request, obj, form, change):
        """Override save to update scheduler when configuration changes"""
        super().save_model(request, obj, form, change)
        
        # If scheduler is running and configuration changed, restart it
        if change and obj.status == 'running':
            try:
                from bankmanagement.services.scheduler import restart_scheduler
                restart_scheduler()
                messages.info(request, 'Scheduler restarted to apply configuration changes')
            except Exception as e:
                messages.warning(request, f'Configuration saved but failed to restart scheduler: {str(e)}')
