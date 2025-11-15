from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt
from flask_session import Session
from functools import wraps
import os

# Import modules
from modules import content_processor, mcq_generator, evaluator, utils, rag_chatbot, config

app = Flask(__name__)
bcrypt = Bcrypt(app)

# ---------------- CONFIG ----------------
app.config['UPLOAD_FOLDER'] = getattr(config, 'UPLOAD_DIRECTORY', 'uploads')
app.secret_key = os.getenv(
    "SECRET_KEY",
    "97d9db56259ef94e22c48dc1789c8988dd01f69c6743afbf67882971ff2e6bf8"
)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

Session(app)
bot = rag_chatbot.RAGChatbot()

# ---------------- DATABASE ----------------
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client[os.getenv("DB_NAME", "EduMentorDB")]

users_collection = db["users"]
summaries_collection = db["summaries"]
quiz_results_collection = db["quiz_results"]
session_logs_collection = db["session_logs"]  # NEW

# ---------------- HELPERS ----------------
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

def sanitize_role(role_val: str) -> str:
    role = (role_val or "").strip().lower()
    return "admin" if role == "admin" else "user"

# ---------------- AUTH ROUTES ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        username = (data.get('username') or "").strip()
        password = data.get('password') or ""
        confirm_password = data.get('confirm_password') or password
        role = sanitize_role(data.get('role', 'user'))

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if password != confirm_password:
            return jsonify({"error": "Passwords do not match"}), 400

        if users_collection.find_one({"username": username}):
            return jsonify({"error": "User already exists"}), 400

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        users_collection.insert_one({
            "username": username,
            "password": hashed_pw,
            "role": role,
            "created_at": datetime.utcnow()
        })

        return jsonify({"message": f"{role.capitalize()} registered successfully!"})

    return redirect(url_for("home", login="required"))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login logic – modal-based login"""
    if request.method == 'POST':
        data = request.form
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        selected_role = sanitize_role(data.get("role"))

        user = users_collection.find_one({"username": username})

        if user and bcrypt.check_password_hash(user["password"], password):
            if selected_role != user.get("role"):
                return jsonify({"error": "Incorrect role selected"}), 403

            # Session start
            session["username"] = username
            session["role"] = user["role"]
            session["login_time"] = datetime.utcnow()

            # Log login
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

        return jsonify({"error": "Invalid credentials"}), 401

    # GET: Open modal on homepage
    return redirect(url_for("home", login="required"))


@app.route('/logout')
def logout():
    """Record logout + clear session"""
    username = session.get("username")
    login_time = session.get("login_time")

    if username and login_time:
        logout_time = datetime.utcnow()
        duration = (logout_time - login_time).total_seconds() / 60

        session_logs_collection.update_one(
            {"username": username, "logout_time": None},
            {"$set": {"logout_time": logout_time, "duration_minutes": round(duration, 2)}}
        )

    session.clear()
    return redirect(url_for("home"))


# ---------------- MAIN ROUTES ----------------
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


# ---------------- API: USER INFO ----------------
@app.route('/whoami')
def whoami():
    return jsonify({
        "username": session.get("username"),
        "role": session.get("role")
    })


# ---------------- SUMMARIZER ROUTE ----------------
@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    text = ""
    file = request.files.get('file')

    if 'text' in request.form and request.form['text'].strip():
        text = request.form['text']
    elif file and file.filename:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])

    if not text.strip():
        return jsonify({'error': 'No text provided'}), 400

    summary = content_processor.generate_bullet_point_summary(text)
    mcqs = mcq_generator.generate_meaningful_mcqs(summary, num_questions=5)

    summaries_collection.insert_one({
        "student": session["username"],
        "source_filename": file.filename if file else "text_input",
        "source_type": "pdf" if file else "text",
        "char_count": len(text),
        "summary_bullets": len(summary.split("\n")),
        "timestamp": datetime.utcnow()
    })

    return jsonify({'summary': summary, 'mcqs': mcqs})


# ---------------- MCQ SUBMISSION ----------------
@app.route('/submit_mcqs', methods=['POST'])
@login_required
def submit_mcqs():
    data = request.json
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    mcqs = data.get("mcqs", [])
    filename = data.get("filename", "N/A")

    record = {
        "student": session["username"],
        "filename": filename,
        "score": score,
        "total": total,
        "percentage": round((score / total) * 100, 2),
        "mcqs": mcqs,
        "timestamp": datetime.utcnow()
    }

    quiz_results_collection.insert_one(record)
    return jsonify({"message": "Result saved", "data": record})


# ---------------- ANALYTICS ROUTES ----------------
@app.route('/analytics_summary/<student>')
@login_required
def analytics_summary(student):
    viewer = session.get("username")
    role = session.get("role")

    if role != "admin" and viewer != student:
        return jsonify({"error": "Not allowed"}), 403

    quiz_cursor = quiz_results_collection.find(
        {"student": student}, {"timestamp": 1, "percentage": 1}
    )

    quiz_trend = [{"date": q["timestamp"].isoformat(),
                   "percentage": q["percentage"]} for q in quiz_cursor]

    score_cursor = quiz_results_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$filename", "avgPercentage": {"$avg": "$percentage"}}}
    ])

    score_by_file = [{"file": s["_id"],
                      "avg": round(s["avgPercentage"] or 0, 2)} for s in score_cursor]

    summary_cursor = summaries_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$source_type", "count": {"$sum": 1}}}
    ])

    summary_types = [{"type": s["_id"], "count": s["count"]} for s in summary_cursor]

    return jsonify({
        "quiz_trend": quiz_trend,
        "score_by_file": score_by_file,
        "summary_types": summary_types
    })


# ---------------- ADMIN ROUTES ----------------
@app.route('/get_analytics_all')
@admin_required
def get_analytics_all():
    records = list(quiz_results_collection.find({}, {"_id": 0}))
    return jsonify(records)


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
    records = list(session_logs_collection.find({}, {"_id": 0}))
    return jsonify(records)


# ---------------- HEALTH ----------------
@app.route('/health')
def health():
    return jsonify({"status": "ok"})


# ---------------- RUN ----------------
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
