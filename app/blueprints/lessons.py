# app/blueprints/lessons.py
from flask import Blueprint, request, redirect, url_for, abort, flash
from flask_login import login_required
from app.extensions import db
from app.models import Lesson
from app.constants import PAYMENT_METHODS

bp = Blueprint("lessons", __name__)

@bp.post("/lessons/<int:lesson_id>/payment_method")
@login_required
def set_payment_method(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    value = request.form.get("payment_method")
    allowed = dict(PAYMENT_METHODS)
    if value not in allowed:
        abort(400, description="payment method not allowed")
    lesson.payment_method = value
    db.session.commit()
    flash(f"אופן התשלום עודכן ל־{allowed[value]}", "success")
    return redirect(request.referrer or url_for("teacher.dashboard"))
