from rest_framework import serializers
from .models import PaymentAdvice


class PaymentAdviceSerializer(serializers.ModelSerializer):
    """Serializer for PaymentAdvice model"""
    
    class Meta:
        model = PaymentAdvice
        fields = '__all__'
