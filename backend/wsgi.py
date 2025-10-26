# מצפה שיש app/create_app בפרויקט שלך. אם המבנה שונה, נעדכן אח"כ.
try:
    from app import create_app
    app = create_app()
except Exception:
    # Fallback פשוט כדי שלא נתקע: שרת Flask "שלום" עד שנכוון ל-app האמיתי
    from flask import Flask
    app = Flask(__name__)
    @app.get("/")
    def index():
        return "Backend placeholder is up. Wire your create_app() later."
