from django.urls import path
from . import views

app_name = 'document'

urlpatterns = [
    path('upload/', views.DocumentUploadView.as_view(), name='document-upload'),
    path('', views.DocumentListView.as_view(), name='document-list'),
    path('<int:document_id>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('<int:document_id>/reprocess/', views.reprocess_document, name='document-reprocess'),
    path('<int:document_id>/delete/', views.delete_document, name='document-delete'),
    path('<int:document_id>/status/', views.processing_status, name='processing-status'),
]
