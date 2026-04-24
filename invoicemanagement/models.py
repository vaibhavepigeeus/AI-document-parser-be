from django.db import models
from document.models import Document

# Create your models here.


class Invoice(models.Model):
    invoice_no = models.CharField(max_length=50, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='invoice', null=True, blank=True)

    def __str__(self):
        return self.invoice_no or f"Invoice {self.id}"


class InvoiceLineItem(models.Model):
    invoice = models.ForeignKey(
        Invoice,
        related_name="lines",
        on_delete=models.CASCADE
    )
    description = models.TextField()
    is_matched = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    def __str__(self):
        return f"{self.invoice.invoice_no} - {self.amount}"