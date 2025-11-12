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
# Prefer env vars in production; keep safe fallbacks for local
app.config['UPLOAD_FOLDER'] = getattr(config, 'UPLOAD_DIRECTORY', 'uploads')
app.secret_key = os.getenv(
    "SECRET_KEY",
    "97d9db56259ef94e22c48dc1789c8988dd01f69c6743afbf67882971ff2e6bf8"
)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
# (Optional hardening; flip to True when serving over HTTPS)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# app.config["SESSION_COOKIE_SECURE"] = True  # enable in production HTTPS

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

# ---------------- HELPERS ----------------
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "username" not in session or session.get("role") != "admin":
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

def sanitize_role(role_val: str) -> str:
    role = (role_val or "").strip().lower()
    return "admin" if role == "admin" else "user"

# ---------------- AUTH ROUTES ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new user or admin"""
    if request.method == 'POST':
        data = request.form
        username = (data.get('username') or "").strip()
        password = data.get('password') or ""
        confirm_password = data.get('confirm_password') or password  # backward compat if not sent
        role = sanitize_role(data.get('role', 'user'))

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if password != confirm_password:
            return jsonify({"error": "Passwords do not match"}), 400

        # Case-insensitive uniqueness
        if users_collection.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}}):
            return jsonify({"error": "User already exists"}), 400

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        users_collection.insert_one({
            "username": username,
            "password": hashed_pw,
            "role": role,
            "created_at": datetime.utcnow()
        })
        return jsonify({"message": f"{role.capitalize()} registered successfully!"})
    return render_template("register.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login for user or admin"""
    if request.method == 'POST':
        data = request.form
        username = (data.get('username') or "").strip()
        password = data.get('password') or ""
        selected_role = sanitize_role(data.get('role', 'user'))

        user = users_collection.find_one({"username": username})
        if user and bcrypt.check_password_hash(user["password"], password):
            # Ensure role selection matches stored role
            if selected_role != user.get("role", "user"):
                return jsonify({"error": "Invalid role selected for this user"}), 403

            session.permanent = True
            session["username"] = username
            session["role"] = user["role"]
            if user["role"] == "admin":
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('profile_page'))
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    return render_template("login.html")


@app.route('/logout')
def logout():
    """Clear session"""
    session.clear()
    return redirect(url_for('home'))

# ---------------- MAIN ROUTES ----------------
@app.route('/')
@app.route('/home')
def home():
    # Your homepage with modal login/signup
    return render_template('StudentHome.html')

@app.route('/summary')
@login_required
def summary_page():
    return render_template('summary.html')

@app.route('/mcq')
@login_required
def mcq_page():
    return render_template('mcq.html')

@app.route('/chatbot')
@login_required
def chatbot_page():
    return render_template('chatbot.html')

@app.route('/contact')
def contact_page():
    return render_template('contact.html')

@app.route('/profile')
@login_required
def profile_page():
    """Student Dashboard"""
    return render_template('Studentdashboard.html', username=session.get("username"))

@app.route('/admin-dashboard')
@admin_required
def admin_dashboard():
    """Admin Dashboard"""
    return render_template('admin.html')

# (Optional small helper for frontend)
@app.route('/whoami')
def whoami():
    return jsonify({
        "username": session.get("username"),
        "role": session.get("role")
    })

# ---------------- SUMMARIZE & QUIZ ROUTES ----------------
@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    """Handle text or file summarization"""
    text = ""
    file = request.files.get('file')

    if 'text' in request.form and (request.form['text'] or "").strip():
        text = request.form['text']
    elif file and file.filename:
        text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])

    if not (text or "").strip() or "Error:" in text:
        return jsonify({'error': 'No text provided or file could not be read!'}), 400

    summary = content_processor.generate_bullet_point_summary(text)
    mcqs = mcq_generator.generate_meaningful_mcqs(summary, num_questions=getattr(config, 'MAX_MCQS_TO_GENERATE', 5))

    try:
        summaries_collection.insert_one({
            "student": session["username"],
            "source_filename": file.filename if (file and getattr(file, 'filename', None)) else "text_input",
            "source_type": "pdf" if (file and getattr(file, 'filename', '').lower().endswith('.pdf')) else ("ppt" if (file and getattr(file, 'filename', '').lower().endswith(('.ppt', '.pptx'))) else "text"),
            "char_count": len(text),
            "summary_bullets": len([ln for ln in summary.split("\n") if ln.strip()]),
            "timestamp": datetime.utcnow()
        })
    except Exception as e:
        # Don't block the UX if analytics write fails
        print("summaries insert error:", e)

    return jsonify({'summary': summary, 'mcqs': mcqs})

@app.route('/submit_mcqs', methods=['POST'])
@login_required
def submit_mcqs():
    """Save quiz/MCQ results"""
    data = request.json or {}
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    mcqs = data.get("mcqs", [])
    filename = data.get("filename", "N/A")

    if total <= 0:
        return jsonify({"error": "Total must be > 0"}), 400

    record = {
        "student": session["username"],
        "filename": filename,
        "score": score,
        "total": total,
        "percentage": round((score / total) * 100, 2),
        "mcqs": mcqs,
        "timestamp": datetime.utcnow()
    }
    try:
        quiz_results_collection.insert_one(record)
    except Exception as e:
        print("quiz insert error:", e)
        return jsonify({"error": "Failed to save result"}), 500

    return jsonify({"message": "Result saved successfully!", "data": record})

# ---------------- ANALYTICS ROUTES ----------------
@app.route('/analytics_summary/<student>', methods=['GET'])
@login_required
def analytics_summary(student):
    """Return student's analytics data; students can only view their own; admins can view any."""
    viewer = session.get("username")
    viewer_role = session.get("role")

    if viewer_role != "admin" and viewer != student:
        return jsonify({"error": "Not authorized to view this student's analytics"}), 403

    quiz_cursor = quiz_results_collection.find(
        {"student": student}, {"timestamp": 1, "percentage": 1}
    ).sort("timestamp", 1)
    quiz_trend = [{"date": q["timestamp"].isoformat(), "percentage": q.get("percentage", 0)} for q in quiz_cursor]

    score_cursor = quiz_results_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$filename", "avgPercentage": {"$avg": "$percentage"}}}
    ])
    score_by_file = [{"file": s["_id"] or "N/A", "avg": round(s["avgPercentage"] or 0, 2)} for s in score_cursor]

    summary_cursor = summaries_collection.aggregate([
        {"$match": {"student": student}},
        {"$group": {"_id": "$source_type", "count": {"$sum": 1}}}
    ])
    summary_types = [{"type": s["_id"] or "unknown", "count": s["count"]} for s in summary_cursor]

    return jsonify({
        "quiz_trend": quiz_trend,
        "score_by_file": score_by_file,
        "summary_types": summary_types
    })

# ---------------- ADMIN DATA ROUTES ----------------
@app.route('/get_analytics_all')
@admin_required
def get_analytics_all():
    """Return all quiz results for admin"""
    records = list(quiz_results_collection.find({}, {"_id": 0}))
    return jsonify(records)

@app.route('/get_summary_counts')
@admin_required
def get_summary_counts():
    """Return summary submission count per student"""
    summaries = summaries_collection.aggregate([
        {"$group": {"_id": "$student", "count": {"$sum": 1}}}
    ])
    result = [{"student": s["_id"], "count": s["count"]} for s in summaries]
    return jsonify(result)

# ---------------- HEALTH CHECK ----------------
@app.route('/health')
def health():
    return jsonify({"status": "ok"})

# ---------------- RUN ----------------
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
