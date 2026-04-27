from django.db import models

class PaymentAdvice(models.Model):
    payment_invoice_no = models.CharField(max_length=50, null=True, blank=True)
    total_received_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    payment_currency = models.CharField(max_length=50, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    is_matched = models.BooleanField(default=False)
    extra_data = models.JSONField(null=True, blank=True)
    email_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)