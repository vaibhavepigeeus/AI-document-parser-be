from django.core.management.base import BaseCommand
from document.models import Document
from bankmanagement.scheduler import process_unprocessed_documents

class Command(BaseCommand):
    help = 'Manually trigger document processing'

    def handle(self, *args, **options):
        self.stdout.write('🔄 Manually triggering document processing...')
        
        # Get counts before processing
        uploaded_count = Document.objects.filter(status=Document.StatusChoices.UPLOADED).count()
        parsed_count = Document.objects.filter(status=Document.StatusChoices.PARSED).count()
        failed_count = Document.objects.filter(status=Document.StatusChoices.FAILED).count()
        
        self.stdout.write(f'📊 Before processing: {uploaded_count} uploaded, {parsed_count} parsed, {failed_count} failed')
        
        # Process documents
        process_unprocessed_documents()
        
        # Get counts after processing
        uploaded_count_after = Document.objects.filter(status=Document.StatusChoices.UPLOADED).count()
        parsed_count_after = Document.objects.filter(status=Document.StatusChoices.PARSED).count()
        failed_count_after = Document.objects.filter(status=Document.StatusChoices.FAILED).count()
        
        self.stdout.write(f'📊 After processing: {uploaded_count_after} uploaded, {parsed_count_after} parsed, {failed_count_after} failed')
        self.stdout.write(self.style.SUCCESS('✅ Document processing completed'))
