"""
Document classification services converted from module2.py
"""
import os
import re
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_aws import ChatBedrock
import boto3
import logging

from document.models import Document, ProcessingLog

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class ClassificationService:
    """Service for classifying documents (invoice vs bank statement)"""
    
    def __init__(self, document: Document):
        self.document = document
        self.extracted_text = document.extracted_text or ""
    
    def classify_document(self) -> Dict[str, Any]:
        """
        Main classification method with keyword matching and LLM fallback
        """
        try:
            # Log classification start
            self._log_step('classification', 'started', 'Starting document classification')
            
            if not self.extracted_text:
                return {
                    'document_type': 'unknown',
                    'confidence_score': 0.0,
                    'method': 'no_text'
                }
            
            # Try keyword classification first
            result = self._keyword_classification()
            
            # If keyword classification fails, try LLM fallback
            if result['document_type'] == 'unknown':
                self._log_step('llm_fallback', 'started', 'Keyword classification failed, trying LLM')
                result = self._llm_classification()
            
            # If still undecided, mark for manual review
            if result['document_type'] in ['unknown', 'ambiguous', 'error']:
                self._log_step('manual_review', 'started', 'LLM could not decide, marking for manual review')
                result = self._manual_review_fallback()
            
            # Log final result
            self._log_step('classification', 'completed', f"Classification completed: {result['document_type']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Classification failed for document {self.document.id}: {e}")
            self._log_step('classification', 'failed', f"Classification failed: {str(e)}", str(e))
            return {
                'document_type': 'error',
                'confidence_score': 0.0,
                'method': 'error'
            }
    
    def _keyword_classification(self) -> Dict[str, Any]:
        """Classify document using keyword matching"""
        text_lower = self.extracted_text.lower()
        keywords = self._load_keywords()
        
        invoice_score = 0
        bank_score = 0
        
        # Keyword matching
        for kw in keywords["invoice"]:
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                invoice_score += 1
        
        for kw in keywords["bank_statement"]:
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                bank_score += 1
        
        # Pattern boosting
        if re.search(r"invoice\s*#?\s*\d+", text_lower):
            invoice_score += 2
        if re.search(r"total\s*[:\-]?\s*\$?\d+", text_lower):
            invoice_score += 1
        if re.search(r"account\s*number\s*[:\-]?\s*\d+", text_lower):
            bank_score += 2
        if re.search(r"(debit|credit)\s*[:\-]?\s*\$?\d+", text_lower):
            bank_score += 1
        
        # Final decision
        if invoice_score > bank_score:
            doc_type = "invoice"
            confidence = invoice_score / (invoice_score + bank_score + 1e-5)
        elif bank_score > invoice_score:
            doc_type = "bank_statement"
            confidence = bank_score / (invoice_score + bank_score + 1e-5)
        else:
            doc_type = "unknown"
            confidence = 0.5
        
        return {
            'document_type': doc_type,
            'confidence_score': round(confidence, 2),
            'method': 'keyword_matching',
            'invoice_score': invoice_score,
            'bank_score': bank_score
        }
    
    def _llm_classification(self) -> Dict[str, Any]:
        """Classify document using LLM fallback"""
        try:
            llm = self._get_llm()
            
            # Limit text to first 2000 characters
            text_content = self.extracted_text[:2000]
            
            prompt = f"Classify this document as either 'invoice' or 'bank_statement'. Return ONLY the word.\n\nText: {text_content}"
            
            response = llm.invoke(prompt)
            doc_type = response.content.strip().lower()
            
            # Map response to document type
            if "invoice" in doc_type:
                detected = "invoice"
            elif "bank" in doc_type:
                detected = "bank_statement"
            else:
                detected = "ambiguous"
            
            return {
                'document_type': detected,
                'confidence_score': 0.95,
                'method': 'llm_fallback',
                'llm_response': doc_type
            }
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                'document_type': 'error',
                'confidence_score': 0.0,
                'method': 'llm_error'
            }
    
    def _manual_review_fallback(self) -> Dict[str, Any]:
        """Final fallback: mark document for manual review"""
        logger.warning(f"Document {self.document.id} requires manual review")
        
        return {
            'document_type': 'manual_review',
            'status': 'pending_human_approval',
            'confidence_score': 0.0,
            'method': 'manual_review'
        }
    
    def _load_keywords(self) -> Dict[str, list]:
        """Load keyword lists for classification"""
        invoice_keywords = [
            "invoice", "invoice number", "bill to", "ship to",
            "due date", "total amount", "subtotal", "tax",
            "payment terms", "amount due", "po number"
        ]
        
        bank_keywords = [
            "account number", "statement date", "transaction",
            "balance", "debit", "credit", "withdrawal",
            "deposit", "bank statement", "available balance",
            "opening balance", "closing balance"
        ]
        
        return {
            "invoice": invoice_keywords,
            "bank_statement": bank_keywords
        }
    
    def _get_llm(self):
        """Get LLM instance (AWS Bedrock or Gemini)"""
        # Try AWS Bedrock first
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            try:
                client = boto3.client(
                    service_name="bedrock-runtime",
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name="us-east-1"
                )
                
                return ChatBedrock(
                    client=client,
                    model_id="anthropic.claude-3-sonnet-20240229-v1:0"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize AWS Bedrock: {e}")
        
        # Fallback to Gemini
        if os.getenv("GEMINI_API_KEY"):
            try:
                return ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    google_api_key=os.getenv("GEMINI_API_KEY")
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
        
        raise ValueError("No LLM configuration found. Please set AWS credentials or GEMINI_API_KEY")
    
    def _log_step(self, step_name: str, status: str, description: str, error_message: str = None):
        """Log processing step"""
        try:
            from django.utils import timezone
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


def classify_document(document: Document) -> Dict[str, Any]:
    """
    Convenience function to classify a document
    """
    service = ClassificationService(document)
    return service.classify_document()
