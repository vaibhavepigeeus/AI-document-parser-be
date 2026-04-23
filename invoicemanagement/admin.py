from django.contrib import admin
from .models import Invoice, InvoiceLineItem


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_no', 'invoice_date', 'total_amount']
    search_fields = ['invoice_no']
    inlines = [InvoiceLineItemInline]


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'description', 'amount', 'is_matched']
    search_fields = ['description', 'invoice__invoice_no']
