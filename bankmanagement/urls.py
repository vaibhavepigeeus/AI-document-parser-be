from django.urls import path
from . import views

app_name = 'bankmanagement'

urlpatterns = [
    path('<uuid:document_id>/process/', views.process_document, name='process-document'),
    path('<uuid:document_id>/result/', views.ProcessingResultView.as_view(), name='processing-result'),
    path('<uuid:document_id>/summary/', views.processing_summary, name='processing-summary'),
]
