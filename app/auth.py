from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, session
from flask_login import current_user, login_user, logout_user, login_required

from .extensions import db, login_manager
from .models import User, GRADE_CHOICES, VALID_GRADES


auth_bp = Blueprint("auth", __name__)


def teacher_required(view):
    @login_required
    def wrapper(*args, **kwargs):
        if not getattr(current_user, "is_teacher", lambda: False)():
            abort(403)
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def admin_required(view):
    @login_required
    def wrapper(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            abort(403)
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


@auth_bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


def redirect_after_login(user):
    """Redirect after login, honoring ?next and user role."""
    next_url = (request.args.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)

    role = getattr(user, "role", None)
    if role == "student":
        return redirect(url_for("student.dashboard"))
    if role == "teacher":
        return redirect(url_for("teacher.dashboard"))
    if role == "admin":
        try:
            return redirect(url_for("admin.dashboard"))
        except Exception:
            pass
    return redirect(url_for("main.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect_after_login(current_user)

    if request.method == "POST":
        username = (request.form.get("username") or request.form.get("name") or "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Invalid username or password.", "error")
            return render_template("login.html"), 401

        login_user(user)
        return redirect_after_login(user)

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Extract fields
        email = (request.form.get("email") or "").strip().lower()
        username = (
            request.form.get("username")
            or request.form.get("name")
            or request.form.get("full_name")
            or ""
        ).strip()
        password = request.form.get("password") or ""
        grade = request.form.get("grade", type=int)   # <-- מספר 1..12

        print("REGISTER POST:", request.form.to_dict())

        # ולידציה בסיסית
        if not email or not password or grade not in VALID_GRADES:
            flash("נא למלא את כל השדות ולבחור כיתה תקפה.", "error")
            return redirect(url_for("auth.register"))

        # אם אין שם משתמש – ניצור מהאימייל
        if not username:
            base = (email.split("@")[0] or "user")
            candidate, i = base, 1
            while User.query.filter_by(username=candidate).first():
                i += 1
                candidate = f"{base}{i}"
            username = candidate

        # מניעת כפילויות
        if User.query.filter((User.email == email) | (User.username == username)).first():
            flash("האימייל או שם המשתמש כבר קיימים.", "error")
            return redirect(url_for("auth.register"))

        # יצירת המשתמש (grade נשמר כמספר)
        user = User(email=email, username=username, grade=grade, role="student")
        user.set_password(password)

        # שיוך מורה ברירת מחדל (אם קיים)
        try:
            from .utils.teacher import get_default_teacher
            t = get_default_teacher()
            if t:
                user.teacher_id = t.id
        except Exception:
            pass

        db.session.add(user)
        db.session.commit()

        flash("נרשמת בהצלחה. אפשר להתחבר.", "success")
        return redirect(url_for("auth.login"))

    # GET: שולחים לטמפלט את האופציות (val,label)
    return render_template("register.html", grades=GRADE_CHOICES)

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("main.landing"))

