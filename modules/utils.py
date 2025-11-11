
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
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not safe_filename:
        return "Error: Invalid filename."
    
    temp_file_path = os.path.join(upload_dir, safe_filename)
    
    try:
        uploaded_file.save(temp_file_path)
        
        file_size = os.path.getsize(temp_file_path)
        if file_size > 16 * 1024 * 1024:
            return "Error: File too large. Maximum size is 16MB."
        
        if filename.lower().endswith(".pdf"):
            text = _extract_text_from_pdf(temp_file_path)
        elif filename.lower().endswith(".docx"):
            text = _extract_text_from_docx(temp_file_path)
        else:
            return "Error: Unsupported file type. Only PDF and DOCX files are supported."
        
        return text if text.strip() else "Error: No readable text could be extracted."
    except Exception as e:
        logging.error(f"Error processing file {filename}: {e}")
        return f"Error: Could not process file - {str(e)}"
    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logging.warning(f"Could not remove temp file {temp_file_path}: {e}")

def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF with optimized processing."""
    try:
        with open(file_path, "rb") as pdf_file_obj:
            pdf_reader = PdfReader(pdf_file_obj)
            text_parts = []
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_parts.append(page_text)
                except Exception as e:
                    logging.warning(f"Error extracting text from page: {e}")
                    continue
        return "\n".join(text_parts)
    except Exception as e:
        logging.error(f"Error reading PDF file at {file_path}: {e}")
        return ""

def _extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX with optimized processing."""
    try:
        doc = docx.Document(file_path)
        text_parts = [para.text for para in doc.paragraphs if para.text and para.text.strip()]
        return "\n".join(text_parts)
    except Exception as e:
        logging.error(f"Error reading DOCX file at {file_path}: {e}")
        return ""