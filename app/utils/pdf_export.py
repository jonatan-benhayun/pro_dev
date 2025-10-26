from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Tuple

from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_NAME = "LessonAssistant"
FONT_PATH = Path(__file__).resolve().parent.parent / "static" / "fonts" / "Assistant-Regular.ttf"
FALLBACK_FONTS = [
    FONT_PATH,
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
]

_FONT_READY = False


def _ensure_font_registered() -> None:
    global _FONT_READY
    if _FONT_READY:
        return
    for candidate in FALLBACK_FONTS:
        if candidate and candidate.exists():
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(candidate), validate=False))
            _FONT_READY = True
            return
    raise FileNotFoundError("לא נמצא גופן מתאים ליצוא PDF")


def _wrap_text(line: str, max_width: float, font_size: int) -> List[str]:
    if not line:
        return [""]

    words = line.split(" ")
    lines: List[str] = []
    current: List[str] = []

    def width_of(text: str) -> float:
        display = get_display(text)
        return pdfmetrics.stringWidth(display, FONT_NAME, font_size)

    for word in words:
        candidate = (" ".join(current + [word])).strip()
        if not current:
            current.append(word)
            if width_of(candidate) > max_width:
                # Force-break long single words
                buffer = ""
                for ch in word:
                    tentative = buffer + ch
                    if width_of(tentative) <= max_width or not buffer:
                        buffer = tentative
                        continue
                    lines.append(buffer)
                    buffer = ch
                current = [buffer] if buffer else []
            continue

        if width_of(candidate) <= max_width:
            current.append(word)
            continue

        lines.append(" ".join(current))
        current = [word]
        if width_of(word) > max_width:
            buffer = ""
            for ch in word:
                tentative = buffer + ch
                if width_of(tentative) <= max_width or not buffer:
                    buffer = tentative
                    continue
                lines.append(buffer)
                buffer = ch
            current = [buffer] if buffer else []

    if current:
        lines.append(" ".join(current))

    return lines or [""]


def _draw_wrapped_lines(pdf: canvas.Canvas, raw_line: str, x_right: float, y_pos: float, font_size: int, leading: float, max_width: float) -> float:
    pdf.setFont(FONT_NAME, font_size)
    for part in _wrap_text(raw_line, max_width, font_size):
        display = get_display(part or " ")
        pdf.drawRightString(x_right, y_pos, display)
        y_pos -= leading
    return y_pos


