from django.urls import path
from . import views_bank

app_name = 'bankmanagement'

urlpatterns = [
    path('statements/', views_bank.BankStatementListCreateView.as_view(), name='bank-statement-list-create'),
    path('statements/<uuid:pk>/', views_bank.BankStatementDetailView.as_view(), name='bank-statement-detail'),
    path('statements/document/<uuid:document_id>/summary/', views_bank.bank_statement_summary, name='bank-statement-summary'),
    path('statements/document/<uuid:document_id>/create/', views_bank.create_bank_statement_from_document, name='create-bank-statement-from-document'),
]
