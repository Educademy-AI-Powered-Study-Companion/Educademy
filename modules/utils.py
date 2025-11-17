import os, logging, docx
from PyPDF2 import PdfReader
from werkzeug.datastructures import FileStorage

def extract_text_from_file(uploaded_file: FileStorage, upload_dir: str) -> str:
    if not uploaded_file or not uploaded_file.filename: 
        return "Error: No file was provided."
    
    filename = os.path.basename(uploaded_file.filename)
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    path = os.path.join(upload_dir, safe)
    
    try:
        uploaded_file.save(path)
        text = ""
        
        if filename.lower().endswith(".pdf"): 
            text = _extract_text_from_pdf(path)
        elif filename.lower().endswith(".docx"): 
            text = _extract_text_from_docx(path)
            
        print(f"--- DEBUG: Extracted {len(text)} characters from {filename} ---")
        if len(text) < 50:
            print(f"--- WARNING: Text is very short! content: {text} ---")

        return text if text.strip() else "Error: No readable text could be extracted."
    except Exception as e:
        logging.error("File error %s", e)
        return f"Error: Could not process file - {e}"
    finally:
        try: os.remove(path)
        except: pass

def _extract_text_from_pdf(p):
    try:
        with open(p,'rb') as f:
            reader = PdfReader(f)
            return "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        return ""

def _extract_text_from_docx(p):
    try:
        doc = docx.Document(p)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        return ""