from rest_framework import serializers
from document.models import ProcessingResult
from .models import BankStatement, BankTransaction


class ProcessingResultSerializer(serializers.ModelSerializer):
    """Serializer for ProcessingResult model"""
    
    class Meta:
        model = ProcessingResult
        fields = [
            'raw_json_data', 'structured_data', 'validation_results',
            'confidence_report', 'processing_time', 'processing_steps',
            'error_message', 'error_details', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class ProcessingSummarySerializer(serializers.Serializer):
    """Serializer for processing summary"""
    document_id = serializers.IntegerField()
    original_filename = serializers.CharField()
    file_type = serializers.CharField()
    status = serializers.CharField()
    uploaded_at = serializers.DateTimeField()
    processed_at = serializers.DateTimeField(allow_null=True)
    document_type = serializers.CharField(allow_null=True)
    confidence_score = serializers.FloatField(allow_null=True)
    processing_time = serializers.FloatField(allow_null=True)
    has_structured_data = serializers.BooleanField()
    validation_passed = serializers.BooleanField(allow_null=True)
    final_confidence_score = serializers.FloatField(allow_null=True)
    risk_level = serializers.CharField(allow_null=True)


class BankTransactionSerializer(serializers.ModelSerializer):
    """Serializer for BankTransaction model"""
    
    class Meta:
        model = BankTransaction
        fields = [
            'id', 'txn_no', 'transaction_date', 'description', 'amount',
            'transaction_type', 'reference_number', 'balance_after_transaction',
            'category', 'payee', 'confidence_score', 'created_at', 'updated_at',
            'balance', 'credit', 'debit', 'reference', 'total_credit_amount', 'total_debit_amount'
        ]


class BankStatementSerializer(serializers.ModelSerializer):
    """Serializer for BankStatement model"""
    
    class Meta:
        model = BankStatement
        fields = [
            'id', 'document', 'statement_period', 'statement_date', 'bank_name',
            'account_number', 'account_type', 'opening_balance', 'closing_balance',
            'currency', 'status', 'confidence_score', 'extraction_method',
            'created_at', 'updated_at', 'account_holder_name', 'number_of_txn',
            'total_credit_amount', 'total_debit_amount'
        ]


class BankStatementDetailsSerializer(serializers.Serializer):
    """Flattened serializer for BankStatement with transaction details"""
    Account = serializers.CharField(source='account_number', read_only=True)
    Transaction = serializers.CharField(source='description', read_only=True)
    Date = serializers.DateField(source='transaction_date', read_only=True)
    Amount = serializers.DecimalField(source='amount', max_digits=15, decimal_places=2, read_only=True)
    Total = serializers.DecimalField(source='total_receivable_amt', max_digits=15, decimal_places=2, read_only=True)
    Ageing = serializers.SerializerMethodField()
    
    # Additional statement fields for context
    statement_id = serializers.IntegerField(read_only=True)
    bank_name = serializers.CharField(read_only=True)
    statement_period = serializers.CharField(read_only=True)
    transaction_type = serializers.CharField(read_only=True)
    
    def get_Ageing(self, obj):
        """Calculate ageing based on transaction date"""
        if hasattr(obj, 'transaction_date') and obj.transaction_date:
            from datetime import date
            today = date.today()
            delta = today - obj.transaction_date
            return delta.days
        return None
    
    def to_representation(self, instance):
        """Handle both BankStatement and BankTransaction objects"""
        if isinstance(instance, BankStatement):
            # For statement objects, return statement-level data
            return {
                'Account': instance.account_number,
                'Transaction': None,
                'Date': instance.statement_date,
                'Amount': None,
                'Total': instance.total_receivable_amt,
                'Ageing': None,
                'statement_id': instance.id,
                'bank_name': instance.bank_name,
                'statement_period': instance.statement_period,
                'transaction_type': None
            }
        else:
            # For transaction objects, return transaction-level data
            return super().to_representation(instance)
