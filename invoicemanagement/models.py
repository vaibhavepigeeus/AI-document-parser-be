from django.db import models
from document.models import Document


class Invoice(models.Model):
    """Model to store invoice information extracted from documents"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('validated', 'Validated'),
        ('error', 'Error'),
    ]
    
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='invoice')
    
    # Invoice basic information
    invoiceNo = models.CharField(max_length=100, blank=True, null=True)
    invoicedate = models.DateField(blank=True, null=True)
    totalAmount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    # Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    confidence_score = models.FloatField(blank=True, null=True)
    extraction_method = models.CharField(max_length=50, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice - {self.invoiceNo or 'Unknown'} ({self.invoicedate or 'N/A'})"
    
    class Meta:
        ordering = ['-created_at']


class InvoiceEntry(models.Model):
    """Model to store individual invoice line items"""
    
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='invoice_entries')
    
    # Line item details
    description = models.TextField()
    amt = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Additional fields
    category = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    # Metadata
    confidence_score = models.FloatField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.description} - {self.amt}"
    
    class Meta:
        ordering = ['-created_at']