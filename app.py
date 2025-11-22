from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt
from flask_session import Session
from functools import wraps
import os

from modules import content_processor, mcq_generator, utils, rag_chatbot, config

# ---------------- FLASK SETUP ----------------
app = Flask(__name__)
bcrypt = Bcrypt(app)

app.config['UPLOAD_FOLDER'] = getattr(config, 'UPLOAD_DIRECTORY', 'uploads')
app.secret_key = os.getenv(
    "SECRET_KEY",
    "97d9db56259ef94e22c48dc1789c8988dd01f69c6743afbf67882971ff2e6bf8"
)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

Session(app)
bot = rag_chatbot.RAGChatbot()

# ---------------- DATABASE ----------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "EduMentorDB")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_collection        = db["users"]
summaries_collection    = db["summaries"]
quiz_results_collection = db["quiz_results"]
session_logs_collection = db["session_logs"]


# ---------------- MIDDLEWARE ----------------
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


# ---------------- BASIC ROUTES ----------------
@app.route('/')
@app.route('/home')
def home():
    return render_template('StudentHome.html')


@app.route('/contact')
def contact_page():
    return render_template('Devcontact.html')


# ---------------- AUTH ----------------
@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")
    confirm = data.get("confirm_password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400
    if users_collection.count_documents({"username": username}):
        return jsonify({"error": "User already exists"}), 400

    hashed_pass = bcrypt.generate_password_hash(password).decode("utf-8")
    users_collection.insert_one({
        "username": username,
        "password": hashed_pass,
        "role": "user",
        "created_at": datetime.utcnow()
    })

    return jsonify({"message": "Student registered successfully!"})


@app.route('/login', methods=['POST'])
def login():
    data = request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = users_collection.find_one({"username": username})
    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    session["username"]   = user["username"]
    session["role"]       = user["role"]
    session["login_time"] = datetime.utcnow()

    session_logs_collection.insert_one({
        "username": user["username"],
        "role": user["role"],
        "login_time": session["login_time"],
        "logout_time": None,
        "duration_minutes": None
    })

    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("profile_page"))


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


# ---------------- STUDENT PAGES ----------------
@app.route('/profile')
@login_required
def profile_page():
    return render_template('Studentdashboard.html', username=session.get("username"))


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


# ---------------- ADMIN PAGE ----------------
@app.route('/admin-dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin.html')


# ---------------- SUMMARY SAVE ----------------
@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    text = request.form.get("text", "").strip()
    file = request.files.get("file")

    if not text and file:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])

    if not text:
        return jsonify({"error": "No input provided"}), 400

    summary = content_processor.generate_bullet_point_summary(text)

    summaries_collection.insert_one({
        "student": session["username"],
        "source_filename": file.filename if file else "text_input",
        "timestamp": datetime.utcnow(),
        "action": "summary"
    })

    return jsonify({"summary": summary})


# ---------------- MCQ GENERATOR ----------------
@app.route('/generate_quiz', methods=['POST'])
@login_required
def generate_quiz():
    text = request.form.get("text", "")
    file = request.files.get("file")

    if file:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])

    if not text:
        return jsonify({"error": "No text provided"}), 400

    mcqs = mcq_generator.generate_meaningful_mcqs(text, num_questions=5)

    summaries_collection.insert_one({
        "student": session["username"],
        "source_filename": file.filename if file else "text_input",
        "timestamp": datetime.utcnow(),
        "action": "quiz"
    })

    return jsonify({"mcqs": mcqs})


# ---------------- MCQ SUBMIT ----------------
@app.route('/submit_mcqs', methods=['POST'])
@login_required
def submit_mcqs():
    data = request.json or {}

    score = int(data.get("score", 0))
    total = max(int(data.get("total", 1)), 1)  # avoid divide by 0

    record = {
        "student": session.get("username"),
        "filename": data.get("filename", "N/A"),
        "score": score,
        "total": total,
        "percentage": round((score / total) * 100, 2),
        "timestamp": datetime.utcnow()
    }

    quiz_results_collection.insert_one(record)
    return jsonify({"message": "Result saved successfully!", "data": record})


# ---------------- STUDENT ANALYTICS (PROFILE) ----------------
@app.route('/analytics_summary/<student>')
@login_required
def analytics_summary(student):
    viewer = session.get("username")
    role   = session.get("role")

    if role != "admin" and viewer != student:
        return jsonify({"error": "Not allowed"}), 403

    quiz_trend = list(
        quiz_results_collection.find(
            {"student": student},
            {"_id": 0, "percentage": 1, "timestamp": 1}
        )
    )

    score_by_file = list(quiz_results_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$filename", "avg": {"$avg": "$percentage"}}}
    ]))

    # (summary_types left empty for now)
    return jsonify({
        "quiz_trend": [
            {"date": q["timestamp"].isoformat(), "percentage": q["percentage"]}
            for q in quiz_trend
        ],
        "score_by_file": [
            {"file": s["_id"], "avg": round(s["avg"], 2)}
            for s in score_by_file
        ],
        "summary_types": []
    })


# ---------------- LEADERBOARD (OPTIONAL) ----------------
@app.route('/leaderboard_data')
@login_required
def leaderboard_data():
    data = list(quiz_results_collection.aggregate([
        {
            "$group": {
                "_id": "$student",
                "bestScore": {"$max": "$percentage"},
                "avgScore": {"$avg": "$percentage"},
                "quizCount": {"$sum": 1}
            }
        },
        {
            "$project": {
                "student": "$_id",
                "_id": 0,
                "bestScore": 1,
                "avgScore": 1,
                "quizCount": 1
            }
        },
        {"$sort": {"bestScore": -1}}
    ]))

    for i, row in enumerate(data):
        row["rank"] = i + 1

    return jsonify(data)


# ---------------- ADMIN ANALYTICS APIs (USED BY admin.html) ----------------
@app.route('/get_analytics_all')
@admin_required
def get_analytics_all():
    """
    Return all quiz results for admin dashboard.
    """
    records = list(quiz_results_collection.find({}, {"_id": 0}))
    return jsonify(records)


@app.route('/get_summary_counts')
@admin_required
def get_summary_counts():
    """
    Return number of summaries per student for admin chart.
    """
    pipeline = [
        {"$group": {"_id": "$student", "count": {"$sum": 1}}}
    ]
    data = list(summaries_collection.aggregate(pipeline))
    result = [{"student": d["_id"], "count": d["count"]} for d in data]
    return jsonify(result)


# ---------------- MISC ----------------
@app.route('/health')
def health():
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)
