from django.db.models.signals import post_save
from django.dispatch import receiver
from document.models import Document


@receiver(post_save, sender=Document)
def document_created(sender, instance, created, **kwargs):
    """Signal handler for document creation"""
    if created:
        print(f"Document created: {instance.filename}")
        # You can trigger processing logic here
