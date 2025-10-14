
import os
import logging
import docx
from PyPDF2 import PdfReader
from werkzeug.datastructures import FileStorage

def extract_text_from_file(uploaded_file: FileStorage, upload_dir: str) -> str:
    """Extracts text from an uploaded file and returns the full text content."""
    if not uploaded_file or not uploaded_file.filename:
        return "Error: No file was provided."

    filename = os.path.basename(uploaded_file.filename)
    temp_file_path = os.path.join(upload_dir, filename)
    
    try:
        uploaded_file.save(temp_file_path)
        if filename.endswith(".pdf"):
            text = _extract_text_from_pdf(temp_file_path)
        elif filename.endswith(".docx"):
            text = _extract_text_from_docx(temp_file_path)
        else:
            return "Error: Unsupported file type."
        
        return text if text.strip() else "Error: No readable text could be extracted."
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def _extract_text_from_pdf(file_path: str) -> str:
    try:
        with open(file_path, "rb") as pdf_file_obj:
            pdf_reader = PdfReader(pdf_file_obj)
            text_parts = [page.extract_text() for page in pdf_reader.pages if page.extract_text()]
        return "\n".join(text_parts)
    except Exception as e:
        logging.error(f"Error reading PDF file at {file_path}: {e}")
        return ""

def _extract_text_from_docx(file_path: str) -> str:
    try:
        doc = docx.Document(file_path)
        text_parts = [para.text for para in doc.paragraphs if para.text]
        return "\n".join(text_parts)
    except Exception as e:
        logging.error(f"Error reading DOCX file at {file_path}: {e}")
        return ""