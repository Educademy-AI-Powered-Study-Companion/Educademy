from transformers import pipeline
from PyPDF2 import PdfReader
import docx

# Initialize Hugging Face summarizer
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")


# ----------------- TEXT SUMMARIZATION -----------------
def summarize_text(text, chunk_size=800, max_length=400, min_length=100):
    """
    Summarizes long text by splitting into chunks.
    Returns a single merged summary string.
    """
    if not text.strip():
        return "Error: No text to summarize."

    words = text.split()
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

    summaries = []
    for chunk in chunks:
        if chunk.strip():
            try:
                result = summarizer(chunk, max_length=max_length, min_length=min_length, do_sample=False)
                if result:
                    summaries.append(result[0]['summary_text'])
            except Exception as e:
                print(f"Summarizer error: {e}")

    if not summaries:
        return "Error: Summarizer could not produce output. Possibly empty input."

    return " ".join(summaries)


# ----------------- PDF TEXT EXTRACTION -----------------
def extract_text_from_pdf(file):
    """
    Extracts text from PDF file.
    """
    text = ""
    try:
        pdf_reader = PdfReader(file)
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return text.strip()


# ----------------- DOCX TEXT EXTRACTION -----------------
def extract_text_from_docx(file):
    """
    Extracts text from DOCX file.
    """
    text = ""
    try:
        doc = docx.Document(file)
        for para in doc.paragraphs:
            if para.text:
                text += para.text + " "
    except Exception as e:
        print(f"DOCX extraction error: {e}")
    return text.strip()


# ----------------- MCQ GENERATION -----------------
import random
def generate_mcqs(text, max_mcqs=5):
    """
    Generates simple MCQs from summarized text.
    """
    sentences = text.split(". ")
    mcq_list = []

    for sent in sentences[:max_mcqs]:
        words = sent.split()
        if len(words) > 6:
            answer = random.choice(words[2:-2])
            question = sent.replace(answer, "_____")
            options = [answer]

            # Wrong options
            all_words = [w for s in sentences for w in s.split() if w.isalpha()]
            if len(all_words) >= 3:
                wrong_options = random.sample([w for w in all_words if w.lower() != answer.lower()], 3)
                options.extend(wrong_options)
                random.shuffle(options)

                mcq_list.append({
                    "question": question.strip(),
                    "options": options
                })

    return mcq_list