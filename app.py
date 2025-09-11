from flask import Flask, render_template, request, jsonify
from transformers import pipeline
from sentence_transformers import SentenceTransformer, util
import torch
import random
import os
from PyPDF2 import PdfReader
import docx

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Load Hugging Face summarizer
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# Load sentence transformer for grading answers
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/summarize', methods=['POST'])
def summarize():
    text = ""

    # --- Case 1: Pasted text ---
    if 'text' in request.form and request.form['text'].strip():
        text = request.form['text']

    # --- Case 2: File upload ---
    elif 'file' in request.files:
        file = request.files['file']
        if file.filename.endswith(".pdf"):
            text = extract_text_from_pdf(file)
        elif file.filename.endswith(".docx"):
            text = extract_text_from_docx(file)
        else:
            return jsonify({'error': 'Unsupported file type!'}), 400

    if not text.strip():
        return jsonify({'error': 'No text found in input or uploaded file.'}), 400

    # --- SUMMARIZATION ---
    summary = summarize_text(text)

    # --- MCQ GENERATION (no NER, simple style) ---
    mcqs = generate_mcqs(summary, max_mcqs=5)

    return jsonify({'summary': summary, 'mcqs': mcqs})


@app.route('/grade', methods=['POST'])
def grade():
    """Grade a student’s subjective answer against the generated summary."""
    student_answer = request.json.get("answer", "")
    reference = request.json.get("reference", "")

    if not student_answer.strip():
        return jsonify({"score": 0, "feedback": "⚠️ Please write an answer first."})

    # Encode both texts
    emb_student = embedding_model.encode(student_answer, convert_to_tensor=True)
    emb_ref = embedding_model.encode(reference, convert_to_tensor=True)

    # Similarity score
    similarity = util.pytorch_cos_sim(emb_student, emb_ref).item()

    # Scale similarity → score out of 10
    score = round(similarity * 10, 1)

    # Feedback
    if score > 8:
        feedback = "🌟 Excellent! Your answer is very close to the key points."
    elif score > 5:
        feedback = "👍 Good attempt, but you missed some important details."
    else:
        feedback = "⚡ Needs improvement. Try covering more points from the summary."

    return jsonify({"score": score, "feedback": feedback})


# --------- HELPERS ---------
def extract_text_from_pdf(file):
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


def extract_text_from_docx(file):
    text = ""
    try:
        doc = docx.Document(file)
        for para in doc.paragraphs:
            if para.text:
                text += para.text + " "
    except Exception as e:
        print(f"DOCX extraction error: {e}")
    return text.strip()


def summarize_text(text):
    if not text.strip():
        return "Error: No text to summarize."

    # Split text into chunks (~800 words)
    words = text.split()
    chunk_size = 800
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

    summaries = []
    for chunk in chunks:
        if chunk.strip():  # only non-empty chunks
            try:
                result = summarizer(chunk, max_length=400, min_length=100, do_sample=False)
                if result:
                    summaries.append(result[0]['summary_text'])
            except Exception as e:
                print(f"Summarizer error: {e}")

    if not summaries:
        return "Error: Could not generate summary. Possibly empty or unreadable input."

    return " ".join(summaries)


def generate_mcqs(text, max_mcqs=5):
    """
    Simple MCQ generator without NER.
    Uses sentences and keyword blanks.
    """
    sentences = text.split(". ")
    mcq_list = []

    for sent in sentences:
        if len(mcq_list) >= max_mcqs or len(sent.split()) < 5:
            continue

        words = sent.split()
        keyword = random.choice(words[1:-1])  # avoid first/last word
        question = sent.replace(keyword, "_____")

        # Fake options
        wrong_options = random.sample(words, min(3, len(words)))
        if keyword in wrong_options:
            wrong_options.remove(keyword)
        while len(wrong_options) < 3:
            wrong_options.append(f"Option_{random.randint(1,100)}")

        options = [keyword] + wrong_options
        random.shuffle(options)

        mcq_list.append({
            "question": question.strip(),
            "options": options,
            "answer": keyword
        })

    return mcq_list


if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
