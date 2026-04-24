import os
import json
import re
import pandas as pd
import shutil
from typing import List, Optional, TypedDict
from datetime import datetime
from django.conf import settings
from django.db import transaction
from pydantic import BaseModel, Field, ValidationError
from langchain_aws import ChatBedrock 
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from bankmanagement.models import BankStatement, BankTransaction
from document.models import Document, ProcessingLog


# --- 1. Data Schema (Validation Layer) ---
class Transaction(BaseModel):
    date: str
    description: str
    amount: Optional[float] = None
    debit: Optional[float] = None
    credit: Optional[float] = None
    balance: Optional[float] = None
    reference: Optional[str] = None

class BankStatementData(BaseModel):
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    statement_period: Optional[str] = None
    transactions: List[Transaction] = Field(default_factory=list)
    total_debit_amount: Optional[float] = None
    total_credit_amount: Optional[float] = None
    number_of_txn: Optional[int] = None

# --- 2. Graph State ---
class GraphState(TypedDict):
    file_content: str
    structured_data: Optional[BankStatementData]
    error: Optional[str]

# --- 3. Helper: JSON Cleaning ---
def clean_json_text(text: str) -> str:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()

# --- 4. The Universal Extraction Node ---
def extract_information(state: GraphState):
    # AWS Credentials - RECOMMENDED: Use os.getenv() for security
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
    
    # Updated Prompt to include specific requirements
    prompt = f"""
    You are an expert financial data extraction assistant.
    Extract structured information from the provided bank statement text.

    CRITICAL REQUIREMENTS:
    1. Extract Account Number and Account Name (Holder Name).
    2. Extract ALL transactions found in the statement.
    3. For EACH transaction, you MUST include: date, description, amount, debit, credit, and balance.
    4. Use YYYY-MM-DD format for all dates.
    5. Return ONLY valid JSON, no markdown formatting.

    JSON STRUCTURE REQUIRED:
    {{
        "account_holder_name": "Full account name",
        "bank_name": "Bank name",
        "account_number": "Full account number",
        "statement_period": "e.g. February 2024",
        "transactions": [
            {{
                "date": "YYYY-MM-DD",
                "description": "Description",
                "amount": 123.45,
                "debit": 123.45 or null,
                "credit": null,
                "balance": 1234.56,
                "reference": "Reference or null"
            }}
        ],
        "total_debit_amount": 0.0,
        "total_credit_amount": 0.0,
        "number_of_txn": 0
    }}

    Here is the bank statement text to process:
    ---
    {state['file_content']}
    ---

    Return only the JSON response:"""
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        json_string = clean_json_text(response.content)
        data_dict = json.loads(json_string)
        validated_data = BankStatementData(**data_dict)
            
        return {"structured_data": validated_data, "error": None}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON. Error: {str(e)}", "structured_data": None}
    except ValidationError as e:
        return {"error": f"Pydantic validation failed: {str(e)}", "structured_data": None}
    except Exception as e:
        return {"error": f"Extraction Error: {str(e)}", "structured_data": None}

# --- 5. Graph Assembly ---
workflow = StateGraph(GraphState)
workflow.add_node("extract", extract_information)
workflow.set_entry_point("extract")
workflow.add_edge("extract", END)
app = workflow.compile()

# --- 6. Processing Functions ---
def extract_text_from_file(file_path: str) -> str:
    """Extract text content from various file formats"""
    try:
        if file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path).fillna('')
            return df.to_csv(index=False)
        elif file_path.endswith('.csv'):
            df = pd.read_csv(file_path).fillna('')
            return df.to_csv(index=False)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")

def determine_transaction_type(transaction: Transaction) -> str:
    """Determine transaction type based on debit/credit fields"""
    if transaction.debit and transaction.debit > 0:
        return 'debit'
    elif transaction.credit and transaction.credit > 0:
        return 'credit'
    elif transaction.amount and transaction.amount < 0:
        return 'debit'
    elif transaction.amount and transaction.amount > 0:
        return 'credit'
    else:
        return 'other'

