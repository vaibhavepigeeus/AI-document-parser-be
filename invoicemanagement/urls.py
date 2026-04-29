from django.urls import path
from . import views

app_name = 'invoicemanagement'

urlpatterns = [
    path('list/', views.InvoiceListView.as_view(), name='invoice-list'),
]
