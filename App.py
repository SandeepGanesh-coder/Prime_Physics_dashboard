"""
PRIME PHYSICS — Flask Backend
Complete REST API with authentication, roles, leaderboard, and data persistence.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flask_cors import CORS
import bcrypt
import os
import json
import re
from datetime import datetime, timedelta, timezone
from functools import wraps

# ─── APP SETUP ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")

app.config["SECRET_KEY"]             = os.environ.get("SECRET_KEY", "prime-physics-secret-key-2025")
app.config["JWT_SECRET_KEY"]         = os.environ.get("JWT_SECRET", "prime-physics-jwt-key-2025")
app.config["JWT_ACCESS_TOKEN_EXPIRES"]  = timedelta(hours=8)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
app.config["SQLALCHEMY_DATABASE_URI"]   = os.environ.get("DATABASE_URL", "sqlite:///prime_physics.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 50 MB upload limit

CORS(app, resources={r"/api/*": {
    "origins": "*",
    "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"],
    "expose_headers": ["Content-Disposition", "Content-Length", "Content-Type"],
}})

db  = SQLAlchemy(app)
jwt = JWTManager(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PDF_FOLDER = os.environ.get("PDF_FOLDER", UPLOAD_FOLDER)

# ─── MODELS ──────────────────────────────────────────────────────────────────

class User(db.Model):
    """Student or Mentor account."""
    __tablename__ = "users"

    id         = db.Column(db.Integer,  primary_key=True)
    username   = db.Column(db.String(64),  unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)          # bcrypt hash
    role       = db.Column(db.String(16),  nullable=False, default="student")   # student | mentor
    full_name  = db.Column(db.String(120), nullable=False)
    avatar_url = db.Column(db.String(512), nullable=True)
    target_exam= db.Column(db.String(64),  nullable=True)
    daily_goal_hrs = db.Column(db.Integer, default=4)
    is_active  = db.Column(db.Boolean,     default=True)
    created_at = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime,    nullable=True)

    study_sessions = db.relationship("StudySession", backref="user", lazy=True,
                                     cascade="all, delete-orphan")
    logs           = db.relationship("ActivityLog",  backref="user", lazy=True,
                                     cascade="all, delete-orphan")
    mentor_instructions = db.relationship("MentorInstruction", backref="mentor",
                                          lazy=True, foreign_keys="MentorInstruction.mentor_id",
                                          cascade="all, delete-orphan")

    def set_password(self, plain: str) -> None:
        self.password = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def check_password(self, plain: str) -> bool:
        return bcrypt.checkpw(plain.encode(), self.password.encode())

    def total_study_minutes(self) -> int:
        return sum(s.duration_minutes for s in self.study_sessions)

    def to_public_dict(self) -> dict:
        return {
            "id":           self.id,
            "username":     self.username,
            "email":        self.email,
            "role":         self.role,
            "full_name":    self.full_name,
            "avatar_url":   self.avatar_url,
            "target_exam":  self.target_exam,
            "daily_goal_hrs": self.daily_goal_hrs,
            "total_study_minutes": self.total_study_minutes(),
            "is_active":    self.is_active,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "last_login":   self.last_login.isoformat()  if self.last_login  else None,
        }


class StudySession(db.Model):
    """Pomodoro / focus session record."""
    __tablename__ = "study_sessions"

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    session_type     = db.Column(db.String(16), default="focus")  # focus | break
    started_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at         = db.Column(db.DateTime, nullable=True)
    notes            = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "user_id":          self.user_id,
            "duration_minutes": self.duration_minutes,
            "session_type":     self.session_type,
            "started_at":       self.started_at.isoformat() if self.started_at else None,
            "ended_at":         self.ended_at.isoformat()   if self.ended_at   else None,
            "notes":            self.notes,
        }


class ActivityLog(db.Model):
    """User activity log entries."""
    __tablename__ = "activity_logs"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text       = db.Column(db.String(512), nullable=False)
    timestamp  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "text":      self.text,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class MentorInstruction(db.Model):
    """Instructions set by a mentor for their students."""
    __tablename__ = "mentor_instructions"

    id         = db.Column(db.Integer, primary_key=True)
    mentor_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text       = db.Column(db.Text,    nullable=False)
    order_idx  = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "mentor_id":  self.mentor_id,
            "text":       self.text,
            "order_idx":  self.order_idx,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PDFResource(db.Model):
    """Study material / PDF file metadata."""
    __tablename__ = "pdf_resources"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(256), nullable=False)
    subtitle   = db.Column(db.String(256), nullable=True)
    filename   = db.Column(db.String(256), nullable=False)
    category   = db.Column(db.String(32),  nullable=False)   # cbse | neet | jee
    uploaded_by= db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_active  = db.Column(db.Boolean,  default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "subtitle":    self.subtitle,
            "filename":    self.filename,
            "category":    self.category,
            "uploaded_by": self.uploaded_by,
            "is_active":   self.is_active,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _error(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code

def _ok(data: dict = None, msg: str = "OK", **kwargs):
    payload = {"success": True, "message": msg}
    if data is not None:
        payload.update(data)
    payload.update(kwargs)
    return jsonify(payload), 200

def validate_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.\+\-]+@[\w\-]+\.[a-z]{2,}$", email, re.IGNORECASE))

def validate_password(pw: str) -> tuple[bool, str]:
    if len(pw) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", pw):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"\d", pw):
        return False, "Password must contain at least one digit."
    return True, ""

def require_role(*roles):
    """Decorator: verifies the JWT identity has one of the given roles."""
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            uid = get_jwt_identity()
            user = db.session.get(User, int(uid))
            if not user or user.role not in roles:
                return _error("Access denied — insufficient permissions.", 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ─── AUTH ROUTES ─────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    for field in ("username", "email", "password", "full_name"):
        if not data.get(field, "").strip():
            return _error(f"'{field}' is required.")

    username  = data["username"].strip().lower()
    email     = data["email"].strip().lower()
    password  = data["password"]
    full_name = data["full_name"].strip()
    role      = data.get("role", "student").strip().lower()

    if role not in ("student", "mentor"):
        return _error("Role must be 'student' or 'mentor'.")

    if role == "mentor":
        mentor_code = data.get("mentor_code", "")
        if mentor_code != "MENTOR@PRIME2025":
            return _error("Invalid mentor registration code. Contact the admin.")
        if not username.startswith("mentor_"):
            return _error("Mentor usernames must start with 'mentor_' (e.g. mentor_jairam).")

    if role == "student" and not re.match(r"^[a-z0-9_]{3,30}$", username):
        return _error("Username must be 3–30 characters: lowercase letters, digits, underscores.")

    if not validate_email(email):
        return _error("Invalid email address.")
    ok, reason = validate_password(password)
    if not ok:
        return _error(reason)

    if User.query.filter_by(username=username).first():
        return _error("Username already taken.")
    if User.query.filter_by(email=email).first():
        return _error("Email already registered.")

    user = User(
        username       = username,
        email          = email,
        role           = role,
        full_name      = full_name,
        target_exam    = data.get("target_exam", "JEE Main & Advanced"),
        daily_goal_hrs = int(data.get("daily_goal_hrs", 4)),
        avatar_url     = data.get("avatar_url"),
    )
    user.set_password(password)
    db.session.add(user)

    if role == "mentor":
        defaults = [
            "Complete the daily 4-hour focus goal. Break sessions using the Pomodoro timer.",
            "Solve at least one full CBSE paper every weekend under strict 3-hour exam conditions.",
            "Understand derivations — do not just memorise. Focus especially on Electromagnetism and Optics.",
            "Log every doubt in a dedicated notebook immediately. We will address them in 1-on-1 sessions.",
            "Hydrate regularly and take 5-minute walks during breaks to avoid burnout.",
        ]
        for i, text in enumerate(defaults):
            db.session.add(MentorInstruction(mentor_id=user.id, text=text, order_idx=i))

    db.session.commit()

    db.session.add(ActivityLog(user_id=user.id, text=f"Account created as {role}."))
    db.session.commit()

    access_token  = create_access_token(identity=str(user.id), additional_claims={"role": role})
    refresh_token = create_refresh_token(identity=str(user.id))

    return _ok(
        {"user": user.to_public_dict(), "access_token": access_token, "refresh_token": refresh_token},
        msg=f"Registration successful. Welcome, {full_name}!"
    )


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    login_val = data.get("login", "").strip().lower()
    password  = data.get("password", "")
    if not login_val or not password:
        return _error("'login' and 'password' are required.")

    user = User.query.filter(
        (User.username == login_val) | (User.email == login_val)
    ).first()

    if not user or not user.check_password(password):
        return _error("Invalid credentials.", 401)

    if not user.is_active:
        return _error("Account is disabled. Contact your mentor/admin.", 403)

    expected_role = data.get("role", "").strip().lower()
    if expected_role and user.role != expected_role:
        return _error(f"This account is registered as '{user.role}', not '{expected_role}'.", 403)

    user.last_login = datetime.now(timezone.utc)
    db.session.add(ActivityLog(user_id=user.id, text="Logged in."))
    db.session.commit()

    access_token  = create_access_token(identity=str(user.id),
                                        additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    return _ok(
        {"user": user.to_public_dict(), "access_token": access_token, "refresh_token": refresh_token},
        msg="Login successful."
    )


@app.route("/api/auth/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)
    new_token = create_access_token(identity=uid, additional_claims={"role": user.role})
    return _ok({"access_token": new_token})


@app.route("/api/auth/logout", methods=["POST"])
@jwt_required()
def logout():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if user:
        db.session.add(ActivityLog(user_id=user.id, text="Logged out."))
        db.session.commit()
    return _ok(msg="Logged out successfully.")


@app.route("/api/auth/me", methods=["GET"])
@jwt_required()
def me():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)
    return _ok({"user": user.to_public_dict()})


# ─── PROFILE ROUTES ──────────────────────────────────────────────────────────

@app.route("/api/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)

    data = request.get_json(silent=True) or {}

    if "full_name" in data:
        name = data["full_name"].strip()
        if not name:
            return _error("Name cannot be empty.")
        user.full_name = name

    if "target_exam" in data:
        user.target_exam = data["target_exam"].strip()

    if "daily_goal_hrs" in data:
        hrs = int(data["daily_goal_hrs"])
        if not (1 <= hrs <= 16):
            return _error("Daily goal must be between 1 and 16 hours.")
        user.daily_goal_hrs = hrs

    if "avatar_url" in data:
        user.avatar_url = data["avatar_url"].strip()

    db.session.add(ActivityLog(user_id=user.id, text="Profile updated."))
    db.session.commit()
    return _ok({"user": user.to_public_dict()}, msg="Profile updated.")


# ─── STUDY SESSIONS ──────────────────────────────────────────────────────────

@app.route("/api/sessions", methods=["POST"])
@jwt_required()
def add_session():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    mins = data.get("duration_minutes")
    if not mins or int(mins) < 1:
        return _error("'duration_minutes' must be a positive integer.")

    session = StudySession(
        user_id          = user.id,
        duration_minutes = int(mins),
        session_type     = data.get("session_type", "focus"),
        notes            = data.get("notes", ""),
        ended_at         = datetime.now(timezone.utc),
    )
    db.session.add(session)
    db.session.add(ActivityLog(
        user_id=user.id,
        text=f"Focus session complete! (+{int(mins)} mins)"
    ))
    db.session.commit()

    return _ok({"session": session.to_dict(), "total_minutes": user.total_study_minutes()},
               msg="Session recorded.")


@app.route("/api/sessions", methods=["GET"])
@jwt_required()
def get_sessions():
    uid     = get_jwt_identity()
    user    = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)
    sessions = [s.to_dict() for s in
                StudySession.query.filter_by(user_id=user.id)
                                  .order_by(StudySession.started_at.desc()).all()]
    return _ok({"sessions": sessions, "total_minutes": user.total_study_minutes()})


# ─── ACTIVITY LOG ─────────────────────────────────────────────────────────────

@app.route("/api/logs", methods=["GET"])
@jwt_required()
def get_logs():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)
    logs = [l.to_dict() for l in
            ActivityLog.query.filter_by(user_id=user.id)
                             .order_by(ActivityLog.timestamp.desc()).limit(25).all()]
    return _ok({"logs": logs})


@app.route("/api/logs", methods=["POST"])
@jwt_required()
def add_log():
    uid  = get_jwt_identity()
    user = db.session.get(User, int(uid))
    if not user:
        return _error("User not found.", 404)
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return _error("'text' is required.")
    log = ActivityLog(user_id=user.id, text=text)
    db.session.add(log)
    db.session.commit()
    return _ok({"log": log.to_dict()}, msg="Log entry added.")


# ─── LEADERBOARD ─────────────────────────────────────────────────────────────

@app.route("/api/leaderboard", methods=["GET"])
@jwt_required()
def leaderboard():
    students = User.query.filter_by(role="student", is_active=True).all()
    board = sorted(
        [{"id": u.id, "name": u.full_name, "exam": u.target_exam,
          "avatar": u.avatar_url, "mins": u.total_study_minutes()} for u in students],
        key=lambda x: x["mins"], reverse=True
    )[:20]
    for i, entry in enumerate(board):
        entry["rank"] = i + 1
    return _ok({"leaderboard": board})


# ─── MENTOR INSTRUCTIONS ─────────────────────────────────────────────────────

@app.route("/api/instructions", methods=["GET"])
@jwt_required()
def get_instructions():
    mentor = User.query.filter_by(role="mentor", is_active=True).first()
    if not mentor:
        return _ok({"instructions": []})
    instructions = [i.to_dict() for i in
                    MentorInstruction.query.filter_by(mentor_id=mentor.id)
                                          .order_by(MentorInstruction.order_idx).all()]
    return _ok({"instructions": instructions})


@app.route("/api/instructions", methods=["PUT"])
@require_role("mentor")
def update_instructions():
    uid    = get_jwt_identity()
    user   = db.session.get(User, int(uid))
    data   = request.get_json(silent=True) or {}
    lines  = data.get("instructions", [])
    if not isinstance(lines, list):
        return _error("'instructions' must be an array of strings.")

    MentorInstruction.query.filter_by(mentor_id=user.id).delete()
    for i, text in enumerate(lines):
        text = str(text).strip()
        if text:
            db.session.add(MentorInstruction(mentor_id=user.id, text=text, order_idx=i))

    db.session.add(ActivityLog(user_id=user.id, text="Mentor instructions updated."))
    db.session.commit()
    return _ok(msg="Instructions updated.")


# ─── PDF RESOURCES ────────────────────────────────────────────────────────────

@app.route("/api/resources", methods=["GET"])
@jwt_required()
def list_resources():
    category = request.args.get("category", "").lower()
    q = PDFResource.query.filter_by(is_active=True)
    if category in ("cbse", "neet", "jee"):
        q = q.filter_by(category=category)
    resources = [r.to_dict() for r in q.order_by(PDFResource.created_at.desc()).all()]
    return _ok({"resources": resources})


@app.route("/api/resources", methods=["POST"])
@require_role("mentor")
def add_resource():
    uid  = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    for field in ("name", "filename", "category"):
        if not data.get(field, "").strip():
            return _error(f"'{field}' is required.")

    category = data["category"].strip().lower()
    if category not in ("cbse", "neet", "jee"):
        return _error("Category must be cbse, neet, or jee.")

    resource = PDFResource(
        name        = data["name"].strip(),
        subtitle    = data.get("subtitle", "").strip(),
        filename    = data["filename"].strip(),
        category    = category,
        uploaded_by = int(uid),
    )
    db.session.add(resource)
    db.session.commit()
    return _ok({"resource": resource.to_dict()}, msg="Resource added.")


@app.route("/api/resources/<int:rid>", methods=["DELETE"])
@require_role("mentor")
def delete_resource(rid):
    """Soft-delete a PDF resource from the layout pipeline (mentor only)."""
    resource = db.session.get(PDFResource, rid)
    if not resource:
        return _error("Resource metadata asset missing.", 404)
    resource.is_active = False # Safely flags database state to clear document tracking
    db.session.commit()
    return _ok(msg="Resource removed successfully.")


# ─── FILE UPLOAD / DOWNLOAD ───────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".pdf"}

@app.route("/api/upload", methods=["POST"])
@require_role("mentor")
def upload_file():
    if "file" not in request.files:
        return _error("No file part in the request.")
    f = request.files["file"]
    if not f.filename:
        return _error("No file selected.")

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return _error("Only PDF files are allowed.")

    safe_name = re.sub(r"[^\w\.\-]", "_", f.filename)
    dest = os.path.join(UPLOAD_FOLDER, safe_name)
    f.save(dest)

    uid = get_jwt_identity()
    db.session.add(ActivityLog(user_id=int(uid), text=f"Uploaded file: {safe_name}"))
    db.session.commit()

    return _ok({"filename": safe_name, "url": f"/api/files/{safe_name}"}, msg="File uploaded.")


@app.route("/api/files/<path:filename>", methods=["GET"])
@jwt_required()
def download_file(filename):
    safe = re.sub(r"[^\w\.\-\(\) ]", "_", filename).strip()
    if not safe:
        return _error("Invalid filename.", 400)

    force_download = request.args.get("download", "0") == "1"
    as_attachment  = force_download

    for folder in dict.fromkeys([UPLOAD_FOLDER, PDF_FOLDER]):
        candidate = os.path.join(folder, safe)
        if os.path.isfile(candidate):
            return send_from_directory(
                folder, safe,
                as_attachment=as_attachment,
                mimetype="application/pdf",
                download_name=safe,
            )

    return _error(f"File '{safe}' not found on the server.", 404)


# ─── ADMIN / MENTOR: STUDENT MANAGEMENT ──────────────────────────────────────

@app.route("/api/mentor/students", methods=["GET"])
@require_role("mentor")
def list_students():
    students = [u.to_public_dict() for u in
                User.query.filter_by(role="student").order_by(User.full_name).all()]
    return _ok({"students": students})


@app.route("/api/mentor/students/<int:uid>/toggle", methods=["PATCH"])
@require_role("mentor")
def toggle_student(uid):
    student = db.session.get(User, uid)
    if not student or student.role != "student":
        return _error("Student not found.", 404)
    student.is_active = not student.is_active
    me_uid = int(get_jwt_identity())
    db.session.add(ActivityLog(
        user_id=me_uid,
        text=f"{'Enabled' if student.is_active else 'Disabled'} student: {student.username}"
    ))
    db.session.commit()
    return _ok({"user": student.to_public_dict()},
               msg=f"Student {'enabled' if student.is_active else 'disabled'}.")


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return _ok({"status": "ok", "version": "1.0.0"}, msg="Prime Physics API is running.")


# ─── ERROR HANDLERS ───────────────────────────────────────────────────────────

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return _error("Token has expired. Please log in again.", 401)

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return _error("Invalid token.", 422)

@jwt.unauthorized_loader
def missing_token_callback(error):
    return _error("Authorization token required.", 401)

@app.errorhandler(404)
def not_found(_):
    return _error("Endpoint not found.", 404)

@app.errorhandler(500)
def server_error(_):
    return _error("Internal server error.", 500)


# ─── DB INIT + SEED ──────────────────────────────────────────────────────────

def seed_demo_data():
    if User.query.count() > 0:
        return

    print("🌱  Seeding demo data …")

    mentor = User(
        username="mentor_jairam",
        email="jairam@primephysics.edu",
        role="mentor",
        full_name="Jairam (Mentor)",
        avatar_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?q=80&w=256&auto=format&fit=crop",
        target_exam=None,
    )
    mentor.set_password("Mentor@Prime2025")
    db.session.add(mentor)
    db.session.flush()

    for i, text in enumerate([
        "Complete the daily 4-hour focus goal. Break sessions using the Pomodoro timer.",
        "Solve at least one full CBSE paper every weekend under strict 3-hour exam conditions.",
        "Understand derivations — do not just memorise. Focus especially on Electromagnetism and Optics.",
        "Log every doubt in a dedicated notebook immediately. We will address them in 1-on-1 sessions.",
        "Hydrate regularly and take 5-minute walks during breaks to avoid burnout.",
    ]):
        db.session.add(MentorInstruction(mentor_id=mentor.id, text=text, order_idx=i))

    demo_students = [
        ("sandeep_ganesh", "sandeep@student.edu", "Sandeep Ganesh",     "JEE Main & Advanced",  4, 750,
         "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?q=80&w=256&auto=format&fit=crop"),
        ("neha_gupta",     "neha@student.edu",    "Neha Gupta",         "JEE Main & Advanced",  5, 1050,
         "https://images.unsplash.com/photo-1494790108377-be9c29b29330?q=80&w=256&auto=format&fit=crop"),
        ("aarav_sharma",   "aarav@student.edu",   "Aarav Sharma",       "JEE Main & Advanced",  4, 920,
         "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?q=80&w=256&auto=format&fit=crop"),
        ("riya_patel",     "riya@student.edu",    "Riya Patel",         "NEET UG Physics",      5, 845,
         "https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=256&auto=format&fit=crop"),
        ("karan_singh",    "karan@student.edu",   "Karan Singh",        "CBSE Board Exams",     3, 610,
         "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?q=80&w=256&auto=format&fit=crop"),
        ("vikram_reddy",   "vikram@student.edu",  "Vikram Reddy",       "NEET UG Physics",      4, 420,
         "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?q=80&w=256&auto=format&fit=crop"),
    ]

    for uname, email, fname, exam, goal, mins, avatar in demo_students:
        s = User(username=uname, email=email, role="student", full_name=fname,
                 target_exam=exam, daily_goal_hrs=goal, avatar_url=avatar)
        s.set_password("Student@Prime2025")
        db.session.add(s)
        db.session.flush()
        if mins > 0:
            db.session.add(StudySession(user_id=s.id, duration_minutes=mins,
                                        session_type="focus"))

    cbse = [
        ("Physics Paper 55/1/1", "Set 1 · Board Exam",      "55-1-1 Physics.pdf"),
        ("Physics Paper 55/1/2", "Set 2 · Board Exam",      "55-1-2 Physics.pdf"),
        ("Physics Paper 55/1/3", "Set 3 · Board Exam",      "55-1-3 Physics.pdf"),
        ("Physics Paper 55/2/1", "Set 1 · Board Exam",      "55-2-1 Physics.pdf"),
        ("Physics Paper 55/2/2", "Set 2 · Board Exam",      "55-2-2 Physics.pdf"),
        ("Physics Paper 55/2/3", "Set 3 · Board Exam",      "55-2-3 Physics.pdf"),
        ("Physics Paper 55/3/1", "Set 1 · Board Exam",      "55-3-1 Physics.pdf"),
        ("Physics Paper 55/3/2", "Set 2 · Board Exam",      "55-3-2 Physics.pdf"),
        ("Physics Paper 55/3/3", "Set 3 · Board Exam",      "55-3-3 Physics.pdf"),
        ("Physics Paper 55(B)",  "Visually Impaired Candidates",
         "55(B) Physics (For Blind Candidates).pdf"),
    ]
    neet = [
        ("NEET Graph Bank",      "Important Graphs",         "NEET Graph bank.pdf"),
        ("NCERT Scientists",     "Biology Discoveries",       "New NCERT SCIENTISTS & DISCOVERIES Compiled.pdf"),
        ("Physics Mind Maps",    "Class 12 Visual Notes",    "Physics - Mind Maps.pdf"),
        ("Physics Handbook",     "Math & Formula Reference", "physics handbook.pdf"),
        ("Thermodynamics Notes", "Chapter Notes & Formulas", "THERMODYNAMICS.pdf"),
        ("Biology Flashcards",   "Quick Revision Cards",     "Split_20260305_1234.pdf"),
    ]
    jee = [
        ("JEE Main Formula Sheet", "Full Physics Formula Bank", "JEE Main Formula Sheet.pdf"),
        ("JEE Main Mind Maps",     "Visual Chapter Summaries",  "JEE Main Mind Maps.pdf"),
        ("JEE Main PYQs",          "Previous Year Questions",   "JEE Main PYQs.pdf"),
    ]
    for name, sub, fn in cbse:
        db.session.add(PDFResource(name=name, subtitle=sub, filename=fn,
                                   category="cbse", uploaded_by=mentor.id))
    for name, sub, fn in neet:
        db.session.add(PDFResource(name=name, subtitle=sub, filename=fn,
                                   category="neet", uploaded_by=mentor.id))
    for name, sub, fn in jee:
        db.session.add(PDFResource(name=name, subtitle=sub, filename=fn,
                                   category="jee", uploaded_by=mentor.id))

    db.session.commit()
    print("✅  Seed data inserted.")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_demo_data()
    app.run(debug=True, host="0.0.0.0", port=5000)