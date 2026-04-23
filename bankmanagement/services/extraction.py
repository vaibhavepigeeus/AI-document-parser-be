"""
Text extraction services converted from module1.py
"""
import os
import pandas as pd
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pytesseract
import re
from PIL import Image
from typing import Dict, Any, Optional
import logging

from document.models import Document, ProcessingLog

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service for extracting text from various document types"""
    
    def __init__(self, document: Document):
        self.document = document
        self.file_path = document.file.path
        self.file_type = document.file_type.lower()
    
    def extract_text(self) -> str:
        """Main extraction method that routes to appropriate extractor"""
        try:
            # Log extraction start
            self._log_step('extraction', 'started', f"Starting extraction for {self.file_type}")
            
            if self.file_type == 'csv':
                extracted_text = self._extract_csv()
            elif self.file_type == 'xlsx':
                extracted_text = self._extract_xlsx()
            elif self.file_type == 'pdf':
                extracted_text = self._extract_pdf()
            elif self.file_type in ['png', 'jpg', 'jpeg']:
                extracted_text = self._extract_image()
            else:
                raise ValueError(f"Unsupported file type: {self.file_type}")
            
            # Log extraction completion
            self._log_step('extraction', 'completed', f"Extracted {len(extracted_text)} characters")
            
            return extracted_text
            
        except Exception as e:
            logger.error(f"Extraction failed for document {self.document.id}: {e}")
            self._log_step('extraction', 'failed', f"Extraction failed: {str(e)}", str(e))
            raise
    
    def _extract_csv(self) -> str:
        """Extract text from CSV file"""
        try:
            df = pd.read_csv(self.file_path, header=None)
            return self._process_dataframe_to_text(df)
        except Exception as e:
            logger.error(f"CSV extraction failed: {e}")
            raise
    
    def _extract_xlsx(self) -> str:
        """Extract text from Excel file"""
        try:
            df = pd.read_excel(self.file_path, engine="openpyxl", header=None)
            return self._process_dataframe_to_text(df)
        except Exception as e:
            logger.error(f"Excel extraction failed: {e}")
            raise
    
    def _process_dataframe_to_text(self, df: pd.DataFrame) -> str:
        """
        Convert DataFrame to pipe-separated text while preserving vertical alignment
        """
        lines = []
        for row in df.values:
            row_cells = []
            for cell in row:
                if pd.isna(cell):
                    row_cells.append(" ")
                else:
                    clean = str(cell).replace("\n", " ").replace("\r", " ").strip()
                    row_cells.append(clean if clean else " ")
            
            # Only add the line if it's not entirely empty
            if any(c.strip() for c in row_cells):
                line = " | ".join(row_cells)
                lines.append(line)
        
        return "\n".join(lines)
    
    def _extract_pdf(self) -> str:
        """Extract text from PDF file with OCR fallback"""
        try:
            reader = PdfReader(self.file_path)
            full_text = ""
            
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and text.strip():
                    full_text += text + "\n"
                else:
                    logger.info(f"Running OCR on PDF page {i + 1}")
                    # OCR fallback for this page
                    ocr_text = self._ocr_pdf_page(self.file_path, i + 1)
                    full_text += ocr_text + "\n"
            
            return full_text
            
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise
    
    def _ocr_pdf_page(self, file_path: str, page_num: int) -> str:
        """OCR a specific page of a PDF"""
        try:
            images = convert_from_path(file_path, first_page=page_num, last_page=page_num)
            ocr_text = ""
            
            for img in images:
                text = pytesseract.image_to_string(img)
                ocr_text += text + "\n"
            
            return ocr_text
            
        except Exception as e:
            logger.error(f"PDF OCR failed for page {page_num}: {e}")
            return ""
    
    def _extract_image(self) -> str:
        """Extract text from image file using OCR"""
        try:
            logger.info("Running OCR on image...")
            
            # Preprocess image for better OCR
            img = Image.open(self.file_path)
            img = img.convert('L')  # Convert to grayscale
            img = img.point(lambda p: p > 128 and 255)  # Threshold
            
            text = pytesseract.image_to_string(img)
            
            if len(text.strip()) < 50:
                logger.warning("Extracted text is very poor/short")
            
            return text
            
        except Exception as e:
            logger.error(f"Image OCR failed: {e}")
            raise
    
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


def extract_text_from_document(document: Document) -> str:
    """
    Convenience function to extract text from a document
    """
    service = ExtractionService(document)
    return service.extract_text()
