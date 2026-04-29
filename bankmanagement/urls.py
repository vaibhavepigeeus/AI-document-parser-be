from django.urls import path
from . import views

app_name = 'bankmanagement'

urlpatterns = [
    path('statements/', views.BankStatementListCreateView.as_view(), name='bank-statement-list-create'),
    path('statements/details/', views.BankStatementDetailsListView.as_view(), name='bank-statement-details-list'),
]
