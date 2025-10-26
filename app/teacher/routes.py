# app/teacher/routes.py
import os
from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4
from flask import render_template, request, redirect, url_for, flash, abort, send_file, current_app, send_from_directory
from flask_login import current_user
from app.extensions import db
from app.models import User, Lesson, StudentMaterial
from app.teacher import teacher_bp
from app.utils.auth import teacher_required
from app.utils.pdf_export import generate_lessons_summary_pdf
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func
from app.constants import PAYMENT_METHODS


# -------------------------
# עזר: פרסור תאריך/שעה
# -------------------------
def _parse_start_dt(raw: str) -> datetime:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty")

    # dd/mm/yyyy HH:MM (כמו בפלייסהולדר)
    try:
        return datetime.strptime(raw, "%d/%m/%Y %H:%M")
    except ValueError:
        pass

    # אם זה <input type="datetime-local">
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        pass

    # עוד נסיונות שימושיים
    for fmt in ("%d/%m/%Y, %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    raise ValueError(f"bad datetime format: {raw!r}")


# -------------------------
# עזר: בדיקת חפיפות
# -------------------------
def _overlap_for_teacher(teacher_id, start_at, end_at, exclude_id=None) -> Lesson | None:
    q = (Lesson.query
         .filter(Lesson.teacher_id == teacher_id)
         .filter(Lesson.status != "cancelled")
         .filter(Lesson.end_at > start_at)    # קיים מסתיים אחרי תחילת החדש
         .filter(Lesson.start_at < end_at))   # קיים מתחיל לפני סיום החדש
    if exclude_id:
        q = q.filter(Lesson.id != exclude_id)
    return q.order_by(Lesson.start_at.asc()).first()

def _overlap_for_student(student_id, start_at, end_at, exclude_id=None) -> Lesson | None:
    q = (Lesson.query
         .filter(Lesson.student_id == student_id)
         .filter(Lesson.status != "cancelled")
         .filter(Lesson.end_at > start_at)
         .filter(Lesson.start_at < end_at))
    if exclude_id:
        q = q.filter(Lesson.id != exclude_id)
    return q.order_by(Lesson.start_at.asc()).first()


def _is_allowed_material(filename: str) -> bool:
    if not filename:
        return False
    allowed = current_app.config.get('MATERIALS_ALLOWED_EXTENSIONS')
    if not allowed:
        return True
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in {e.lower() for e in allowed}


# -------------------------
# דשבורד מורה
# -------------------------
@teacher_bp.route("/dashboard")
@teacher_required
def dashboard():
    # תלמידים משויכים
    students = (User.query
                .filter(User.teacher_id == current_user.id, User.role == "student")
                .order_by(User.username.asc())
                .all())

    # שיעורים אחרונים – בלי cancelled (כולל כאלה עם סטטוס None)
    lessons = (Lesson.query
               .filter(
                   Lesson.teacher_id == current_user.id,
                   or_(Lesson.status.is_(None), func.lower(Lesson.status).notin_(["cancelled", "done"]))
               )
               .order_by(Lesson.start_at.desc())
               .limit(30)
               .all())

    now_utc = datetime.utcnow()
    overdue_threshold = now_utc - timedelta(minutes=30)
    past_due_lessons = [
        l for l in lessons
        if l.end_at and l.end_at < overdue_threshold and (l.status or "").lower() not in {"done", "cancelled"}
    ]

    return render_template(
        "teacher/dashboard.html",
        students=students,
        lessons=lessons,
        past_due_lessons=past_due_lessons,
    )

# -------------------------
# Completed lessons summary
# -------------------------
@teacher_bp.route("/lessons/completed")
@teacher_required
def lessons_completed():
    students = (User.query
                .filter(User.teacher_id == current_user.id, User.role == "student")
                .order_by(User.username.asc())
                .all())

    filters = {
        "start_date": (request.args.get("start_date") or "").strip(),
        "end_date": (request.args.get("end_date") or "").strip(),
        "student_id": request.args.get("student_id", type=int),
        "paid_status": (request.args.get("paid_status") or "").strip().lower(),
        "payment_method": (request.args.get("payment_method") or "").strip(),
    }

    q = (Lesson.query
         .filter(Lesson.teacher_id == current_user.id)
         .filter(Lesson.status.isnot(None))
         .filter(func.lower(Lesson.status) == "done"))

    student_id = filters["student_id"]
    if student_id:
        q = q.filter(Lesson.student_id == student_id)

    paid_status = filters["paid_status"]
    if paid_status:
        if paid_status in {"paid", "partial", "unpaid"}:
            q = q.filter(func.lower(Lesson.paid_status) == paid_status)
        else:
            flash("Invalid paid status filter.", "error")
            filters["paid_status"] = ""

    payment_method = filters["payment_method"]
    if payment_method != "":
        valid_methods = {v for v, _ in PAYMENT_METHODS}  # סט של הערכים בלבד: {"", "cash", "bit", ...}
        if payment_method in valid_methods:
            q = q.filter(Lesson.payment_method == payment_method)
        else:
            flash("Invalid payment method filter.", "error")
            filters["payment_method"] = ""

    if filters["start_date"]:
        try:
            start_dt = datetime.strptime(filters["start_date"], "%Y-%m-%d")
            q = q.filter(Lesson.start_at >= start_dt)
        except ValueError:
            flash("Invalid start date format.", "error")
            filters["start_date"] = ""

    if filters["end_date"]:
        try:
            end_dt = datetime.strptime(filters["end_date"], "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(Lesson.start_at < end_dt)
        except ValueError:
            flash("Invalid end date format.", "error")
            filters["end_date"] = ""

    lessons = q.order_by(Lesson.start_at.desc()).all()
    total_cost = sum((lesson.cost or 0) for lesson in lessons)
    total_minutes = sum((lesson.duration_minutes or 0) for lesson in lessons)
    total_hours = round(total_minutes / 60.0, 2) if total_minutes else 0

    if request.args.get("export") == "pdf":
        student_label = "ללא"
        if filters["student_id"]:
            selected = next((s for s in students if s.id == filters["student_id"]), None)
            if selected:
                student_label = selected.username
        pdf_filters = dict(filters)
        pdf_filters["student_name"] = student_label
        pdf_bytes = generate_lessons_summary_pdf(
            teacher_name=getattr(current_user, "username", ""),
            lessons=lessons,
            filters=pdf_filters,
            totals=(len(lessons), total_hours, total_cost),
        )
        filename = f"lessons-summary-{datetime.now():%Y%m%d-%H%M}.pdf"
        return send_file(BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=filename)

    return render_template(
        "teacher/lessons_completed.html",
        lessons=lessons,
        students=students,
        filters=filters,
        payment_methods=PAYMENT_METHODS,
        total_cost=total_cost,
        total_minutes=total_minutes,
        total_hours=total_hours,
    )

@teacher_bp.post("/lessons/<int:lesson_id>/payment_method")
@teacher_required
def set_payment_method(lesson_id):
    method = (request.form.get("payment_method") or "").strip()
    lesson = Lesson.query.get_or_404(lesson_id)

    lesson.payment_method = method or None
    lesson.paid_status = "paid" if method else "unpaid"

    db.session.commit()
    return redirect(request.referrer or url_for("teacher.lessons_completed"))


@teacher_bp.route("/lessons/new", methods=["GET", "POST"])
@teacher_required
def lesson_new():
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        start_raw = request.form.get("start_at")
        duration_m = request.form.get("duration_minutes", type=int) or 60
        price_input = request.form.get("price_per_hour", type=float)
        note_text = (request.form.get("note") or "").strip()

        if not student_id:
            flash("???? ????? ?????.", "error")
            return redirect(url_for("teacher.lesson_new"))

        try:
            start_at = _parse_start_dt(start_raw)
        except ValueError:
            flash("????? ????? ?? ????. ??????: dd/mm/yyyy HH:MM.", "error")
            return redirect(url_for("teacher.lesson_new"))

        if start_at < datetime.now():
            flash("אי אפשר לקבוע שיעור לתאריך שכבר עבר.", "error")
            return redirect(url_for("teacher.lesson_new"))

        end_at = start_at + timedelta(minutes=duration_m)
        if end_at <= start_at:
            flash("??? ????? ???? ????? ???? ????.", "error")
            return redirect(url_for("teacher.lesson_new"))

        t_conf = _overlap_for_teacher(current_user.id, start_at, end_at)
        if t_conf:
            flash(f"??????? ???""? ?????: {t_conf.start_at:%d.%m %H:%M}-{t_conf.end_at:%H:%M}.", "error")
            return redirect(url_for("teacher.lesson_new"))

        s_conf = _overlap_for_student(student_id, start_at, end_at)
        if s_conf:
            flash(f"?????? ??? ?? ?????: {s_conf.start_at:%d.%m %H:%M}-{s_conf.end_at:%H:%M}.", "error")
            return redirect(url_for("teacher.lesson_new"))

        student = User.query.get_or_404(student_id)
        rate = price_input if (price_input and price_input > 0) else (student.student_rate or 110.0)

        l = Lesson(
            student_id=student_id,
            teacher_id=current_user.id,
            start_at=start_at,
            end_at=end_at,
            duration_minutes=duration_m,
            status="scheduled",
            hourly_rate=rate,
            hourly_rate_at_time=rate,
            paid_status="unpaid",
            paid_amount=0.0,
            notes=note_text,
        )
        db.session.add(l)
        db.session.commit()
        flash("?????? ????.", "success")
        return redirect(url_for("teacher.dashboard"))

    students = (User.query
                .filter(User.teacher_id == current_user.id, User.role == "student")
                .order_by(User.username.asc())
                .all())
    return render_template("teacher/lesson_form.html", students=students, default_price=110, min_start=datetime.now().strftime("%Y-%m-%dT%H:%M"))

@teacher_bp.route("/lessons/<int:lesson_id>/done", methods=["POST"])
@teacher_required
def lesson_mark_done(lesson_id):
    l = Lesson.query.get_or_404(lesson_id)
    if l.teacher_id != current_user.id:
        abort(403)
    l.status = "done"
    db.session.commit()
    flash("סומן כבוצע.", "success")
    return redirect(url_for("teacher.dashboard"))

# ביטול שיעור
@teacher_bp.route("/lessons/<int:lesson_id>/cancel", methods=["POST"])
@teacher_required
def lesson_cancel(lesson_id):
    l = Lesson.query.get_or_404(lesson_id)
    if l.teacher_id != current_user.id:
        abort(403)

    if l.status != "cancelled":
        l.status = "cancelled"
        db.session.commit()
        flash("השיעור סומן כ'בוטל'.", "success")
    else:
        flash("השיעור כבר מבוטל.", "info")

    return redirect(url_for("teacher.dashboard"))


# עדכון תאריך/שעה
@teacher_bp.route("/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
@teacher_required
def lesson_edit(lesson_id):
    l = Lesson.query.get_or_404(lesson_id)
    if l.teacher_id != current_user.id:
        abort(403)

    if request.method == "POST":
        # קולט ערכים מטופס datetime-local בפורמט YYYY-MM-DDTHH:MM
        start_at = datetime.fromisoformat(request.form["start_at"])
        end_at   = datetime.fromisoformat(request.form["end_at"])

        if start_at < datetime.now():
            flash("אי אפשר לקבוע שיעור לתאריך שכבר עבר.", "error")
            return redirect(url_for("teacher.lesson_edit", lesson_id=l.id))

        if end_at <= start_at:
            flash("שעת הסיום חייבת להיות אחרי שעת ההתחלה.", "error")
            return redirect(url_for("teacher.lesson_edit", lesson_id=l.id))

        # חסימת חפיפה אצל המורה
        conflict_t = (Lesson.query
                      .filter(Lesson.teacher_id == current_user.id,
                              Lesson.status != "cancelled",
                              Lesson.id != l.id,
                              Lesson.end_at > start_at,
                              Lesson.start_at < end_at)
                      .first())
        if conflict_t:
            flash("יש כבר שיעור אצלך בזמן הזה.", "error")
            return redirect(url_for("teacher.lesson_edit", lesson_id=l.id))

        # חסימת חפיפה אצל התלמיד
        conflict_s = (Lesson.query
                      .filter(Lesson.student_id == l.student_id,
                              Lesson.status != "cancelled",
                              Lesson.id != l.id,
                              Lesson.end_at > start_at,
                              Lesson.start_at < end_at)
                      .first())
        if conflict_s:
            flash("לתלמיד כבר יש שיעור בזמן הזה.", "error")
            return redirect(url_for("teacher.lesson_edit", lesson_id=l.id))

        l.start_at = start_at
        l.end_at   = end_at
        db.session.commit()
        flash("התאריך/השעה עודכנו.", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template("teacher/lesson_edit.html", lesson=l, min_start=datetime.now().strftime("%Y-%m-%dT%H:%M"))

# -------------------------
# עריכת תלמיד
# -------------------------


# -------------------------
# חומרי לימוד לתלמידים
# -------------------------
@teacher_bp.route("/materials", methods=["GET", "POST"])
@teacher_required
def materials_manage():
    students = (User.query
                .filter(User.teacher_id == current_user.id, User.role == "student")
                .order_by(User.username.asc())
                .all())

    selected_id = request.args.get('student_id', type=int)
    if request.method == 'POST':
        selected_id = request.form.get('student_id', type=int)
        student = User.query.filter_by(id=selected_id, teacher_id=current_user.id, role='student').first()
        if not student:
            flash('התלמיד המבוקש לא נמצא.', 'error')
            return redirect(url_for('teacher.materials_manage'))

        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        link_url = (request.form.get('link_url') or '').strip()
        file = request.files.get('file')

        if not title:
            flash('יש להזין כותרת לחומר הלימוד.', 'error')
            return redirect(url_for('teacher.materials_manage', student_id=student.id))

        has_file = file and file.filename
        if not (has_file or link_url or description):
            flash('נא להוסיף קובץ, קישור או תיאור לחומר.', 'error')
            return redirect(url_for('teacher.materials_manage', student_id=student.id))

        saved_filename = None
        stored_name = None
        if has_file:
            original_name = secure_filename(file.filename)
            if not original_name:
                flash('שם הקובץ אינו תקין.', 'error')
                return redirect(url_for('teacher.materials_manage', student_id=student.id))
            if not _is_allowed_material(original_name):
                flash('סוג הקובץ אינו מותר להעלאה.', 'error')
                return redirect(url_for('teacher.materials_manage', student_id=student.id))
            stored_name = f"{uuid4().hex}_{original_name}"
            upload_path = current_app.config.get('MATERIALS_UPLOAD_PATH')
            try:
                file.save(os.path.join(upload_path, stored_name))
            except Exception as exc:
                current_app.logger.exception('Failed saving material file: %r', exc)
                flash('שמירת הקובץ נכשלה. נסו שנית.', 'error')
                return redirect(url_for('teacher.materials_manage', student_id=student.id))
            saved_filename = original_name

        material = StudentMaterial(
            student_id=student.id,
            teacher_id=current_user.id,
            title=title,
            description=description or None,
            link_url=link_url or None,
            file_path=stored_name,
            file_name=saved_filename,
        )
        db.session.add(material)
        db.session.commit()
        flash('חומר הלימוד נוסף בהצלחה.', 'success')
        return redirect(url_for('teacher.materials_manage', student_id=student.id))

    selected_student = None
    materials = []
    if selected_id:
        selected_student = User.query.filter_by(id=selected_id, teacher_id=current_user.id, role='student').first()
        if not selected_student and selected_id:
            flash('התלמיד המבוקש לא נמצא אצלך.', 'error')
            return redirect(url_for('teacher.materials_manage'))
    elif students:
        selected_student = students[0]
    if selected_student:
        materials = (StudentMaterial.query
                     .filter_by(student_id=selected_student.id, teacher_id=current_user.id)
                     .order_by(StudentMaterial.created_at.desc())
                     .all())

    return render_template('teacher/materials.html',
                           students=students,
                           selected_student=selected_student,
                           materials=materials)


@teacher_bp.post('/materials/<int:material_id>/delete')
@teacher_required
def material_delete(material_id):
    material = StudentMaterial.query.get_or_404(material_id)
    if material.teacher_id != current_user.id:
        abort(403)
    file_path = material.file_path
    upload_path = current_app.config.get('MATERIALS_UPLOAD_PATH')
    if file_path and upload_path:
        try:
            os.remove(os.path.join(upload_path, file_path))
        except FileNotFoundError:
            pass
        except Exception as exc:
            current_app.logger.warning('Failed removing material file %s: %r', file_path, exc)
    student_id = material.student_id
    db.session.delete(material)
    db.session.commit()
    flash('החומר הוסר.', 'success')
    return redirect(url_for('teacher.materials_manage', student_id=student_id))


@teacher_bp.route('/materials/<int:material_id>/download')
@teacher_required
def material_download(material_id):
    material = StudentMaterial.query.get_or_404(material_id)
    if material.teacher_id != current_user.id and material.student_id != current_user.id:
        abort(403)
    if not material.file_path:
        abort(404)
    upload_path = current_app.config.get('MATERIALS_UPLOAD_PATH')
    return send_from_directory(upload_path, material.file_path, as_attachment=True,
                               download_name=material.file_name or material.file_path)

@teacher_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@teacher_required
def student_edit(student_id):
    student = User.query.filter_by(id=student_id, teacher_id=current_user.id).first_or_404()

    if request.method == "POST":
        # כיתה (שומר אצלך כמחרוזת; אם עברת למספר – המר ל-int)
        student.grade = request.form.get("grade", student.grade)

        # תעריף
        raw_rate = (request.form.get("student_rate") or "").strip()
        try:
            rate_shekels = float(raw_rate or 0)
        except ValueError:
            rate_shekels = 0.0
        student.set_student_rate(rate_shekels if rate_shekels > 0 else 110.0)

        db.session.commit()
        flash("עודכן בהצלחה.", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template("teacher/student_edit.html", student=student)
