from django.urls import path
from .views import PaymentAdviceListCreateView

urlpatterns = [
    path('advice/', PaymentAdviceListCreateView.as_view(), name='payment-advice-list-create'),
]
