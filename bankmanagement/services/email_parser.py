import os
import json
import re
import imaplib
import email
import logging
import traceback
import boto3
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field, ValidationError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from langgraph.graph import StateGraph, END

from bankmanagement.models import BankStatement, BankTransaction
from document.models import Document, ProcessingLog
from paymentadvice.models import PaymentAdvice

# Initialize logger for this module
logger = logging.getLogger(__name__)

# --- 1. Data Schema (Validation Layer) ---
class PaymentEntry(BaseModel):
    invoice_number: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    payment_date: Optional[str] = None
    reference: Optional[str] = None

class EmailPaymentData(BaseModel):
    payment_invoice_no: Optional[str] = None
    total_received_amount: Optional[float] = None
    payment_currency: Optional[str] = None
    payment_date: Optional[str] = None
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    email_date: Optional[str] = None
    payment_entries: List[PaymentEntry] = Field(default_factory=list)
    extra_details: Optional[dict] = None

# --- 2. Graph State ---
class GraphState(TypedDict):
    email_content: str
    email_metadata: dict
    structured_data: Optional[EmailPaymentData]
    error: Optional[str]

# --- 3. Helper: JSON Cleaning ---
def clean_json_text(text: str) -> str:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()

# --- 4. Bedrock Claude Client ---
class BedrockClaude:
    def __init__(self):
        ACCESS_KEY = getattr(settings, 'AWS_ACCESS_KEY_ID', os.getenv('AWS_ACCESS_KEY_ID'))
        SECRET_KEY = getattr(settings, 'AWS_SECRET_ACCESS_KEY', os.getenv('AWS_SECRET_ACCESS_KEY'))
        
        self.bedrock_runtime = boto3.client(
            'bedrock-runtime',
            region_name="us-east-1",
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY
        )
        self.model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    def invoke(self, prompt: str):
        """Send prompt to Bedrock Claude and return text response"""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
            "temperature": 0
        }

        response = self.bedrock_runtime.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )
        response_json = json.loads(response["body"].read())
        return response_json["content"][0]["text"]

claude = BedrockClaude()

# --- 5. Email Fetching Functions ---
def decode_email_header(header):
    """Decode email header properly"""
    if header is None:
        return ""
    
    decoded_parts = decode_header(header)
    header_str = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            if encoding:
                try:
                    header_str += part.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    header_str += part.decode('utf-8', errors='ignore')
            else:
                header_str += part.decode('utf-8', errors='ignore')
        else:
            header_str += part
    return header_str

def clean_subject(subject):
    if subject:
        decoded, charset = decode_header(subject)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(charset or "utf-8", errors="ignore")
        return decoded
    return ""

def fetch_all_emails(limit: int = 5):
    """Fetch all emails from inbox - AI will filter payment-related ones"""
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASS = os.getenv("EMAIL_PASS")
    IMAP_SERVER = os.getenv("IMAP_SERVER", "mail.epigeeus.com")
    IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
    
    try:
        # Connect and login
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Search all emails
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()

        output = []

        # Get the last processed email date to avoid fetching older emails
        last_payment_advice = PaymentAdvice.objects.order_by('-email_date').first()
        last_processed_date = None
        if last_payment_advice and last_payment_advice.email_date:
            last_processed_date = last_payment_advice.email_date
            logger.info(f"ℹ Last processed email date: {last_processed_date}")

        # Loop through latest emails
        for eid in email_ids[-1:-limit-1:-1]:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = clean_subject(msg.get("subject", ""))
                    from_ = msg.get("From", "")

                    # Extract body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition") or "")
                            
                            if "attachment" not in content_disposition:
                                # Prefer plain text
                                if content_type == "text/plain":
                                    body = part.get_payload(decode=True).decode(errors="ignore")
                                    break
                                elif content_type == "text/html" and not body:
                                    body = part.get_payload(decode=True).decode(errors="ignore")
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    # Extract date and time
                    date_obj = parsedate_to_datetime(msg["Date"])
                    print("email_date", date_obj)
                    
                    # Ensure timezone-aware datetime
                    if date_obj and date_obj.tzinfo is None:
                        date_obj = timezone.make_aware(date_obj, timezone.utc)

                    # Skip emails older than last processed date
                    if last_processed_date and date_obj <= last_processed_date:
                        logger.info(f"⏭ Skipping older email from {date_obj} (last processed: {last_processed_date})")
                        continue

                    output.append({
                        'subject': subject,
                        'from': from_,
                        'date': date_obj,
                        'body': body
                    })

        mail.logout()
        return output

    except Exception as e:
        logger.error(f"❌ Error reading emails: {e}")
        return []

