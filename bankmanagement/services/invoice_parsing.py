import os
import json
import re
import pandas as pd
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field, ValidationError
from PyPDF2 import PdfReader
from PIL import Image
import pytesseract
from datetime import datetime

# LangChain / AWS Imports
from langchain_aws import ChatBedrock 
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

# Django imports
from django.conf import settings
from django.db import transaction
from document.models import Document, ProcessingLog
from invoicemanagement.models import Invoice, InvoiceLineItem

# --- 1. Data Schema ---
class InvoiceEntry(BaseModel):
    description: str
    amt: float 

class InvoiceData(BaseModel):
    invoiceNo: Optional[str] = None
    invoicedate: Optional[str] = None
    totalAmount: Optional[float] = None
    invoice_entries: List[InvoiceEntry] = Field(default_factory=list)

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
    Extract structured information from provided invoice.

    CRITICAL REQUIREMENTS:
    1. Extract invoice number and Invoice date.
    2. Extract ALL transactions found in invoice.
    3. For EACH invoice, you MUST include: date, description, amount.
    4. Use YYYY-MM-DD format for all dates.
    5. Return ONLY valid JSON, no markdown formatting.
    6. Compute total amount by adding amt of each invoice entry.

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


    Here is invoice text to process:
    ---
    {state['content']}
    ---

    Return only the JSON response:"""
    
    # Always send raw extracted text to LLM.
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
    file_ext = file_path.lower().split('.')[-1]
    
    try:
        # 1. Handle PDF with PyPDF2 and extract raw text
        if file_ext == 'pdf':
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts).strip()

        # 2. Handle images with pytesseract OCR and extract raw text
        elif file_ext in ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp']:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image).strip()

        # 3. Handle Structured Data (Excel/CSV as text) via pandas
        elif file_ext in ['xlsx', 'xls', 'csv']:
            df = pd.read_excel(file_path) if 'xls' in file_ext else pd.read_csv(file_path)
            return df.fillna('').to_string()

        # 4. Handle Raw Text
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")

def process_invoice_file(file_path: str):
    """Process invoice file and return structured data"""
    print(f"📂 Processing File: {file_path}...")
    
    try:
        # Extract text content
        text_content = extract_text_from_file(file_path)
        
        if not text_content.strip():
            raise ValueError("No text content extracted from file")
        
        # Prepare state for graph
        state_input = {
            "content": text_content, 
            "file_type": 'text', 
            "file_path": file_path
        }

        # Run Graph
        output = app.invoke(state_input)
        
        if output.get("error"):
            print(f"❌ Error: {output['error']}")
            return {"success": False, "error": output['error']}
        else:
            data = output["structured_data"]
            print(f"✅ Success!")
            print(json.dumps(data.model_dump(), indent=2))
            return {"success": True, "data": data.model_dump()}
            
    except Exception as e:
        print(f"❌ System Error: {str(e)}")
        return {"success": False, "error": str(e)}

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

@transaction.atomic
def save_invoice_data(document: Document, invoice_data: InvoiceData) -> Invoice:
    """Save extracted invoice data to database"""
    from datetime import datetime
    
    # Create Invoice record
    invoice = Invoice.objects.create(
        document=document,
        invoiceNo=invoice_data.invoiceNo,
        totalAmount=invoice_data.totalAmount,
        status='processed',
        extraction_method='langchain'
    )
    
    # Parse date if available
    if invoice_data.invoicedate:
        try:
            invoice_date = datetime.strptime(invoice_data.invoicedate, '%Y-%m-%d').date()
            invoice.invoicedate = invoice_date
        except ValueError:
            # If date parsing fails, leave as None
            pass
    
    invoice.save()
    
    # Create InvoiceLineItem records
    for entry_data in invoice_data.invoice_entries:
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description=entry_data.description,
            amt=entry_data.amt
        )
    
    return invoice

def process_invoice(document: Document) -> dict:
    """
    Main function to process an invoice document
    """
    result = {
        'success': False,
        'error': None,
        'data': None
    }
    
    try:
        # Log processing start
        log_processing_step(document, 'invoice_processing', 'started')
        
        # Extract text from file
        file_content = extract_text_from_file(document.file.path)
        
        if not file_content.strip():
            raise ValueError("No text content extracted from file")
        
        # Prepare state for graph
        state_input = {
            "content": file_content, 
            "file_type": 'text', 
            "file_path": document.file.path
        }

        # Run Graph
        output = app.invoke(state_input)
        
        if output.get("error"):
            result['error'] = output['error']
            log_processing_step(document, 'invoice_processing', 'failed', output['error'])
            document.status = Document.StatusChoices.FAILED
            document.error_message = output['error']
            document.save()
            return result
        
        # Save to database
        invoice_data = output["structured_data"]
        saved_invoice = save_invoice_data(document, invoice_data)
        
        # Log success
        log_processing_step(document, 'invoice_processing', 'completed')
        
        result.update({
            'success': True,
            'data': invoice_data.model_dump(),
            'invoice_id': saved_invoice.id
        })
        
    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        result['error'] = error_msg
        log_processing_step(document, 'invoice_processing', 'failed', error_msg)
        
        document.status = Document.StatusChoices.FAILED
        document.error_message = error_msg
        document.save()
    
    return result

# --- 6. Main Entry Point ---
if __name__ == "__main__":
    # Specify your invoice path here
    target_file = "invoice.pdf" 
    process_invoice_file(target_file)
