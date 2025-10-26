from datetime import datetime
from flask import render_template, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app.extensions import db
from app.models import Lesson, StudentMaterial
from . import student_bp

def _get_upcoming_lessons(student_id, limit=5):
    return (Lesson.query
            .filter(Lesson.student_id == student_id,
                    Lesson.start_at >= datetime.utcnow(),
                    or_(Lesson.status.is_(None), func.lower(Lesson.status).notin_(("cancelled", "done"))))
            .order_by(Lesson.start_at.asc())
            .limit(limit)
            .all())

def _get_student_materials(student_id, limit=None):
    q = (StudentMaterial.query
         .filter(StudentMaterial.student_id == student_id)
         .order_by(StudentMaterial.created_at.desc()))
    if limit:
        q = q.limit(limit)
    return q.all()

@student_bp.route("/dashboard")
@login_required
def dashboard():
    if getattr(current_user, "role", None) != "student":
        return render_template("errors/403.html"), 403

    lessons = _get_upcoming_lessons(current_user.id)
    materials = _get_student_materials(current_user.id, limit=5)

    return render_template("student/dashboard.html",
                           lessons=lessons, materials=materials)

@student_bp.route("/materials")
@login_required
def materials():
    if getattr(current_user, "role", None) != "student":
        return render_template("errors/403.html"), 403

    materials = _get_student_materials(current_user.id)
    return render_template("student/materials.html", materials=materials)

@student_bp.route("/materials/<int:material_id>/download")
@login_required
def material_download(material_id):
    material = StudentMaterial.query.get_or_404(material_id)
    role = getattr(current_user, 'role', None)
    if role == 'student' and material.student_id != current_user.id:
        return abort(403)
    if role == 'teacher' and material.teacher_id != current_user.id:
        return abort(403)
    if role not in {'student', 'teacher'}:
        return abort(403)
    if not material.file_path:
        return abort(404)
    upload_path = current_app.config.get('MATERIALS_UPLOAD_PATH')
    if not upload_path:
        return abort(404)
    return send_from_directory(upload_path, material.file_path, as_attachment=True,
                               download_name=material.file_name or material.file_path)
