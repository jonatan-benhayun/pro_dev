# from . import db , login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
from datetime import datetime
from .extensions import db, login_manager
from decimal import Decimal
from sqlalchemy import Index, Numeric, event



GRADE_LABELS = { 1:"א׳",2:"ב׳",3:"ג׳",4:"ד׳",5:"ה׳",6:"ו׳",7:"ז׳",8:"ח׳",9:"ט׳",10:"י׳",11:"י״א",12:"י״ב" }
GRADE_CHOICES = list(GRADE_LABELS.items())           # [(1,"א׳"), ...]
VALID_GRADES  = set(GRADE_LABELS.keys())             # {1,2,...,12}

class RoleEnum(str, Enum):
    student = "student"
    teacher = "teacher"
    admin   = "admin"

class User(UserMixin, db.Model):        # ← יורש מ־UserMixin
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    grade = db.Column(db.String(10))
    role = db.Column(db.String(20), default="student", nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    teacher = db.relationship('User', remote_side=[id], backref='students', foreign_keys=[teacher_id])
    # hourly_rate = db.Column(db.Numeric(10, 2))
    student_rate_cents = db.Column(db.Integer, nullable=False, default=11000, server_default="11000")
    school = db.Column(db.String(50), index=True)   # בית ספר (אופציונלי)


    def is_teacher(self):
        return str(self.role) == "teacher"

    def is_admin(self):
        return str(self.role) == "admin"
    
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
    @property
    def student_rate(self) -> float:
        """תעריף לשעה בשקלים (מהשדה באגורות)"""
        return round((self.student_rate_cents or 0) / 100.0, 2)

    @property
    def student_rate_effective(self) -> float:
        """תמיד מחזיר מחיר תקין (דיפולט 110 אם חסר/0)"""
        cents = self.student_rate_cents if self.student_rate_cents is not None else 11000
        if cents <= 0:
            cents = 11000
        return round(cents / 100.0, 2)

    def set_student_rate(self, shekels: float) -> None:
        cents = int(round((shekels or 0) * 100))
        self.student_rate_cents = max(0, cents)

    @property
    def hourly_rate(self):
        return self.student_rate

    @hourly_rate.setter
    def hourly_rate(self, value):
        try:
            self.set_student_rate(float(value or 0))
        except (TypeError, ValueError):
            self.set_student_rate(0.0)
        
    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return User.query.get(int(user_id))
        except (TypeError, ValueError):
            return None
    
    
class Lesson(db.Model):
    __tablename__ = "lesson"

    id = db.Column(db.Integer, primary_key=True)

    # קשרים ל-User
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    teacher = db.relationship("User", foreign_keys=[teacher_id], backref="lessons_as_teacher")
    student = db.relationship("User", foreign_keys=[student_id], backref="lessons_as_student")

    # זמנים
    start_at = db.Column(db.DateTime, nullable=False)
    end_at   = db.Column(db.DateTime, nullable=False)

    # סטטוס ותמחור
    status = db.Column(db.String(20))
    hourly_rate_cents         = db.Column(db.Integer, nullable=False, server_default="11000")
    hourly_rate_at_time_cents = db.Column(db.Integer, nullable=False, server_default="11000")

    # תשלומים
    paid_status = db.Column(db.String(20), nullable=False, default="unpaid")  # unpaid / partial / paid
    paid_amount = db.Column(db.Float,       nullable=False, default=0.0)

    payment_method = db.Column(db.String(30), nullable=True)


    # משך השיעור בדקות (נשמר בעמודה)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)

    # הערות
    notes = db.Column(db.Text)

    # אינדקסים מועילים
    __table_args__ = (
        db.CheckConstraint('end_at > start_at', name='ck_lesson_time_order'),
        Index("ix_lesson_teacher_start", "teacher_id", "start_at"),
        Index("ix_lesson_student_start", "student_id", "start_at"),
    )


    # חישובי עזר
    @property
    def cost(self) -> float:
        hours = (self.duration_minutes or 0) / 60.0
        return round(self.hourly_rate_at_time * hours, 2)

    @property
    def hourly_rate(self) -> float:
        return round((self.hourly_rate_cents or 0) / 100.0, 2)

    @hourly_rate.setter
    def hourly_rate(self, value):
        self.hourly_rate_cents = int(round(float(value or 0) * 100))

    @property
    def hourly_rate_at_time(self) -> float:
        return round((self.hourly_rate_at_time_cents or 0) / 100.0, 2)

    @hourly_rate_at_time.setter
    def hourly_rate_at_time(self, value):
        self.hourly_rate_at_time_cents = int(round(float(value or 0) * 100))

    @property
    def amount_due(self) -> float:
        """יתרה לתשלום (עלות פחות סכום ששולם)."""
        return max(self.cost - float(self.paid_amount or 0.0), 0.0)

    def __repr__(self) -> str:
        return f"<Lesson id={self.id} teacher={self.teacher_id} student={self.student_id} start={self.start_at} end={self.end_at}>"


class StudentMaterial(db.Model):
    __tablename__ = "student_material"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    link_url = db.Column(db.String(500))
    file_path = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship("User", foreign_keys=[student_id], backref="materials_received")
    teacher = db.relationship("User", foreign_keys=[teacher_id], backref="materials_created")

    def has_file(self) -> bool:
        return bool(self.file_path)

    def __repr__(self) -> str:
        return f"<StudentMaterial id={self.id} student={self.student_id} title={self.title!r}>"

@event.listens_for(Lesson, "before_insert")

def _lesson_before_insert(mapper, connection, target: "Lesson"):
    # אם לא קיים צילום תעריף — קבע לפי hourly_rate (או 110 כברירת מחדל)
    if not target.hourly_rate_at_time:
        hr = target.hourly_rate if target.hourly_rate else 110.0
        target.hourly_rate_at_time = float(hr)

    # אם לא הוגדר משך — חשב לפי start/end
    if (not target.duration_minutes) and target.start_at and target.end_at:
        delta_min = int(round((target.end_at - target.start_at).total_seconds() / 60.0))
        target.duration_minutes = max(0, delta_min)


@event.listens_for(Lesson, "before_update")
def _lesson_before_update(mapper, connection, target: "Lesson"):
    # אם שינו טווח ולא קיים משך — השלם
    if target.start_at and target.end_at and (not target.duration_minutes):
        delta_min = int(round((target.end_at - target.start_at).total_seconds() / 60.0))
        target.duration_minutes = max(0, delta_min)

class Lead(db.Model):
    __tablename__ = "lead"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(255))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Lead id={self.id} name={self.name!r} phone={self.phone!r}>"
