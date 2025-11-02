# scripts/seed_all.py
from app import create_app
from app.extensions import db
from app.models import User


def seed_all():
    # === מורה ===
    teacher = User(
        username="לימור",
        email="jonatan0897@gmail.com",
        role="teacher",
    )
    teacher.set_password("123456")
    db.session.add(teacher)
    db.session.commit()
    print(f"[seed] Created teacher: {teacher.username} (id={teacher.id})")

    # === תלמידים ===
    students = [
        {"username": "יואב", "email": "yoav@classA.com", "grade": "ט'", "school": "אורט סינגלובסקי"},
        {"username": "נועה", "email": "noa@classB.com", "grade": "י'", "school": "גימנסיה הרצליה"},
        {"username": "רועי", "email": "roi@classC.com", "grade": "י״א", "school": "תיכון בליך"},
        {"username": "מאיה", "email": "maya@classD.com", "grade": "י״ב", "school": "תיכון חדש"},
        {"username": "אדם", "email": "adam@classE.com", "grade": "ח'", "school": "תיכון אבן יהודה"},
    ]

    for s in students:
        student = User(
            username=s["username"],
            email=s["email"],
            role="student",
            teacher_id=teacher.id,
            grade=s["grade"],
            school=s["school"],
        )
        student.set_password("123456")
        db.session.add(student)

    db.session.commit()
    print(f"[seed] Created {len(students)} students for teacher '{teacher.username}'")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed_all()