@transaction.atomic
def save_bank_statement_data(document: Document, statement_data: BankStatementData) -> BankStatement:
    """Save extracted bank statement data to database"""
    
    # Create BankStatement record
    bank_statement = BankStatement.objects.create(
        document=document,
        statement_period=statement_data.statement_period,
        bank_name=statement_data.bank_name,
        account_number=statement_data.account_number,
        account_holder_name=statement_data.account_holder_name,
        number_of_txn=statement_data.number_of_txn,
        total_credit_amount=statement_data.total_credit_amount,
        total_debit_amount=statement_data.total_debit_amount,
        status='processed',
        extraction_method='langchain'
    )
    
    # Create BankTransaction records
    for txn_data in statement_data.transactions:
        try:
            transaction_date = datetime.strptime(txn_data.date, '%Y-%m-%d').date()
        except ValueError:
            transaction_date = None
        
        transaction_type = determine_transaction_type(txn_data)
        
        BankTransaction.objects.create(
            bank_statement=bank_statement,
            transaction_date=transaction_date,
            description=txn_data.description,
            amount=txn_data.amount or 0,
            transaction_type=transaction_type,
            reference_number=txn_data.reference,
            balance_after_transaction=txn_data.balance,
            debit=txn_data.debit,
            credit=txn_data.credit,
            balance=txn_data.balance,
            reference=txn_data.reference
        )
    
    return bank_statement

def move_processed_file(document: Document) -> bool:
    """Move file from media/upload to media/processed after successful parsing"""
    try:
        if not document.file:
            return False
            
        # Get current file path
        current_path = document.file.path
        
        # Check if file is in upload directory
        if 'upload' not in current_path:
            return True  # Already moved or not in upload
            
        # Create processed directory if it doesn't exist
        media_root = getattr(settings, 'MEDIA_ROOT', 'media')
        processed_dir = os.path.join(media_root, 'processed')
        os.makedirs(processed_dir, exist_ok=True)
        
        # Get filename and create new path
        filename = os.path.basename(current_path)
        new_path = os.path.join(processed_dir, filename)
        
        # If file already exists in processed, add timestamp
        if os.path.exists(new_path):
            name, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_path = os.path.join(processed_dir, f"{name}_{timestamp}{ext}")
        
        # Move the file
        shutil.move(current_path, new_path)
        
        # Update document file path
        relative_new_path = os.path.relpath(new_path, media_root)
        document.file.name = relative_new_path
        document.save()
        
        return True
        
    except Exception as e:
        print(f"Error moving file: {str(e)}")
        return False

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

def process_bank_statement(document: Document) -> dict:
    """
    Main function to process a bank statement document
    """
    result = {
        'success': False,
        'bank_statement_id': None,
        'error': None,
        'transactions_count': 0
    }
    
    start_time = datetime.now()
    
    try:
        # Log processing start
        log_processing_step(document, 'extraction_started', 'started')
        
        # Extract text from file
        file_content = extract_text_from_file(document.file.path)
        
        # Process with LangChain
        output = app.invoke({"file_content": file_content})
        
        if output.get("error"):
            result['error'] = output['error']
            log_processing_step(document, 'extraction_failed', 'failed', output['error'])
            document.status = Document.StatusChoices.FAILED
            document.error_message = output['error']
            document.save()
            return result
        
        # Save to database
        statement_data = output["structured_data"]
        bank_statement = save_bank_statement_data(document, statement_data)
        
        # Update document status
        document.status = Document.StatusChoices.PARSED
        document.save()
        
        # Move file to processed directory
        move_success = move_processed_file(document)
        if not move_success:
            print(f"Warning: Failed to move file for document {document.id}")
        
        # Log success
        duration = (datetime.now() - start_time).total_seconds()
        log_processing_step(document, 'extraction_completed', 'completed', duration=duration)
        
        result.update({
            'success': True,
            'bank_statement_id': bank_statement.id,
            'transactions_count': len(statement_data.transactions)
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

# --- 7. Entry Point for Standalone Testing ---
def process_statement_file(file_path: str):
    """Standalone function for testing purposes"""
    print(f"📂 Processing: {file_path}...")
    try:
        file_content = extract_text_from_file(file_path)
        output = app.invoke({"file_content": file_content})
        
        if output.get("error"):
            print(f"❌ {output['error']}")
        else:
            data = output["structured_data"]
            print(f"✅ Success! Found {len(data.transactions)} transactions.")
            print(f"👤 Account Name: {data.account_holder_name}")
            print(f"🔢 Account Number: {data.account_number}")
            print(data.model_dump_json(indent=2))
            
    except Exception as e:
        print(f"❌ System Error: {str(e)}")

if __name__ == "__main__":
    # Example usage for testing
    process_statement_file("statement1.xlsx")
