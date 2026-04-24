import os
import json
import re
import pandas as pd
from typing import List, Optional, TypedDict
from datetime import datetime
from django.conf import settings
from django.db import transaction
from pydantic import BaseModel, Field, ValidationError
from PyPDF2 import PdfReader
from PIL import Image
import pytesseract

from langchain_aws import ChatBedrock 
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from invoicemanagement.models import Invoice, InvoiceLineItem
from document.models import Document, ProcessingLog


# --- 1. Data Schema ---
class InvoiceEntryData(BaseModel):
    description: str
    amt: float 

class InvoiceData(BaseModel):
    invoiceNo: Optional[str] = None
    invoicedate: Optional[str] = None
    totalAmount: Optional[float] = None
    invoice_entries: List[InvoiceEntryData] = Field(default_factory=list)

# --- 2. Graph State ---
class GraphState(TypedDict):
    file_path: str
    file_type: str  # 'text'
    content: str    # Raw extracted text only
    structured_data: Optional[InvoiceData]
    error: Optional[str]

# --- 3. The Extraction Node ---
def extract_invoice_info(state: GraphState):
    # --- AWS CREDENTIALS ---
    ACCESS_KEY = getattr(settings, 'AWS_ACCESS_KEY_ID', os.getenv('AWS_ACCESS_KEY_ID'))
    SECRET_KEY = getattr(settings, 'AWS_SECRET_ACCESS_KEY', os.getenv('AWS_SECRET_ACCESS_KEY'))
    REGION = getattr(settings, 'AWS_REGION', os.getenv('AWS_REGION', 'us-east-1'))

    if not ACCESS_KEY or not SECRET_KEY:
        return {"error": "AWS credentials not configured", "structured_data": None}

    llm = ChatBedrock(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION,
        model_kwargs={"temperature": 0, "max_tokens": 4096}
    )
    
    prompt_text = f"""
    You are an expert financial invoice extraction assistant.
    Extract structured information from the provided invoice.

    CRITICAL REQUIREMENTS:
    1. Extract invoice number and Invoice date.
    2. Extract ALL transactions found in the invoice.
    3. For EACH invoice, you MUST include: date, description, amount.
    4. Use YYYY-MM-DD format for all dates.
    5. Return ONLY valid JSON, no markdown formatting.
    6. Compute the total amount by adding the amt of each invoice entry.

    REQUIRED JSON STRUCTURE:
    {{
        "invoiceNo": "string",
        "invoicedate": "YYYY-MM-DD",
        "totalAmount": 0.00,
        "invoice_entries": [
            {{
                "description": "item description",
                "amt": 0.00
            }}
        ]
    }}


    Here is the invoice text to process:
    ---
    {state['content']}
    ---

    Return only the JSON response:"""
    
    # Always send raw extracted text to the LLM.
    message_content = [
        {"type": "text", "text": prompt_text}
    ]
    
    try:
        response = llm.invoke([HumanMessage(content=message_content)])
        raw_output = response.content
        if isinstance(raw_output, list):
            raw_output = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw_output
            )
        else:
            raw_output = str(raw_output)
        
        # Strip markdown if present
        json_str = re.sub(r"```json\s*|```\s*", "", raw_output).strip()
        data_dict = json.loads(json_str)
        
        validated_data = InvoiceData(**data_dict)
        return {"structured_data": validated_data, "error": None}
    except Exception as e:
        return {"error": f"LLM Extraction Error: {str(e)}", "structured_data": None}

# --- 4. Graph Assembly ---
workflow = StateGraph(GraphState)
workflow.add_node("extract", extract_invoice_info)
workflow.set_entry_point("extract")
workflow.add_edge("extract", END)
app = workflow.compile()

# --- 5. File Processing Logic ---
def extract_text_from_file(file_path: str) -> str:
    """Extract text content from various file formats"""
    try:
        file_ext = file_path.lower().split('.')[-1]
        
        # Handle PDF files
        if file_ext == 'pdf':
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts).strip()

        # Handle image files with OCR
        elif file_ext in ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp']:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image).strip()

        # Handle Excel/CSV files
        elif file_ext in ['xlsx', 'xls', 'csv']:
            df = pd.read_excel(file_path) if 'xls' in file_ext else pd.read_csv(file_path)
            return df.fillna('').to_string()

        # Handle text files
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
                
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")

