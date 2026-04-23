"""
Invoice parsing services converted from module_6.py
"""
import json
import logging
from typing import Dict, Any, Optional
from django.utils import timezone

from document.models import Document, ProcessingLog
from .classification import ClassificationService

logger = logging.getLogger(__name__)


class InvoiceParsingService:
    """Service for parsing invoice documents and extracting structured data"""
    
    INVOICE_PROMPT_TEMPLATE = """You are an expert invoice parser. Your task is to extract ALL structured data from the provided raw invoice text.

===============================
\u0012 LOCK CORE INSTRUCTIONS
===============================
1. Extract EVERY piece of information explicitly present in the invoice.
2. DO NOT hallucinate, infer, or guess any values.
3. If a value is not clearly present, return null.
4. DO NOT omit any fields.

===============================
\ud83d\udcd0 STRUCTURE RULES (CRITICAL)
===============================
5. Keep the JSON structure FLAT at the top level.
6. DO NOT create nested objects EXCEPT for:
   - "line_items"
   - "charges"
7. Use consistent snake_case keys.
8. ALWAYS include the required fields listed below (even if null).

===============================
\ud83d\udd25 REQUIRED STANDARD FIELDS
===============================
You MUST include these fields in every output:

- "invoice_number"
- "invoice_date"
- "due_date"

- "subtotal"
- "tax_amount"
- "shipping_amount"
- "discount_amount"

- "total_amount"

===============================
\ud83d\udcb0 NEW: CHARGES ARRAY (VERY IMPORTANT)
===============================
9. You MUST extract ALL monetary components contributing to the final total into a field called:

"charges": [
  {
    "type": "string",
    "amount": number
  }
]

RULES:
- Include ALL charges, fees, taxes, discounts, reversals
- Each entry must represent ONE monetary component
- Use NEGATIVE values for:
  - discounts
  - refunds
  - reversals
- DO NOT duplicate values
- DO NOT include subtotal as a charge if line items are already present
- Ensure:
    sum(charges.amount) == total_amount (very important)

Examples of types:
- "cab_hire"
- "driver_charges"
- "service_fee"
- "tax"
- "shipping"
- "discount"
- "reversal"

===============================
\ud83e\udde0 FLEXIBLE EXTRACTION (VERY IMPORTANT)
===============================
10. In addition to required fields:
   - Extract ALL other fields present in the invoice
   - Use meaningful snake_case keys
   - DO NOT drop any useful information

===============================
\ud83d\udcb0 FINANCIAL NORMALIZATION (CRITICAL)
===============================
11. Normalize financial fields strictly:

- "subtotal" \u2192 SUM of (quantity \u00d7 unit_price) for all items (EXCLUDING tax, shipping, discount)
- "tax_amount" \u2192 TOTAL tax for the invoice
- "shipping_amount" \u2192 delivery/shipping charges
- "discount_amount" \u2192 discount
- "total_amount" \u2192 FINAL payable amount

\ud83d\udea8 IMPORTANT RULE:
total_amount MUST satisfy:
total_amount = subtotal + tax_amount + shipping_amount - discount_amount

12. DO NOT mix tax into subtotal or unit_price.

13. If invoice shows "price including tax":
   \u2192 Extract base price into unit_price
   \u2192 Extract tax separately into tax_amount

===============================
\ud83d\udce6 LINE ITEMS (STRICT)
===============================
14. Use "line_items" as array of objects

15. Each item MUST include:
   - description
   - quantity
   - unit_price (price BEFORE tax)
   - tax_amount (tax for that item, if available else null)
   - total (quantity \u00d7 unit_price ONLY, EXCLUDING tax)

\ud83d\udea8 IMPORTANT:
- item.total MUST NOT include tax
- item.total = quantity \u00d7 unit_price

16. TAX HANDLING:
- If item-level tax exists \u2192 store in item.tax_amount
- If only invoice-level tax exists \u2192 keep item.tax_amount = null

17. DO NOT distribute tax unless explicitly shown.

===============================
\ud83d\udd22 NUMERIC RULES
===============================
18. All numeric values must be pure numbers:
   \u274c No currency symbols
   \u274c No text like "(21%)"

===============================
\ud83d\udce4 OUTPUT RULES
===============================
19. Output strictly valid JSON
20. No explanation, only JSON
21. Return ONLY ONE JSON object

===============================
\ud83d\udcc4 RAW INPUT
===============================
Raw Invoice Text:
"""
    
    def __init__(self, document: Document):
        self.document = document
        self.extracted_text = document.extracted_text or ""
    
    def parse_invoice(self) -> Dict[str, Any]:
        """
        Parse invoice and return structured JSON data
        """
        try:
            # Log parsing start
            self._log_step('invoice_parsing', 'started', 'Starting invoice parsing')
            
            if not self.extracted_text:
                raise ValueError("No text available for parsing")
            
            # Get LLM instance
            llm = self._get_llm()
            
            # Create prompt
            prompt = self.INVOICE_PROMPT_TEMPLATE + f"\n{self.extracted_text}"
            
            # Invoke LLM
            response = llm.invoke(prompt)
            content = response.content.strip()
            
            # Clean up possible markdown wrappers
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[:-3]
            
            # Parse JSON
            invoice_data = json.loads(content)
            
            # Validate and normalize the parsed data
            validated_data = self._validate_invoice_data(invoice_data)
            
            # Log parsing completion
            self._log_step('invoice_parsing', 'completed', f"Successfully parsed invoice with {len(validated_data)} fields")
            
            return validated_data
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed for invoice {self.document.id}: {e}")
            self._log_step('invoice_parsing', 'failed', f"JSON parsing failed: {str(e)}", str(e))
            raise
            
        except Exception as e:
            logger.error(f"Invoice parsing failed for document {self.document.id}: {e}")
            self._log_step('invoice_parsing', 'failed', f"Invoice parsing failed: {str(e)}", str(e))
            raise
    
    def _validate_invoice_data(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize invoice data
        """
        try:
            # Ensure required fields exist
            required_fields = [
                'invoice_number', 'invoice_date', 'due_date',
                'subtotal', 'tax_amount', 'shipping_amount', 
                'discount_amount', 'total_amount'
            ]
            
            validated_data = invoice_data.copy()
            
            # Add missing required fields with null values
            for field in required_fields:
                if field not in validated_data:
                    validated_data[field] = None
            
            # Normalize numeric fields
            numeric_fields = ['subtotal', 'tax_amount', 'shipping_amount', 'discount_amount', 'total_amount']
            for field in numeric_fields:
                if validated_data[field] is not None:
                    try:
                        # Convert to float, removing any currency symbols or formatting
                        value = str(validated_data[field]).replace('$', '').replace(',', '').strip()
                        validated_data[field] = float(value)
                    except (ValueError, TypeError):
                        validated_data[field] = None
            
            # Validate line items if present
            if 'line_items' in validated_data and isinstance(validated_data['line_items'], list):
                validated_line_items = []
                for item in validated_data['line_items']:
                    if isinstance(item, dict):
                        # Ensure required item fields
                        item_fields = ['description', 'quantity', 'unit_price', 'tax_amount', 'total']
                        validated_item = item.copy()
                        
                        for field in item_fields:
                            if field not in validated_item:
                                validated_item[field] = None
                        
                        # Normalize numeric item fields
                        item_numeric_fields = ['quantity', 'unit_price', 'tax_amount', 'total']
                        for field in item_numeric_fields:
                            if validated_item[field] is not None:
                                try:
                                    value = str(validated_item[field]).replace('$', '').replace(',', '').strip()
                                    validated_item[field] = float(value)
                                except (ValueError, TypeError):
                                    validated_item[field] = None
                        
                        validated_line_items.append(validated_item)
                
                validated_data['line_items'] = validated_line_items
            
            # Validate charges array if present
            if 'charges' in validated_data and isinstance(validated_data['charges'], list):
                validated_charges = []
                for charge in validated_data['charges']:
                    if isinstance(charge, dict):
                        # Ensure required charge fields
                        charge_fields = ['type', 'amount']
                        validated_charge = charge.copy()
                        
                        for field in charge_fields:
                            if field not in validated_charge:
                                validated_charge[field] = None
                        
                        # Normalize amount
                        if validated_charge['amount'] is not None:
                            try:
                                value = str(validated_charge['amount']).replace('$', '').replace(',', '').strip()
                                validated_charge['amount'] = float(value)
                            except (ValueError, TypeError):
                                validated_charge['amount'] = None
                        
                        validated_charges.append(validated_charge)
                
                validated_data['charges'] = validated_charges
            
            return validated_data
            
        except Exception as e:
            logger.error(f"Data validation failed: {e}")
            # Return original data if validation fails
            return invoice_data
    
    def _get_llm(self):
        """Get LLM instance (reuse classification service method)"""
        classification_service = ClassificationService(self.document)
        return classification_service._get_llm()
    
    def _log_step(self, step_name: str, status: str, description: str, error_message: str = None):
        """Log processing step"""
        try:
            ProcessingLog.objects.create(
                document=self.document,
                step_name=step_name,
                step_description=description,
                status=status,
                started_at=timezone.now(),
                error_message=error_message
            )
        except Exception as e:
            logger.error(f"Failed to log processing step: {e}")


def parse_invoice(document: Document) -> Dict[str, Any]:
    """
    Convenience function to parse an invoice document
    """
    service = InvoiceParsingService(document)
    return service.parse_invoice()