# --- 6. The Universal Extraction Node ---
def extract_payment_information(state: GraphState):
    """Extract payment information using Bedrock Claude"""
    
    # Updated Prompt for email payment advice extraction
    prompt = f"""
    You are an expert payment advice extraction assistant.
    Analyze the provided email content and determine if it contains payment-related information.
    If the email is NOT about payments, invoices, receipts, or payment advice, return null.
    Only extract payment information if the email is genuinely payment-related.

    CRITICAL REQUIREMENTS:
    1. First determine if this email is about payments/advice/invoices/receipts.
    2. If NOT payment-related, return exactly: null
    3. If payment-related, extract payment invoice number and total amount.
    4. Extract payment currency and payment date.
    5. Look for multiple payment entries if present.
    6. Use YYYY-MM-DD format for all dates.
    7. Return ONLY valid JSON, no markdown formatting.
    8. Focus on actual payment transactions only.

    JSON STRUCTURE REQUIRED:
    {{
        "payment_invoice_no": "Invoice number or reference",
        "total_received_amount": 123.45,
        "payment_currency": "USD, EUR, etc.",
        "payment_date": "YYYY-MM-DD",
        "email_subject": "Email subject line",
        "email_from": "Sender email",
        "email_date": "YYYY-MM-DD",
        "payment_entries": [
            {{
                "invoice_number": "Invoice reference",
                "amount": 123.45,
                "currency": "USD",
                "payment_date": "YYYY-MM-DD",
                "reference": "Additional reference"
            }}
        ],
        "extra_details": {{
            "notes": "Additional payment details",
            "bank_reference": "Bank reference if available"
        }}
    }}

    Here is the email content to process:
    ---
    Subject: {state['email_metadata'].get('subject', '')}
    From: {state['email_metadata'].get('from', '')}
    Date: {state['email_metadata'].get('date', '')}

    Email Body:
    {state['email_content']}
    ---

    Return only the JSON response:"""
    
    try:
        response = claude.invoke(prompt)
        cleaned_response = clean_json_text(response)
        
        # Check if AI determined this is not a payment-related email
        if cleaned_response.strip().lower() == 'null':
            return {"structured_data": None, "error": "Not a payment-related email"}
        
        data_dict = json.loads(cleaned_response)
        validated_data = EmailPaymentData(**data_dict)
            
        return {"structured_data": validated_data, "error": None}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON. Error: {str(e)}", "structured_data": None}
    except ValidationError as e:
        return {"error": f"Pydantic validation failed: {str(e)}", "structured_data": None}
    except Exception as e:
        return {"error": f"Extraction Error: {str(e)}", "structured_data": None}

# --- 7. Graph Assembly ---
workflow = StateGraph(GraphState)
workflow.add_node("extract", extract_payment_information)
workflow.set_entry_point("extract")
workflow.add_edge("extract", END)
app = workflow.compile()

# --- 8. Processing Functions ---
def is_email_already_processed(email_data: dict) -> bool:
    """Check if email has already been processed to avoid duplicates"""
    try:
        email_date = email_data.get('date')
        email_from = email_data.get('from')
        email_subject = email_data.get('subject')
        
        if not email_date:
            return False
        
        # Get the last processed email date from PaymentAdvice
        last_payment_advice = PaymentAdvice.objects.order_by('-email_date').first()
        
        if last_payment_advice and last_payment_advice.email_date:
            last_processed_dt = last_payment_advice.email_date
            logger.info(f"ℹ Last processed email at: {last_processed_dt}")
            
            # Skip if current email is older or equal to last processed
            if email_date <= last_processed_dt:
                logger.info(f"⏭ Skipping email from {email_date} (older than last processed)")
                return True
        
        # Additional check: look for exact same email already processed
        existing_email = PaymentAdvice.objects.filter(
            extra_data__email_metadata__from=email_from,
            extra_data__email_metadata__subject=email_subject,
            email_date=email_date
        ).first()
        
        if existing_email:
            logger.info(f"⏭ Skipping duplicate email: {email_subject} from {email_from}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking duplicate email: {str(e)}")
        return False

def log_processing_step(step_name: str, status: str, error_message: str = None, duration: float = None):
    """Log processing steps for debugging and monitoring"""
    import logging
    logger = logging.getLogger(__name__)
    
    log_message = f"{step_name}: {status}"
    
    if status == 'started':
        logger.info(f"🚀 {log_message}")
    elif status == 'completed':
        logger.info(f"✅ {log_message}")
        if duration:
            logger.info(f"⏱️ Duration: {duration}s")
    elif status == 'failed':
        logger.error(f"❌ {log_message}")
        if error_message:
            logger.error(f"🔥 Error: {error_message}")
        if duration:
            logger.error(f"⏱️ Duration: {duration}s")
    else:
        logger.info(f"ℹ️ {log_message}")
    
    # Also log to console for immediate feedback
    logger.info(f"[{datetime.now()}] {log_message}")
    if error_message:
        logger.error(f"Error: {error_message}")
    if duration:
        logger.info(f"Duration: {duration}s")

