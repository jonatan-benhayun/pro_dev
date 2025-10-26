# app/utils/auth.py
from functools import wraps
from typing import Iterable
from flask import abort, redirect, url_for
from flask_login import login_required, current_user

def _require_roles(roles: Iterable[str], *, allow_admin: bool = True):
    """
    מחזיר דקורטור שמחייב שלמשתמש יהיה אחד התפקידים ב-roles.
    ברירת המחדל: לאפשר גם ל-admin לעבור (allow_admin=True).
    """
    wanted = {str(r).lower() for r in roles}

    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            # שים לב: is_authenticated הוא property (ללא סוגריים)
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            user_role = str(getattr(current_user, "role", "")).lower()

            # אם מותר לאדמין, והוא אדמין — אפשר לעבור
            if allow_admin and user_role == "admin":
                return fn(*args, **kwargs)

            if user_role not in wanted:
                # אין הרשאה — 403
                abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return deco

# שימושים נוחים
teacher_required      = _require_roles(["teacher"])                 # מורה או אדמין
admin_required        = _require_roles(["admin"], allow_admin=False)  # רק אדמין
teacher_only_required = _require_roles(["teacher"], allow_admin=False) # רק מורה, לא אדמין
