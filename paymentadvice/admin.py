from django.contrib import admin
from .models import PaymentAdvice


@admin.register(PaymentAdvice)
class PaymentAdviceAdmin(admin.ModelAdmin):
    list_display = [
        'payment_invoice_no', 
        'total_received_amount', 
        'payment_currency', 
        'payment_date', 
        'is_matched', 
        'email_date',
        'created_at'
    ]
    list_filter = [
        'is_matched', 
        'payment_currency', 
        'payment_date',
        'email_date',
        'created_at'
    ]
    search_fields = [
        'payment_invoice_no'
    ]
    readonly_fields = [
        'created_at'
    ]
    ordering = ['-created_at']
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_invoice_no', 'total_received_amount', 'payment_currency', 'payment_date')
        }),
        ('Status', {
            'fields': ('is_matched',)
        }),
        ('Additional Data', {
            'fields': ('extra_data', 'email_date'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