@transaction.atomic 
def save_payment_advice_data(email_data: dict, payment_data: EmailPaymentData) -> PaymentAdvice:
    """Save extracted payment advice data to database"""
    
    # Parse payment date
    payment_date = None
    if payment_data.payment_date:
        try:
            payment_date = datetime.strptime(payment_data.payment_date, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    # Parse email date
    email_datetime = email_data.get('date')
    
    # Create PaymentAdvice record
    payment_advice = PaymentAdvice.objects.create(
        payment_invoice_no=payment_data.payment_invoice_no,
        total_received_amount=payment_data.total_received_amount,
        payment_currency=payment_data.payment_currency,
        payment_date=payment_date,
        email_date=email_datetime,
        extra_data={
            'email_metadata': {
                'subject': payment_data.email_subject,
                'from': payment_data.email_from,
                'date': payment_data.email_date
            },
            'payment_entries': [entry.model_dump() for entry in payment_data.payment_entries],
            'extra_details': payment_data.extra_details
        },
        is_matched=False
    )
    
    return payment_advice

def process_payment_emails(limit: int = 5) -> dict:
    """
    Main function to fetch and process payment advice emails
    """
    result = {
        'success': False,
        'processed_count': 0,
        'failed_count': 0,
        'payment_advices': [],
        'errors': []
    }
    
    start_time = datetime.now()
    
    try:
        # Log processing start
        log_processing_step('email_fetch_started', 'started')
        
        # Fetch emails
        emails = fetch_all_emails(limit)
        
        if not emails:
            result['success'] = True
            result['message'] = 'No payment emails found'
            return result
        
        # Process each email
        for email_data in emails:
            try:
                # Check if email has already been processed
                if is_email_already_processed(email_data):
                    logger.info(f"Skipping already processed email from {email_data['from']}")
                    continue
                
                # Prepare state for graph
                state_input = {
                    "email_content": email_data['body'],
                    "email_metadata": {
                        'subject': email_data['subject'],
                        'from': email_data['from'],
                        'date': email_data['date'].strftime('%Y-%m-%d') if email_data['date'] else ''
                    }
                }
                
                # Process with LangChain
                output = app.invoke(state_input)
                
                if output.get("error"):
                    # Don't count non-payment emails as errors
                    if "Not a payment-related email" in output.get("error", ""):
                        logger.info(f"⏭ Skipping non-payment email from {email_data['from']}")
                        continue
                    else:
                        result['errors'].append(f"Email from {email_data['from']}: {output['error']}")
                        result['failed_count'] += 1
                        continue
                
                # Save to database
                payment_data = output["structured_data"]
                payment_advice = save_payment_advice_data(email_data, payment_data)
                
                result['payment_advices'].append({
                    'id': payment_advice.id,
                    'invoice_no': payment_advice.payment_invoice_no,
                    'amount': float(payment_advice.total_received_amount) if payment_advice.total_received_amount else 0,
                    'currency': payment_advice.payment_currency,
                    'email_from': email_data['from']
                })
                result['processed_count'] += 1
                
            except Exception as e:
                error_msg = f"Error processing email from {email_data.get('from', 'unknown')}: {str(e)}"
                result['errors'].append(error_msg)
                result['failed_count'] += 1
                continue
        
        # Log success
        duration = (datetime.now() - start_time).total_seconds()
        log_processing_step('email_processing_completed', 'completed', duration=duration)
        
        result['success'] = True
        
    except Exception as e:
        error_msg = f"Email processing error: {str(e)}"
        result['errors'].append(error_msg)
        duration = (datetime.now() - start_time).total_seconds()
        log_processing_step('email_processing_failed', 'failed', error_msg, duration)
    
    return result

# --- 9. Scheduled Job Function ---
def email_parser_job():
    """
    Scheduled job to process payment advice emails
    """
    try:
        result = process_payment_emails(limit=5)  # Process 5 emails at a time
        if result['success']:
            logger.info(f"Email parser processed {result['processed_count']} emails successfully")
            if result['errors']:
                logger.warning(f"Email parser encountered {len(result['errors'])} errors")
        else:
            logger.error("Email parser job failed")
    except Exception as e:
        logger.error(f"Email parser job error: {str(e)}")
