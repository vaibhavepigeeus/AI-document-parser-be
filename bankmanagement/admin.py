from django.contrib import admin
from .models import BankStatement, BankTransaction


class BankTransactionInline(admin.TabularInline):
    model = BankTransaction
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'statement_period', 'account_number', 'closing_balance', 'currency', 'status', 'created_at']
    list_filter = ['status', 'currency', 'bank_name', 'created_at']
    search_fields = ['bank_name', 'account_number', 'statement_period']
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [BankTransactionInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('document', 'user', 'bank_name', 'statement_period', 'statement_date')
        }),
        ('Account Information', {
            'fields': ('account_number', 'account_type')
        }),
        ('Balance Information', {
            'fields': ('opening_balance', 'closing_balance', 'currency')
        }),
        ('Metadata', {
            'fields': ('status', 'confidence_score', 'extraction_method')
        }),
        ('System Information', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ['bank_statement', 'transaction_date', 'description', 'amount', 'transaction_type', 'created_at']
    list_filter = ['transaction_type', 'transaction_date', 'created_at']
    search_fields = ['description', 'reference_number', 'payee']
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('bank_statement', 'transaction_date', 'description', 'amount', 'transaction_type')
        }),
        ('Additional Information', {
            'fields': ('reference_number', 'balance_after_transaction', 'category', 'payee')
        }),
        ('Metadata', {
            'fields': ('confidence_score',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
