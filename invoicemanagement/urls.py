from django.urls import path
from . import views

app_name = 'invoicemanagement'

urlpatterns = [
    path('', views.InvoiceListCreateView.as_view(), name='invoice-list-create'),
    path('<uuid:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),
    path('document/<uuid:document_id>/summary/', views.invoice_summary, name='invoice-summary'),
    path('document/<uuid:document_id>/create/', views.create_invoice_from_document, name='create-invoice-from-document'),
]
