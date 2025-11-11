from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
from datetime import datetime
import os
from modules import content_processor
from modules import mcq_generator
from modules import evaluator
from modules import utils
from modules import rag_chatbot
from modules import config 

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = config.UPLOAD_DIRECTORY

bot = rag_chatbot.RAGChatbot()


client = MongoClient("mongodb://localhost:27017/")
db = client["EduMentorDB"]
students_collection = db["students"]


@app.route('/')
def home():
    return render_template('StudentHome.html')

@app.route('/summary')
def summary_page():
    return render_template('summary.html')

@app.route('/mcq')
def mcq_page():
    return render_template('mcq.html')
    
@app.route('/chatbot')
def chatbot_page():
    return render_template('chatbot.html')

@app.route('/contact')
def contact_page():
    return render_template('Devcontact.html')

@app.route('/profile')
def profile_page():
    return render_template('Studentdashboard.html')


@app.route('/analytics')
def analytics_page():

    return render_template('analytics.html')


@app.route('/summarize', methods=['POST'])
def summarize():
    text = ""
    file = request.files.get('file')

    if 'text' in request.form and request.form['text'].strip():
        text = request.form['text']
    elif file and file.filename:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])

    if not text.strip() or "Error:" in text:
        return jsonify({'error': 'No text provided or file could not be read!'}), 400

    summary = content_processor.generate_bullet_point_summary(text)

    mcqs = mcq_generator.generate_meaningful_mcqs(summary, num_questions=config.MAX_MCQS_TO_GENERATE)

    return jsonify({'summary': summary, 'mcqs': mcqs})

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    question = request.form.get('question', '').strip()
    file = request.files.get('file')

    if file and file.filename:
        document_text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])
        if "Error:" not in document_text and document_text.strip():
            bot.setup_document(document_text)
            if not question:
                return jsonify({'answer': f"'{file.filename}' has been processed. You can now ask questions about it."})
        else:
            return jsonify({'answer': "Sorry, I could not read the document."})
    
    if not question:
        return jsonify({'answer': "Please ask a question."})

    answer = bot.answer_query(question)
    return jsonify({'answer': answer})


@app.route('/grade', methods=['POST'])
def grade():
    student_answer = request.json.get("answer", "")
    reference = request.json.get("reference", "")

    if not student_answer.strip():
        return jsonify({"score": 0, "feedback": "⚠️ Please write an answer first."})
    score, feedback = evaluator.evaluate_student_answer(student_answer, reference)
    return jsonify({"score": score, "feedback": feedback})

@app.route('/submit_mcqs', methods=['POST'])
def submit_mcqs():
    data = request.json
    student_name = data.get("student", "Anonymous")
    score = data.get("score", 0)
    total = data.get("total", 0)
    mcqs = data.get("mcqs", [])

    if not all([isinstance(score, int), isinstance(total, int), total > 0]):
        return jsonify({"error": "Invalid score or total."}), 400

    record = {
        "student": student_name,
        "score": score,
        "total": total,
        "percentage": round((score / total) * 100, 2),
        "mcqs": mcqs,
        "timestamp": datetime.utcnow()
    }
    students_collection.insert_one(record)
    return jsonify({"message": "Result saved successfully!", "data": record})

@app.route('/get_analytics/<student>', methods=['GET'])
def get_analytics(student):

    records = list(students_collection.find({"student": str(student)}, {"_id": 0}))
    return jsonify(records)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)