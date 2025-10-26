# scripts/add_duration_minutes.py
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # בדיקה אילו עמודות קיימות כרגע בטבלת lesson
    rows = db.session.execute(text("PRAGMA table_info(lesson)")).fetchall()
    cols = [r[1] for r in rows]
    print("current columns:", cols)

    if "duration_minutes" not in cols:
        db.session.execute(
            text("ALTER TABLE lesson ADD COLUMN duration_minutes INTEGER DEFAULT 60")
        )
        db.session.commit()
        print("✅ added column: duration_minutes (DEFAULT 60)")
    else:
        print("✅ duration_minutes already exists - nothing to do")
