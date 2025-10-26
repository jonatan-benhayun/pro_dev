# app/utils/mail.py
import os
import smtplib
import ssl
import mimetypes
from email.message import EmailMessage
from typing import Iterable, Optional, Union, List
from flask import current_app


def _as_list(x) -> List[str]:
    if not x:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i) for i in x if i]
    return [str(x)]


def send_email(
    subject: str,
    text_body: str,
    to: Union[str, Iterable[str]],
    *,
    html_body: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    attachments: Optional[Iterable[str]] = None,  # רשימת נתיבי קבצים לצירוף (אופציונלי)
) -> bool:
    """
    שולח מייל דרך הגדרות SMTP שב- Flask current_app.config.
    מחזיר True אם נשלח בהצלחה, אחרת False (וכותב לוג עם exception).

    נדרשות ההגדרות:
      MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD,
      MAIL_USE_TLS (1/0), MAIL_USE_SSL (1/0),
      MAIL_DEFAULT_SENDER (אופציונלי – אם לא, נשתמש ב- MAIL_USERNAME)
    """

    cfg = current_app.config
    server = cfg.get("MAIL_SERVER")
    port = int(cfg.get("MAIL_PORT") or 0)
    username = cfg.get("MAIL_USERNAME")
    password = cfg.get("MAIL_PASSWORD")
    use_tls = bool(cfg.get("MAIL_USE_TLS"))
    use_ssl = bool(cfg.get("MAIL_USE_SSL"))
    sender = cfg.get("MAIL_DEFAULT_SENDER") or username or "noreply@example.com"

    if not server or not port:
        current_app.logger.warning("send_email: missing MAIL_SERVER/MAIL_PORT.")
        return False

    to_list = _as_list(to)
    cc_list = _as_list(cc)
    bcc_list = _as_list(bcc)
    all_rcpts = to_list + cc_list + bcc_list
    if not all_rcpts:
        current_app.logger.warning("send_email: no recipients.")
        return False

    # בונים הודעה
    msg = EmailMessage()
    msg["Subject"] = str(subject)
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to

    # גוף ההודעה: תמיד טקסט, ואם יש HTML נוסיף כ-alternative
    msg.set_content(text_body or "")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    # צרופות (אופציונלי)
    for path in _as_list(attachments):
        try:
            ctype, encoding = mimetypes.guess_type(path)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(path, "rb") as f:
                data = f.read()
            filename = os.path.basename(path)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
        except Exception as e:
            current_app.logger.exception("send_email: failed to attach %r: %r", path, e)

    # שליחה בפועל
    try:
        if use_ssl or port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(server, port, context=context) as smtp:
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg, from_addr=sender, to_addrs=all_rcpts)
        else:
            with smtplib.SMTP(server, port) as smtp:
                smtp.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg, from_addr=sender, to_addrs=all_rcpts)
        return True
    except Exception as e:
        current_app.logger.exception("send_email failed: %r", e)
        return False
