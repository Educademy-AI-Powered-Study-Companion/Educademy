from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt
from flask_session import Session
from functools import wraps
import os

from modules import content_processor, mcq_generator, evaluator, utils, rag_chatbot, config

app = Flask(__name__)
bcrypt = Bcrypt(app)

# ---------------- CONFIG ----------------
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
session_logs_collection = db["session_logs"]  # Logs user session duration


# ---------------- AUTH DECORATORS ----------------
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


# ---------------- SECURE REGISTER (Students only) ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Public register — ALWAYS creates a student user."""
    if request.method == "POST":
        data = request.form
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        confirm = data.get("confirm_password") or ""

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        if password != confirm:
            return jsonify({"error": "Passwords do not match"}), 400

        # Case-insensitive check
        if users_collection.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}}):
            return jsonify({"error": "User already exists"}), 400

        hashed = bcrypt.generate_password_hash(password).decode("utf-8")

        users_collection.insert_one({
            "username": username,
            "password": hashed,
            "role": "user",   # 🔥 ALWAYS student
            "created_at": datetime.utcnow()
        })

        return jsonify({"message": "Student registered successfully!"})

    return redirect(url_for("home", login="required"))


# ---------------- SECURE LOGIN (Role auto-detected from DB) ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        data = request.form
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        user = users_collection.find_one({"username": username})

        if user and bcrypt.check_password_hash(user["password"], password):

            session["username"] = username
            session["role"] = user["role"]  # Role only from DB
            session["login_time"] = datetime.utcnow()

            # Log session entry
            session_logs_collection.insert_one({
                "username": username,
                "role": user["role"],
                "login_time": session["login_time"],
                "logout_time": None,
                "duration_minutes": None
            })

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("profile_page"))

        return jsonify({"error": "Invalid username or password"}), 401

    return redirect(url_for("home", login="required"))


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    username = session.get("username")
    login_time = session.get("login_time")

    if username and login_time:
        logout_time = datetime.utcnow()
        duration = (logout_time - login_time).total_seconds() / 60

        session_logs_collection.update_one(
            {"username": username, "logout_time": None},
            {"$set": {
                "logout_time": logout_time,
                "duration_minutes": round(duration, 2)
            }}
        )

    session.clear()
    return redirect(url_for("home"))


# ---------------- ROUTES ----------------
@app.route('/')
@app.route('/home')
def home():
    return render_template('StudentHome.html')


@app.route('/summary')
@login_required
def summary_page():
    return render_template('Summarizer.html')


@app.route('/mcq')
@login_required
def mcq_page():
    return render_template('MCQGenerater.html')


@app.route('/chatbot')
@login_required
def chatbot_page():
    return render_template('chatbot.html')


@app.route('/contact')
def contact_page():
    return render_template('Devcontact.html')


@app.route('/profile')
@login_required
def profile_page():
    return render_template('Studentdashboard.html', username=session.get("username"))


@app.route('/admin-dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin.html')


# ---------------- WHO AM I ----------------
@app.route('/whoami')
def whoami():
    return jsonify({
        "username": session.get("username"),
        "role": session.get("role")
    })


# ---------------- SUMMARIZER ----------------
@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    text = ""
    file = request.files.get("file")

    if 'text' in request.form and request.form['text'].strip():
        text = request.form["text"]
    elif file and file.filename:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])

    if not text.strip():
        return jsonify({"error": "No text provided"}), 400

    summary = content_processor.generate_bullet_point_summary(text)
    mcqs = mcq_generator.generate_meaningful_mcqs(summary, num_questions=5)

    try:
        fname = file.filename if (file and getattr(file, "filename", None)) else "text_input"
        fext = fname.lower()

        if fext.endswith(".pdf"): ftype = "pdf"
        elif fext.endswith((".ppt", ".pptx")): ftype = "ppt"
        else: ftype = "text"

        summaries_collection.insert_one({
            "student": session["username"],
            "source_filename": fname,
            "source_type": ftype,
            "char_count": len(text),
            "summary_bullets": len([ln for ln in summary.split("\n") if ln.strip()]),
            "timestamp": datetime.utcnow()
        })
    except Exception as e:
        print("summary insert error:", e)

    return jsonify({'summary': summary, 'mcqs': mcqs})


# ---------------- MCQ SUBMISSION ----------------
@app.route('/submit_mcqs', methods=['POST'])
@login_required
def submit_mcqs():
    data = request.json
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    filename = data.get("filename", "N/A")

    record = {
        "student": session["username"],
        "filename": filename,
        "score": score,
        "total": total,
        "percentage": round((score / total) * 100, 2),
        "mcqs": data.get("mcqs", []),
        "timestamp": datetime.utcnow()
    }

    quiz_results_collection.insert_one(record)
    return jsonify({"message": "Result saved", "data": record})


# ---------------- STUDENT ANALYTICS ----------------
@app.route('/analytics_summary/<student>')
@login_required
def analytics_summary(student):
    viewer = session.get("username")
    role = session.get("role")

    if role != "admin" and viewer != student:
        return jsonify({"error": "Not authorized"}), 403

    quiz_cursor = quiz_results_collection.find(
        {"student": student}, {"timestamp": 1, "percentage": 1}
    )

    quiz_trend = [
        {"date": q["timestamp"].isoformat(), "percentage": q["percentage"]}
        for q in quiz_cursor
    ]

    score_cursor = quiz_results_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$filename", "avgPercentage": {"$avg": "$percentage"}}}
    ])

    score_by_file = [
        {"file": s["_id"], "avg": round(s["avgPercentage"] or 0, 2)}
        for s in score_cursor
    ]

    summary_cursor = summaries_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$source_type", "count": {"$sum": 1}}}
    ])

    summary_types = [
        {"type": s["_id"], "count": s["count"]}
        for s in summary_cursor
    ]

    return jsonify({
        "quiz_trend": quiz_trend,
        "score_by_file": score_by_file,
        "summary_types": summary_types
    })


# ---------------- ADMIN ANALYTICS ----------------
@app.route('/get_analytics_all')
@admin_required
def get_analytics_all():
    return jsonify(list(quiz_results_collection.find({}, {"_id": 0})))


@app.route('/get_summary_counts')
@admin_required
def get_summary_counts():
    data = summaries_collection.aggregate([
        {"$group": {"_id": "$student", "count": {"$sum": 1}}}
    ])
    return jsonify([{"student": d["_id"], "count": d["count"]} for d in data])


@app.route('/get_session_logs')
@admin_required
def get_session_logs():
    return jsonify(list(session_logs_collection.find({}, {"_id": 0})))


# ---------------- HEALTH ----------------
@app.route('/health')
def health():
    return jsonify({"status": "ok"})


# ---------------- RUN ----------------
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
