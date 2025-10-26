# scripts/seed.py
import os
from app import create_app
from app.extensions import db
from app.models import User

def get_or_create_teacher(username, email, password):
    # חיפוש לפי אימייל כדי למנוע כפילות
    teacher = User.query.filter_by(email=email).first()
    if teacher:
        print(f"[seed] Teacher already exists: id={teacher.id} email={teacher.email}")
        return teacher

    teacher = User(username=username, email=email, role="teacher")
    teacher.set_password(password)
    db.session.add(teacher)
    db.session.commit()
    print(f"[seed] Created default teacher: id={teacher.id} email={teacher.email}")
    return teacher

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        # אפשר להגדיר פרטים דרך משתני סביבה, או להשתמש בברירת המחדל
        username = os.getenv("SEED_TEACHER_USERNAME", "לימור")
        email    = os.getenv("SEED_TEACHER_EMAIL",    "limor5272@gmail.com")
        password = os.getenv("SEED_TEACHER_PASSWORD", "123456")

        # אם אין בכלל מורים – ניצור אחד. אם יש – נוודא שיש לפחות את זה לפי אימייל
        existing_any = User.query.filter_by(role="teacher").first()
        if not existing_any:
            get_or_create_teacher(username, email, password)
        else:
            # גם אם יש מורה כלשהו, אם ביקשו אימייל מסוים – נוודא שקיים
            get_or_create_teacher(username, email, password)
