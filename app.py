from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt
from flask_session import Session
from functools import wraps
import os
import logging

from modules import content_processor, mcq_generator, utils, rag_chatbot, config

app = Flask(__name__)
bcrypt = Bcrypt(app)

app.config['UPLOAD_FOLDER'] = getattr(config, 'UPLOAD_DIRECTORY', 'uploads')
app.secret_key = os.getenv("SECRET_KEY", "97d9db56259ef94e22c48dc1789c8988dd01f69c6743afbf67882971ff2e6bf8")
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

Session(app)
bot = rag_chatbot.RAGChatbot()

# ---------------- DATABASE ----------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "EduMentorDB")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_collection = db["users"]
summaries_collection = db["summaries"]
quiz_results_collection = db["quiz_results"]
session_logs_collection = db["session_logs"]  

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("home", login="required"))
        return func(*args, **kwargs)
    return wrapper

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("home", login="required"))
        return func(*args, **kwargs)
    return wrapper

def get_text_and_file_from_request():
    """Helper to safely extract text and file info from request"""
    text = ""
    file = request.files.get("file")
    if 'text' in request.form and request.form['text'].strip():
        text = request.form["text"]
    elif file and file.filename:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])
    return text, file

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        data = request.form
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        confirm = data.get("confirm_password") or ""

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if password != confirm:
            return jsonify({"error": "Passwords do not match"}), 400
        if users_collection.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}}):
            return jsonify({"error": "User already exists"}), 400

        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        users_collection.insert_one({
            "username": username, "password": hashed, "role": "user", "created_at": datetime.utcnow()
        })
        return jsonify({"message": "Student registered successfully!"})
    return redirect(url_for("home", login="required"))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        data = request.form
        user = users_collection.find_one({"username": (data.get("username") or "").strip()})
        if user and bcrypt.check_password_hash(user["password"], data.get("password") or ""):
            session["username"] = user["username"]
            session["role"] = user["role"]  
            session["login_time"] = datetime.utcnow()
            session_logs_collection.insert_one({
                "username": user["username"], "role": user["role"], "login_time": session["login_time"], "logout_time": None, "duration_minutes": None
            })
            if user["role"] == "admin": return redirect(url_for("admin_dashboard"))
            return redirect(url_for("profile_page"))
        return jsonify({"error": "Invalid credentials"}), 401
    return redirect(url_for("home", login="required"))

@app.route('/logout')
def logout():
    if session.get("username") and session.get("login_time"):
        logout_time = datetime.utcnow()
        duration = (logout_time - session["login_time"]).total_seconds() / 60
        session_logs_collection.update_one(
            {"username": session["username"], "logout_time": None},
            {"$set": {"logout_time": logout_time, "duration_minutes": round(duration, 2)}}
        )
    session.clear()
    return redirect(url_for("home"))

@app.route('/') 
@app.route('/home')
def home(): return render_template('StudentHome.html')

@app.route('/summary') 
@login_required
def summary_page(): return render_template('Summarizer.html')

@app.route('/mcq') 
@login_required
def mcq_page(): return render_template('MCQGenerater.html')

@app.route('/chatbot')
@login_required
def chatbot_page(): return render_template('chatbot.html')

@app.route('/contact')
def contact_page(): return render_template('Devcontact.html')

@app.route('/profile')
@login_required
def profile_page(): return render_template('Studentdashboard.html', username=session.get("username"))

@app.route('/admin-dashboard')
@admin_required
def admin_dashboard(): return render_template('admin.html')

@app.route('/whoami')
def whoami(): return jsonify({"username": session.get("username"), "role": session.get("role")})



@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    text, file = get_text_and_file_from_request()
    if not text.strip(): return jsonify({"error": "No text provided"}), 400

    summary = content_processor.generate_bullet_point_summary(text)

    fname = file.filename if (file and getattr(file, "filename", None)) else "text_input"
    summaries_collection.insert_one({
        "student": session["username"], "action": "summary", "source_filename": fname, "timestamp": datetime.utcnow()
    })
    return jsonify({'summary': summary})

@app.route('/generate_quiz', methods=['POST'])
@login_required
def generate_quiz():
    text, file = get_text_and_file_from_request()
    if not text.strip(): return jsonify({"error": "No text provided"}), 400

    mcqs = mcq_generator.generate_meaningful_mcqs(text, num_questions=5)

    fname = file.filename if (file and getattr(file, "filename", None)) else "text_input"
    summaries_collection.insert_one({
        "student": session["username"], "action": "quiz", "source_filename": fname, "timestamp": datetime.utcnow()
    })
    return jsonify({'mcqs': mcqs})

@app.route('/ask-ai', methods=['POST'])
@login_required
def ask_ai():
    question = request.form.get("question")
    file = request.files.get("file")

    if file:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])
        if "Error" not in text:
            bot.setup_document(text)
        else:
            return jsonify({"answer": f"File Error: {text}"})
    
    response = bot.answer_query(question)
    return jsonify({"answer": response})


@app.route('/submit_mcqs', methods=['POST'])
@login_required
def submit_mcqs():
    data = request.json
    score, total = int(data.get("score", 0)), int(data.get("total", 1))
    quiz_results_collection.insert_one({
        "student": session["username"],
        "score": score, "total": total,
        "percentage": round((score / total) * 100, 2),
        "timestamp": datetime.utcnow()
    })
    return jsonify({"message": "Result saved"})

@app.route('/analytics_summary/<student>')
@login_required
def analytics_summary(student):
    if session.get("role") != "admin" and session.get("username") != student:
        return jsonify({"error": "Unauthorized"}), 403
    
    results = list(quiz_results_collection.find({"student": student}, {"_id":0}))
    return jsonify({"quiz_trend": results, "score_by_file": [], "summary_types": []})

@app.route('/get_analytics_all')
@admin_required
def get_analytics_all(): return jsonify(list(quiz_results_collection.find({}, {"_id": 0})))

@app.route('/get_summary_counts')
@admin_required
def get_summary_counts():
    data = summaries_collection.aggregate([{"$group": {"_id": "$student", "count": {"$sum": 1}}}])
    return jsonify([{"student": d["_id"], "count": d["count"]} for d in data])

@app.route('/get_session_logs')
@admin_required
def get_session_logs(): return jsonify(list(session_logs_collection.find({}, {"_id": 0})))

@app.route('/health')
def health(): return jsonify({"status": "ok"})

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)