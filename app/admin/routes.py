from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.extensions import db
from app.models import User
from app.utils.auth import admin_required
from . import admin_bp

@admin_bp.route("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()
    qry = User.query
    if q:
        like = f"%{q}%"
        qry = qry.filter((User.username.ilike(like)) | (User.email.ilike(like)))
    users = qry.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users, q=q)

@admin_bp.route("/set-role/<int:user_id>", methods=["POST"])
@admin_required
def set_role(user_id):
    role = request.form.get("role")
    if role not in ("student", "teacher", "admin"):
        flash("תפקיד לא חוקי", "danger")
        return redirect(url_for("admin.users"))
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id and role != "admin":
        flash("אי אפשר להסיר לעצמך הרשאת מנהל", "warning")
        return redirect(url_for("admin.users"))
    u.role = role
    db.session.commit()
    flash(f"התפקיד של {u.username} עודכן ל-{role}", "success")
    return redirect(url_for("admin.users"))