def generate_lessons_summary_pdf(*, teacher_name: str, lessons: Iterable, filters: dict, totals: Tuple[int, float, float]) -> bytes:
    """Create a PDF summary for completed lessons."""
    _ensure_font_registered()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin = 40
    content_width = width - (margin * 2)
    x_right = width - margin
    y = height - margin

    title_font = 18
    body_font = 12
    small_font = 10
    leading_title = title_font + 6
    leading_body = body_font + 6

    pdf.setFont(FONT_NAME, title_font)
    y = _draw_wrapped_lines(pdf, "סיכום שיעורים שהושלמו", x_right, y, title_font, leading_title, content_width)
    y -= 6

    pdf.setFont(FONT_NAME, body_font)
    y = _draw_wrapped_lines(pdf, f"מורה: {teacher_name}", x_right, y, body_font, leading_body, content_width)

    start_label = filters.get("start_date") or "ללא"
    end_label = filters.get("end_date") or "ללא"
    paid_map = {"paid": "שולם", "partial": "שולם חלקית", "unpaid": "לא שולם"}
    paid_label = paid_map.get((filters.get("paid_status") or "").lower(), "ללא")
    student_label = filters.get("student_name") or "ללא"
    payment_label = filters.get("payment_method") or "ללא"

    y = _draw_wrapped_lines(pdf, f"תאריך התחלה מסונן: {start_label}", x_right, y, body_font, leading_body, content_width)
    y = _draw_wrapped_lines(pdf, f"תאריך סיום מסונן: {end_label}", x_right, y, body_font, leading_body, content_width)
    y = _draw_wrapped_lines(pdf, f"תלמיד מסונן: {student_label}", x_right, y, body_font, leading_body, content_width)
    y = _draw_wrapped_lines(pdf, f"סטטוס תשלום: {paid_label}", x_right, y, body_font, leading_body, content_width)
    y = _draw_wrapped_lines(pdf, f"אופן תשלום מסונן: {payment_label}", x_right, y, body_font, leading_body, content_width)

    total_count, total_hours, total_cost = totals
    y -= leading_body / 2
    y = _draw_wrapped_lines(pdf, f"סה\"כ שיעורים: {total_count}", x_right, y, body_font, leading_body, content_width)
    y = _draw_wrapped_lines(pdf, f"סה\"כ שעות: {total_hours:.2f}", x_right, y, body_font, leading_body, content_width)
    y = _draw_wrapped_lines(pdf, f"סה\"כ הכנסות: ₪{total_cost:.2f}", x_right, y, body_font, leading_body, content_width)

    y -= leading_body
    pdf.setFont(FONT_NAME, body_font)

    # Aggregate by student
    per_student = defaultdict(lambda: {
        "name": "",
        "count": 0,
        "total_cost": 0.0,
        "total_minutes": 0,
        "dates": [],
        "payment_methods": set(),
    })

    for lesson in lessons:
        student = getattr(lesson, "student", None)
        entry = per_student[lesson.student_id]
        entry["name"] = getattr(student, "username", "ללא שם")
        entry["count"] += 1
        entry["total_cost"] += float(getattr(lesson, "cost", 0) or 0)
        entry["total_minutes"] += int(getattr(lesson, "duration_minutes", 0) or 0)
        start_at = getattr(lesson, "start_at", None)
        if isinstance(start_at, datetime):
            entry["dates"].append(start_at.date())
        payment_method = getattr(lesson, "payment_method", None)
        if payment_method:
            entry["payment_methods"].add(payment_method)

    if not per_student:
        y = _draw_wrapped_lines(pdf, "לא נמצאו שיעורים להפקה", x_right, y, body_font, leading_body, content_width)
    else:
        for entry in sorted(per_student.values(), key=lambda v: v["name"]):
            y -= leading_body / 2
            if y < margin:
                pdf.showPage()
                pdf.setFont(FONT_NAME, body_font)
                y = height - margin

            student_header = f"תלמיד: {entry['name']}"
            y = _draw_wrapped_lines(pdf, student_header, x_right, y, body_font, leading_body, content_width)

            cost_line = f"מספר שיעורים: {entry['count']} | סכום כולל: ₪{entry['total_cost']:.2f}"
            y = _draw_wrapped_lines(pdf, cost_line, x_right, y, small_font, small_font + 4, content_width)

            hours = entry["total_minutes"] / 60.0 if entry["total_minutes"] else 0
            duration_line = f"סה\"כ שעות: {hours:.2f}"
            y = _draw_wrapped_lines(pdf, duration_line, x_right, y, small_font, small_font + 4, content_width)
            methods = entry["payment_methods"]
            methods_line = "אופני תשלום: " + (", ".join(sorted(methods)) if methods else "ללא מידע")
            y = _draw_wrapped_lines(pdf, methods_line, x_right, y, small_font, small_font + 4, content_width)

            if entry["dates"]:
                unique_dates = sorted({d.strftime("%d/%m/%Y") for d in entry["dates"]})
                dates_line = "תאריכים: " + ", ".join(unique_dates)
                y = _draw_wrapped_lines(pdf, dates_line, x_right, y, small_font, small_font + 4, content_width)

            y -= small_font
            if y < margin:
                pdf.showPage()
                pdf.setFont(FONT_NAME, body_font)
                y = height - margin

    pdf.save()
    return buffer.getvalue()
