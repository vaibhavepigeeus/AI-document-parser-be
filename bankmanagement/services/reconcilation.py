import logging
from django.db.models import Q
from decimal import Decimal
from document.models import Reconciliation
from invoicemanagement.models import Invoice
from paymentadvice.models import PaymentAdvice
from bankmanagement.models import BankTransaction
 
logger = logging.getLogger('bankmanagement.services.reconcilation')
 
def run_reconcilation():
    """
    Run reconciliation between bank statements and invoices.
    This function is called by scheduler at regular intervals.
 
    Reconciliation process:
    1. Match invoice amount with the payment advice amount based on the invoice number
       - invoice.totalAmount with paymentadvice.total_received_amount and paymentadvice.payment_invoice_no with invoice.invoiceNo
 
    2. Match payment advice amount with bank statement amount +/- 25$ 
       - paymentadvice.total_received_amount with BankTransaction.amount
 
    If both conditions pass, reconciliation is successful and we create a Reconciliation record.
    """
 
    print("RECONCILIATION FUNCTION CALLED!")  # Debug print
    logger.info("Starting reconciliation process")
 
    # Get all invoices that haven't been reconciled yet
    unreconciled_invoices = Invoice.objects.filter(
        reconciliation_status='unreconciled'
    )
 
    total_invoices = Invoice.objects.count()
    logger.info(f"Found {len(unreconciled_invoices)} unreconciled invoices out of {total_invoices} total invoices")
 
    reconciliations_created = 0
    reconciliations_failed = 0
 
    for invoice in unreconciled_invoices:
        if not invoice.invoiceNo or not invoice.totalAmount:
            logger.warning(f"Skipping invoice {invoice.id} - missing invoice number or amount")
            continue
 
        logger.info(f"Processing invoice {invoice.invoiceNo} (ID: {invoice.id}) - Amount: {invoice.totalAmount}")
 
        # Step 1: Find matching payment advice
        matching_payment_advice = PaymentAdvice.objects.filter(
            payment_invoice_no=invoice.invoiceNo,
            total_received_amount=invoice.totalAmount
        ).first()
 
        if not matching_payment_advice:
            # No matching payment advice found
            logger.warning(f"No payment advice found for invoice {invoice.invoiceNo}")
            reconciliations_failed += 1
            continue
 
        # Step 2: Find matching bank transaction (amount +/- $25)
        amount_variance = Decimal('25.00')
        min_amount = matching_payment_advice.total_received_amount - amount_variance
        max_amount = matching_payment_advice.total_received_amount + amount_variance
 
        matching_bank_transaction = BankTransaction.objects.filter(
            amount__gte=min_amount,
            amount__lte=max_amount
        ).first()
 
        if not matching_bank_transaction:
            # No matching bank transaction found
            logger.warning(f"No bank transaction found for payment advice {matching_payment_advice.id} within ±$25 variance")
            reconciliations_failed += 1
            continue
 
        # Both matches found - create reconciliation record
        variance = abs(matching_bank_transaction.amount - matching_payment_advice.total_received_amount)
 
        # Check if reconciliation already exists
        existing_reconciliation = Reconciliation.objects.filter(
            invoice=invoice,
            payment_advice=matching_payment_advice,
            bank_transaction=matching_bank_transaction
        ).first()
 
        if existing_reconciliation:
            # Update existing reconciliation
            existing_reconciliation.status = 'matched'
            existing_reconciliation.amount_variance = variance
            existing_reconciliation.matching_confidence = 1.0 if variance == 0 else 0.8
            existing_reconciliation.save()
            logger.info(f"Updated existing reconciliation {existing_reconciliation.id} for invoice {invoice.invoiceNo}")
        else:
            # Create new reconciliation record
            reconciliation = Reconciliation.objects.create(
                invoice=invoice,
                payment_advice=matching_payment_advice,
                bank_transaction=matching_bank_transaction,
                status='matched',
                amount_variance=variance,
                matching_confidence=1.0 if variance == 0 else 0.8,
                notes=f"Auto-reconciled: Invoice {invoice.invoiceNo} matched with payment advice and bank transaction"
            )
            logger.info(f"Created new reconciliation {reconciliation.id} for invoice {invoice.invoiceNo}")
 
        # Update invoice reconciliation status and link
        invoice.reconciliation_status = 'matched'
        invoice.reconciliation = reconciliation if 'reconciliation' in locals() else existing_reconciliation
        invoice.save()
        logger.info(f"Updated invoice {invoice.invoiceNo} status to 'matched'")
 
        reconciliations_created += 1
 
    # Handle failed reconciliations - create records for manual review
    failed_invoices = unreconciled_invoices.exclude(
        invoiceNo__in=PaymentAdvice.objects.filter(
            total_received_amount__in=[inv.totalAmount for inv in unreconciled_invoices if inv.totalAmount]
        ).values_list('payment_invoice_no', flat=True)
    )
 
    for failed_invoice in failed_invoices:
        if failed_invoice.invoiceNo and failed_invoice.totalAmount:
            # Only create reconciliation record if we don't have one already
            existing_failed_reconciliation = Reconciliation.objects.filter(invoice=failed_invoice).first()
 
            if not existing_failed_reconciliation:
                # Don't create reconciliation record for failed cases - just update invoice status
                logger.warning(f"No matching payment advice found for invoice {failed_invoice.invoiceNo}")
 
            # Update invoice reconciliation status (but don't link to reconciliation record)
            failed_invoice.reconciliation_status = 'manual_review'
            failed_invoice.reconciliation = None  # Explicitly set to null
            failed_invoice.save()
            logger.info(f"Set invoice {failed_invoice.invoiceNo} to manual review status")
 
    result = {
        'reconciliations_created': reconciliations_created,
        'reconciliations_failed': reconciliations_failed,
        'total_processed': len(unreconciled_invoices)
    }
 
    logger.info(f"Reconciliation completed: {result}")