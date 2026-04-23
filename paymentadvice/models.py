from django.db import models

class PaymentAdvice(models.Model):
    invoice = models.ForeignKey(
        "Invoice",
        related_name="payment_advices",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    account_no = models.CharField(max_length=50)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    subject = models.CharField(max_length=255)
    body = models.TextField()

    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_no} - {self.total_amount}"