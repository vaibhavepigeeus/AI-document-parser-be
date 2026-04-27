from django.db import models
from django.contrib.auth.models import User
from document.models import Document


class BankStatement(models.Model):
    """Model to store bank statement information extracted from documents"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('validated', 'Validated'),
        ('error', 'Error'),
    ]
    
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='bank_statement')
    
    # Bank statement basic information
    statement_period = models.CharField(max_length=100, blank=True, null=True)
    statement_date = models.DateField(blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    account_type = models.CharField(max_length=50, blank=True, null=True)
    
    # Balance information
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=10, default='USD')
    
    # Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    confidence_score = models.FloatField(blank=True, null=True)
    extraction_method = models.CharField(max_length=50, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    account_holder_name = models.CharField(max_length=255, null=True,
        blank=True)
    number_of_txn = models.PositiveIntegerField(null=True,
        blank=True)
    total_credit_amount = models.DecimalField(max_digits=15, decimal_places=2,  null=True,
        blank=True)
    total_debit_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    def __str__(self):
        return f"Bank Statement - {self.bank_name or 'Unknown Bank'} ({self.statement_period or 'N/A'})"
    
    class Meta:
        ordering = ['-created_at']


class BankTransaction(models.Model):
    """Model to store individual bank transactions"""
    
    TRANSACTION_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('payment', 'Payment'),
        ('fee', 'Fee'),
        ('interest', 'Interest'),
        ('other', 'Other'),
    ]
    
    bank_statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='transactions')
    
    # Transaction details
    txn_no = models.CharField(max_length=100, blank=True, null=True)
    transaction_date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    # Additional fields
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    balance_after_transaction = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    payee = models.CharField(max_length=255, blank=True, null=True)
    
    # Metadata
    confidence_score = models.FloatField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    balance = models.DecimalField(max_digits=15, decimal_places=2,  null=True,
        blank=True)
    credit = models.DecimalField(max_digits=15, decimal_places=2,  null=True,
        blank=True)
    debit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    reference = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )
    total_credit_amount = models.DecimalField(max_digits=15, decimal_places=2,  null=True,
        blank=True)
    total_debit_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.transaction_type.title()} - {self.amount} ({self.transaction_date})"
    
    class Meta:
        ordering = ['-transaction_date']
