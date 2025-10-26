from flask import Blueprint, jsonify
from app.extensions import db
from sqlalchemy import text

bp = Blueprint("sys", __name__)

@bp.get("/api/ping")
def ping():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "db": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "db": "down", "message": str(e)}), 500

