from rest_framework import serializers
from .models import BankStatement, BankTransaction


class BankTransactionSerializer(serializers.ModelSerializer):
    """Serializer for BankTransaction model"""
    
    class Meta:
        model = BankTransaction
        fields = [
            'id', 'transaction_date', 'description', 'amount', 'transaction_type',
            'reference_number', 'balance_after_transaction', 'category', 'payee',
            'confidence_score', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BankStatementSerializer(serializers.ModelSerializer):
    """Serializer for BankStatement model"""
    transactions = BankTransactionSerializer(many=True, read_only=True)
    
    class Meta:
        model = BankStatement
        fields = [
            'id', 'document', 'user', 'bank_name', 'statement_period', 'statement_date',
            'account_number', 'account_type', 'opening_balance', 'closing_balance',
            'currency', 'status', 'confidence_score', 'extraction_method',
            'created_at', 'updated_at', 'transactions'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'transactions']


class BankStatementCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating BankStatement with transactions"""
    transactions = BankTransactionSerializer(many=True, required=False)
    
    class Meta:
        model = BankStatement
        fields = [
            'document', 'bank_name', 'statement_period', 'statement_date',
            'account_number', 'account_type', 'opening_balance', 'closing_balance',
            'currency', 'status', 'confidence_score', 'extraction_method', 'transactions'
        ]
    
    def create(self, validated_data):
        transactions_data = validated_data.pop('transactions', [])
        bank_statement = BankStatement.objects.create(**validated_data)
        
        for transaction_data in transactions_data:
            BankTransaction.objects.create(bank_statement=bank_statement, **transaction_data)
        
        return bank_statement


class BankStatementSummarySerializer(serializers.Serializer):
    """Serializer for bank statement summary information"""
    statement_id = serializers.IntegerField()
    bank_name = serializers.CharField()
    statement_period = serializers.CharField()
    closing_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    currency = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    transaction_count = serializers.IntegerField()
    confidence_score = serializers.FloatField(allow_null=True)
