from datetime import datetime
from flask import Blueprint, jsonify, redirect, render_template, request, url_for, flash, current_app
from flask_login import current_user, login_required
from sqlalchemy import or_
from .extensions import db, login_manager
from .models import Lesson, User, GRADE_CHOICES, VALID_GRADES, Lead
from app.constants import SCHOOLS
from app.utils.teacher import get_default_teacher
from app.utils.mail import send_email
main_bp = Blueprint("main", __name__)
@main_bp.route("/")
def landing():
    return render_template("landing.html")
@main_bp.post("/contact/lead")
def submit_lead():
    # honeypot נגד בוטים: שדה חבוי שלא אמור להתמלא
    if (request.form.get("website") or "").strip():
        return redirect(url_for("main.landing") + "#contact")

    name    = (request.form.get("name") or "").strip()
    phone   = (request.form.get("phone") or "").strip()
    email   = (request.form.get("email") or "").strip()
    message = (request.form.get("message") or "").strip()

    if not name or not phone:
        flash("נא למלא שם וטלפון כדי שנוכל לחזור אליך.", "error")
        return redirect(url_for("main.landing") + "#contact")

    lead = Lead(name=name, phone=phone, email=email or None, message=message or None)
    try:
        db.session.add(lead)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("submit_lead: failed to persist lead")

    recipient = (current_app.config.get("TEACHER_EMAIL") or "").strip()
    if not recipient:
        teacher = get_default_teacher()
        if teacher and teacher.email:
            recipient = teacher.email

    subject = f"פניה חדשה מהאתר - {name}"
    body_lines = [
        "התקבלה פניה חדשה מהאתר:",
        f"- שם: {name}",
        f"- טלפון: {phone}",
        f"- אימייל: {email or '-'}",
        f"- הודעה: {message or '-'}",
    ]
    body = "\n".join(body_lines)

    if recipient:
        ok = send_email(subject, body, recipient, reply_to=email or None)
        if ok:
            flash("תודה! קיבלנו את הפניה ונחזור אליך בקרוב.", "success")
        else:
            flash("שליחת המייל נכשלה, אנא בדקו את הגדרות הדואר הנכנסות.", "warning")
    else:
        current_app.logger.warning("submit_lead: no teacher email configured.")
        flash("שליחת המייל נכשלה, אנא בדקו את הגדרות הדואר הנכנסות.", "warning")

    return redirect(url_for("main.landing") + "#contact")
@main_bp.route("/dashboard")
@login_required
def dashboard():
    days_since = (datetime.utcnow() - current_user.created_at).days if current_user.created_at else None
    return render_template("dashboard.html", user=current_user, days_since=days_since)
@main_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_item():
    # Placeholder page for creating items
    return render_template("create_item.html")
@main_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        form_type = request.form.get("form_type", "profile")
        if form_type == "profile":
            new_username = (request.form.get("username") or "").strip()
            new_email    = (request.form.get("email") or "").strip().lower()

            if not new_username or not new_email:
                flash("שם משתמש ואימייל נדרשים.", "error")
                return redirect(url_for("main.edit_profile"))

            if User.query.filter(User.username == new_username, User.id != current_user.id).first():
                flash("שם המשתמש כבר בשימוש.", "error")
                return redirect(url_for("main.edit_profile"))
            if User.query.filter(User.email == new_email, User.id != current_user.id).first():
                flash("האימייל כבר בשימוש.", "error")
                return redirect(url_for("main.edit_profile"))

            if current_user.role == "student":
                new_grade = request.form.get("grade", type=int)
                new_school = (request.form.get("school") or "").strip()
                if new_grade not in VALID_GRADES:
                    flash("נא לבחור כיתה תקפה.", "error")
                    return redirect(url_for("main.edit_profile"))
                if new_school and new_school not in SCHOOLS:
                    flash("בית הספר שנבחר לא קיים.", "error")
                    return redirect(url_for("main.edit_profile"))
            else:
                new_grade = None
                new_school = None

            current_user.username = new_username
            current_user.email    = new_email
            if current_user.role == "student":
                current_user.grade = new_grade
                current_user.school = new_school or None
            else:
                current_user.grade = None
                current_user.school = None
            db.session.commit()
            flash("הפרופיל עודכן בהצלחה.", "success")
            if current_user.role == "student":
                return redirect(url_for("student.dashboard"))
            if current_user.role == "teacher":
                return redirect(url_for("teacher.dashboard"))
            return redirect(url_for("main.dashboard"))
        if form_type == "password":
            current = request.form.get("current_password") or ""
            new     = request.form.get("new_password") or ""
            confirm = request.form.get("confirm_password") or ""
            if not current_user.check_password(current):
                flash("הסיסמה הנוכחית שגויה.", "error")
                return redirect(url_for("main.edit_profile"))
            if len(new) < 6:
                flash("הסיסמה החדשה חייבת להיות באורך 6 תווים לפחות.", "error")
                return redirect(url_for("main.edit_profile"))
            if new != confirm:
                flash("אימות הסיסמה אינו תואם.", "error")
                return redirect(url_for("main.edit_profile"))
            current_user.set_password(new)
            db.session.commit()
            flash("הסיסמה עודכנה.", "success")
            return redirect(url_for("main.edit_profile"))
    # GET: שולחים לטמפלט את רשימת האופציות כ[(value,label)]
    return render_template(
        "profile_edit.html",
        user=current_user,
        grades=GRADE_CHOICES,
        schools=SCHOOLS,
    )
@main_bp.route("/calendar")
@login_required
def calendar_view():
    return render_template("calendar.html")
@main_bp.route("/api/calendar/events", endpoint="calendar_events")
@login_required
def calendar_events():
    role = (getattr(current_user, "role", "") or "").strip()
    if role == "teacher":
        q = Lesson.query.filter_by(teacher_id=current_user.id)
    else:
        q = Lesson.query.filter_by(student_id=current_user.id)
    q = q.filter(or_(Lesson.status.is_(None), Lesson.status != "cancelled"))
    events = []
    for l in q.order_by(Lesson.start_at.asc()).all():
        title = (
            f"Lesson with {l.student.username}"
            if role == "teacher"
            else f"Lesson with {l.teacher.username}"
        )
        extended_props = {
            "role_view": role,
            "student": getattr(l.student, "username", ""),
            "teacher": getattr(l.teacher, "username", ""),
            "show_payment": (role == "teacher"),
        }
        if role == "teacher":
            extended_props.update(
                {
                    "status": l.status or "",
                    "paid_status": getattr(l, "paid_status", "") or "",
                    "paid_amount": str(getattr(l, "paid_amount", "") or ""),
                }
            )
        events.append(
            {
                "id": l.id,
                "title": title,
                "start": l.start_at.isoformat(),
                "end": l.end_at.isoformat(),
                "allDay": False,
                "extendedProps": extended_props,
            }
        )
    return jsonify(events)
