from django.contrib import admin
from .models import Invoice, InvoiceLineItem


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoiceNo', 'invoicedate', 'totalAmount', 'status']
    search_fields = ['invoiceNo']
    inlines = [InvoiceLineItemInline]


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'description', 'amt', 'category']
    search_fields = ['description', 'invoice__invoiceNo']
