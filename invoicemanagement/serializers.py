from rest_framework import serializers
from .models import Invoice, InvoiceLineItem


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    """Serializer for InvoiceLineItem model"""
    
    class Meta:
        model = InvoiceLineItem
        fields = [
            'id', 'description', 'amt', 'category', 'quantity', 'unit_price',
            'confidence_score', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model with nested line items"""
    lines = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'document', 'invoiceNo', 'invoicedate', 'totalAmount',
            'status', 'confidence_score', 'extraction_method',
            'created_at', 'updated_at', 'reconciliation_status', 'reconciliation', 'lines'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_lines(self, obj):
        """Get line items for this invoice"""
        line_items = obj.invoice_entries.all()
        return InvoiceLineItemSerializer(line_items, many=True).data


class InvoiceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Invoice with line items"""
    line_items = InvoiceLineItemSerializer(many=True, required=False)
    
    class Meta:
        model = Invoice
        fields = [
            'document', 'invoiceNo', 'invoicedate', 'totalAmount',
            'status', 'confidence_score', 'extraction_method'
        ]
    
    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items', [])
        invoice = Invoice.objects.create(**validated_data)
        
        for line_item_data in line_items_data:
            InvoiceLineItem.objects.create(invoice=invoice, **line_item_data)
        
        return invoice


class InvoiceSummarySerializer(serializers.Serializer):
    """Serializer for invoice summary information"""
    invoice_id = serializers.IntegerField()
    invoice_number = serializers.CharField()
    vendor_name = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    currency = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    line_item_count = serializers.IntegerField()
    confidence_score = serializers.FloatField(allow_null=True)
