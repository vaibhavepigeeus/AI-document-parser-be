from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import SimpleUploadedFile
from document.models import Document
from bankmanagement.models import BankStatement
from invoicemanagement.models import Invoice
import os

class Command(BaseCommand):
    help = 'Test the complete document processing workflow'

    def handle(self, *args, **options):
        self.stdout.write('🧪 Testing document processing workflow...')
        
        # Test 1: Create a sample bank statement document
        self.stdout.write('\n📊 Test 1: Creating sample bank statement document...')
        
        # Create a simple CSV content for testing
        csv_content = """Date,Description,Debit,Credit,Balance
2024-01-01,Opening Balance,,1000.00,1000.00
2024-01-02,Coffee Shop,5.50,,994.50
2024-01-03,Salary,,1500.00,2494.50
2024-01-04,Rent Payment,800.00,,1694.50"""
        
        uploaded_file = SimpleUploadedFile(
            "test_bank_statement.csv",
            csv_content.encode('utf-8'),
            content_type="text/csv"
        )
        
        bank_doc = Document.objects.create(
            file=uploaded_file,
            filename="test_bank_statement.csv",
            document_type=Document.DocumentType.BANK_STATEMENT,
            status=Document.StatusChoices.UPLOADED
        )
        
        self.stdout.write(f'✅ Created bank statement document: {bank_doc.id}')
        
        # Test 2: Create a sample invoice document
        self.stdout.write('\n📄 Test 2: Creating sample invoice document...')
        
        invoice_content = """Invoice #INV-001
Date: 2024-01-15

Item 1 - $100.00
Item 2 - $150.00
Item 3 - $75.00

Total: $325.00"""
        
        uploaded_invoice = SimpleUploadedFile(
            "test_invoice.txt",
            invoice_content.encode('utf-8'),
            content_type="text/plain"
        )
        
        invoice_doc = Document.objects.create(
            file=uploaded_invoice,
            filename="test_invoice.txt",
            document_type=Document.DocumentType.INVOICE,
            status=Document.StatusChoices.UPLOADED
        )
        
        self.stdout.write(f'✅ Created invoice document: {invoice_doc.id}')
        
        # Test 3: Check initial state
        self.stdout.write('\n📊 Test 3: Checking initial state...')
        uploaded_count = Document.objects.filter(status=Document.StatusChoices.UPLOADED).count()
        self.stdout.write(f'📋 Documents uploaded: {uploaded_count}')
        
        # Test 4: Manually trigger processing
        self.stdout.write('\n🔄 Test 4: Triggering document processing...')
        
        try:
            from bankmanagement.scheduler import process_unprocessed_documents
            process_unprocessed_documents()
            self.stdout.write('✅ Processing triggered successfully')
        except ImportError as e:
            self.stdout.write(self.style.WARNING(f'⚠️ Scheduler not available: {e}'))
            return
        
        # Test 5: Check final state
        self.stdout.write('\n📊 Test 5: Checking final state...')
        
        # Check document statuses
        final_uploaded = Document.objects.filter(status=Document.StatusChoices.UPLOADED).count()
        final_parsed = Document.objects.filter(status=Document.StatusChoices.PARSED).count()
        final_failed = Document.objects.filter(status=Document.StatusChoices.FAILED).count()
        
        self.stdout.write(f'📋 Final state - Uploaded: {final_uploaded}, Parsed: {final_parsed}, Failed: {final_failed}')
        
        # Check if related models were created
        bank_statements = BankStatement.objects.count()
        invoices = Invoice.objects.count()
        
        self.stdout.write(f'💼 Bank statements created: {bank_statements}')
        self.stdout.write(f'🧾 Invoices created: {invoices}')
        
        # Test 6: Show document details
        self.stdout.write('\n📋 Test 6: Document details...')
        
        for doc in Document.objects.all():
            self.stdout.write(f'📄 {doc.filename}: {doc.status}')
            if doc.error_message:
                self.stdout.write(f'   ❌ Error: {doc.error_message}')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Workflow test completed!'))
