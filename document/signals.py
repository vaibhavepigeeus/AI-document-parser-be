from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Document


@receiver(post_save, sender=Document)
def document_created(sender, instance, created, **kwargs):
    """Signal handler for document creation"""
    if created:
        # Log document creation
        print(f"Document created: {instance.filename}")
        
        # You could trigger async processing here
        # from backend.bankmanagement.tasks import process_document_task
        # process_document_task.delay(instance.id)
