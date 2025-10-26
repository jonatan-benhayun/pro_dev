from flask import Flask, url_for
import os
import time
from flask_login import current_user
from flask_migrate import Migrate
from sqlalchemy import text
from app.models import GRADE_LABELS, GRADE_CHOICES
from .extensions import db, login_manager
from app.blueprints.student import student_bp
from app.constants import PAYMENT_METHODS



login_manager.login_view = "auth.login"
migrate = Migrate()


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    from dotenv import load_dotenv
    load_dotenv()
    
    # Config (env with safe defaults)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me")
    os.makedirs(app.instance_path, exist_ok=True)
    materials_path = os.path.join(app.instance_path, "materials")
    os.makedirs(materials_path, exist_ok=True)
    db_path = os.path.join(app.instance_path, "app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_URL")
        or f"sqlite:///{db_path}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MATERIALS_UPLOAD_PATH"] = materials_path
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["MATERIALS_ALLOWED_EXTENSIONS"] = {
        "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "png", "jpg", "jpeg", "gif", "zip", "rar", "mp4", "mp3"
    }

    # ---- Email config (SMTP) ----  ← (זה ה"1")
    app.config.update(
        MAIL_SERVER=os.getenv("MAIL_SERVER", ""),         # למשל: smtp.gmail.com
        MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),     # 587=STARTTLS, 465=SSL
        MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),     # שם משתמש SMTP
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),     # סיסמה/סיסמת אפליקציה
        MAIL_USE_TLS=(os.getenv("MAIL_USE_TLS", "1") == "1"),
        MAIL_USE_SSL=(os.getenv("MAIL_USE_SSL", "0") == "1"),
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com"),
        TEACHER_EMAIL=os.getenv("TEACHER_EMAIL", ""),     # כתובת המורה לקבלת לידים
    )

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Import models so SQLAlchemy knows them
    from . import models  # noqa: F401

    # Register blueprints
    from .auth import auth_bp
    from .main import main_bp
    from .teacher import teacher_bp
    from .admin import admin_bp
    from app.blueprints.lessons import bp as lessons_bp
    from app.routes_ping import bp as sys_bp

    app.register_blueprint(sys_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(lessons_bp)


    # Template context: dynamic home link based on user role
    @app.context_processor
    def inject_home_url():
        def home_url():
            if getattr(current_user, "is_authenticated", False):
                role = getattr(current_user, "role", None)
                if role == "student":
                    return url_for("student.dashboard")
                if role == "teacher":
                    return url_for("teacher.dashboard")
                return url_for("main.dashboard")
            return url_for("main.landing")
        return {"home_url": home_url}

    # Diagnostics
    print("CWD:", os.getcwd())
    print("APP ROOT:", app.root_path)
    print("TEMPLATES:", os.path.abspath(app.template_folder))
    print("STATIC:", os.path.abspath(app.static_folder))
	
    def inject_payment_constants():
        return dict(PAYMENT_METHODS=PAYMENT_METHODS)

    @app.get("/__routes")
    def __routes():
        rows = [f"{r.rule}  ->  {r.endpoint}" for r in app.url_map.iter_rules()]
        return "<pre>" + "\n".join(sorted(rows)) + "</pre>"

    @app.get("/healthz")
    def healthz():
        return "OK"
    
    @app.context_processor
    def inject_grade_helpers():
        def grade_label(val):
            try:
                return GRADE_LABELS.get(int(val), val)
            except (TypeError, ValueError):
                return val or "ללא כיתה"
        return {"grade_choices": GRADE_CHOICES, "grade_label": grade_label}

    # Login loader lives in models.py (already registered)

    # Create tables / wait for DB
    retries = int(os.getenv("DB_INIT_RETRIES", "20"))
    delay = float(os.getenv("DB_INIT_DELAY", "1.5"))
    created = False
    for attempt in range(1, retries + 1):
        try:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
                db.create_all()
            created = True
            break
        except Exception as e:  # pragma: no cover - startup only
            print(f"[create_app] DB not ready (attempt {attempt}/{retries}): {e}")
            time.sleep(delay)
    if not created:
        print("[create_app] Proceeding without create_all; DB still unavailable.")

    return app