@transaction.atomic
def save_invoice_data(document: Document, invoice_data: InvoiceData) -> Invoice:
    """Save extracted invoice data to database"""
    
    # Parse invoice date
    invoice_date = None
    if invoice_data.invoicedate:
        try:
            invoice_date = datetime.strptime(invoice_data.invoicedate, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    # Create Invoice record
    invoice = Invoice.objects.create(
        document=document,
        invoiceNo=invoice_data.invoiceNo,
        invoicedate=invoice_date,
        totalAmount=invoice_data.totalAmount,
        status='processed',
        extraction_method='langchain'
    )
    
    # Create InvoiceLineItem records
    for entry_data in invoice_data.invoice_entries:
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description=entry_data.description,
            amt=entry_data.amt
        )
    
    return invoice

def log_processing_step(document: Document, step_name: str, status: str, 
                       error_message: str = None, duration: float = None):
    """Log processing steps for debugging and monitoring"""
    ProcessingLog.objects.create(
        document=document,
        step_name=step_name,
        step_description=f"Processing step: {step_name}",
        status=status,
        started_at=datetime.now(),
        completed_at=datetime.now() if status in ['completed', 'failed'] else None,
        duration=duration,
        error_message=error_message
    )

def process_invoice_document(document: Document) -> dict:
    """
    Main function to process an invoice document
    """
    result = {
        'success': False,
        'invoice_id': None,
        'error': None,
        'entries_count': 0
    }
    
    start_time = datetime.now()
    
    try:
        # Log processing start
        log_processing_step(document, 'extraction_started', 'started')
        
        # Extract text from file
        text_content = extract_text_from_file(document.file.path)
        
        # Process with LangChain
        state_input = {"content": text_content, "file_type": 'text', "file_path": document.file.path}
        output = app.invoke(state_input)
        
        if output.get("error"):
            result['error'] = output['error']
            log_processing_step(document, 'extraction_failed', 'failed', output['error'])
            document.status = Document.StatusChoices.FAILED
            document.error_message = output['error']
            document.save()
            return result
        
        # Save to database
        invoice_data = output["structured_data"]
        invoice = save_invoice_data(document, invoice_data)
        
        # Update document status
        document.status = Document.StatusChoices.PARSED
        document.save()
        
        # Log success
        duration = (datetime.now() - start_time).total_seconds()
        log_processing_step(document, 'extraction_completed', 'completed', duration=duration)
        
        result.update({
            'success': True,
            'invoice_id': invoice.id,
            'entries_count': len(invoice_data.invoice_entries)
        })
        
    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        result['error'] = error_msg
        duration = (datetime.now() - start_time).total_seconds()
        log_processing_step(document, 'extraction_failed', 'failed', error_msg, duration)
        
        document.status = Document.StatusChoices.FAILED
        document.error_message = error_msg
        document.save()
    
    return result

# --- 6. Legacy Entry Point for Standalone Testing ---
def process_invoice_file(file_name: str):
    """Standalone function for testing purposes"""
    print(f"📂 Processing File: {file_name}...")
    
    try:
        # Extract text from file
        text_content = extract_text_from_file(file_name)
        state_input = {"content": text_content, "file_type": 'text', "file_path": file_name}

        # Run the Graph
        output = app.invoke(state_input)
        
        if output.get("error"):
            print(f"❌ Error: {output['error']}")
        else:
            data = output["structured_data"]
            print(f"✅ Success!")
            print(json.dumps(data.model_dump(), indent=2))
            
    except Exception as e:
        print(f"❌ System Error: {str(e)}")

# --- 7. Main Entry Point ---
if __name__ == "__main__":
    # Specify your invoice path here
    target_file = "invoice.pdf" 
    process_invoice_file(target_file)
