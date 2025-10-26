from app.models import User


def get_default_teacher():
    # Try a few conventional names, otherwise just the first teacher
    t = User.query.filter(
        User.role == "teacher",
        User.username.in_(["Limor", "limor"]),
    ).first()
    if t:
        return t
    return User.query.filter_by(role="teacher").first()

# app/utils/teacher.py
from app.models import User

def get_default_teacher():
    """המורה ה'ראשון' במערכת – הוותיק ביותר (לפי created_at, אח"כ id)."""
    return (User.query
            .filter_by(role="teacher")
            .order_by(User.created_at.asc(), User.id.asc())
            .first())
