# app/utils/scheduling.py
from app.extensions import db
from app.models import Lesson

def has_overlap_for_teacher(teacher_id, start_at, end_at, exclude_id=None):
    q = (Lesson.query
         .filter(Lesson.teacher_id == teacher_id)
         .filter(Lesson.status != "cancelled")
         .filter(Lesson.end_at > start_at)   # existing ends AFTER new starts
         .filter(Lesson.start_at < end_at))  # existing starts BEFORE new ends
    if exclude_id:
        q = q.filter(Lesson.id != exclude_id)
    return db.session.query(q.exists()).scalar()

def has_overlap_for_student(student_id, start_at, end_at, exclude_id=None):
    q = (Lesson.query
         .filter(Lesson.student_id == student_id)
         .filter(Lesson.status != "cancelled")
         .filter(Lesson.end_at > start_at)
         .filter(Lesson.start_at < end_at))
    if exclude_id:
        q = q.filter(Lesson.id != exclude_id)
    return db.session.query(q.exists()).scalar()
