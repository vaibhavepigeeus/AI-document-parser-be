from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from .bankparser import process_bank_statement_document, process_invoice_document
from document.models import Document

def process_unprocessed_documents():
    """Check for unprocessed documents and trigger appropriate processing"""
    print(f"🔍 Checking for unprocessed documents at {timezone.now()}")
    
    # Get all uploaded documents that haven't been processed
    unprocessed_docs = Document.objects.filter(
        status=Document.StatusChoices.UPLOADED
    )
    
    if not unprocessed_docs.exists():
        print("📋 No unprocessed documents found")
        return
    
    print(f"📁 Found {unprocessed_docs.count()} unprocessed documents")
    
    for document in unprocessed_docs:
        print(f"🔄 Processing: {document.filename} ({document.document_type})")
        
        try:
            if document.document_type == Document.DocumentType.BANK_STATEMENT:
                success = process_bank_statement_document(document.id)
            elif document.document_type == Document.DocumentType.INVOICE:
                success = process_invoice_document(document.id)
            else:
                print(f"⚠️ Unknown document type: {document.document_type}")
                continue
                
            if success:
                print(f"✅ Successfully processed: {document.filename}")
            else:
                print(f"❌ Failed to process: {document.filename}")
                
        except Exception as e:
            print(f"💥 Error processing {document.filename}: {str(e)}")
            # Update document status to failed
            document.status = Document.StatusChoices.FAILED
            document.error_message = str(e)
            document.save()

def run():
    """Start the unified scheduler"""
    print("🔧 Initializing scheduler...")
    scheduler = BackgroundScheduler()
    
    # Add job to process unprocessed documents every 2 minutes
    scheduler.add_job(
        process_unprocessed_documents,
        "interval",
        seconds=60,
        name="Process Unprocessed Documents"
    )

    
    print("🚀 Starting unified document processing scheduler...")
    print("⏰ Scheduler will check for documents every 2 minutes")
    scheduler.start()
    print("✅ Scheduler started successfully!")
