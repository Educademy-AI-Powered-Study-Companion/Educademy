import os, logging, docx
from PyPDF2 import PdfReader
from werkzeug.datastructures import FileStorage

def extract_text_from_file(uploaded_file: FileStorage, upload_dir: str) -> str:
    if not uploaded_file or not uploaded_file.filename: return "Error: No file was provided."
    filename = os.path.basename(uploaded_file.filename)
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not safe: return "Error: Invalid filename."
    path = os.path.join(upload_dir, safe)
    try:
        uploaded_file.save(path)
        if os.path.getsize(path) > 16*1024*1024: return "Error: File too large. Maximum size is 16MB."
        if filename.lower().endswith(".pdf"): text = _extract_text_from_pdf(path)
        elif filename.lower().endswith(".docx"): text = _extract_text_from_docx(path)
        else: return "Error: Unsupported file type. Only PDF and DOCX files are supported."
        return text if text.strip() else "Error: No readable text could be extracted."
    except Exception as e:
        logging.error("File error %s", e); return f"Error: Could not process file - {e}"
    finally:
        try: os.remove(path)
        except: pass

def _extract_text_from_pdf(p):
    try:
        with open(p,'rb') as f:
            reader = PdfReader(f); parts = []
            for page in reader.pages:
                try:
                    t = page.extract_text()
                    if t and t.strip(): parts.append(t)
                except: continue
        return "\n".join(parts)
    except Exception as e:
        logging.error("PDF read %s", e); return ""

def _extract_text_from_docx(p):
    try:
        doc = docx.Document(p); return "\n".join([para.text for para in doc.paragraphs if para.text and para.text.strip()])
    except Exception as e:
        logging.error("DOCX read %s", e); return ""