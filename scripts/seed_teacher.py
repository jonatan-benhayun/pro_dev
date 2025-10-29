from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():
    # פרטי המורה הקבוע
    email = "jonatan0897@gmail.com"
    username = "לימור"
    password = "123456" 
    role = "teacher"

    user = User.query.filter_by(email=email).first()
    if user:
        print("✅ Teacher already exists:", user.email)
    else:
        new_user = User(email=email, username=username, role=role)
        try:
            new_user.set_password(password)
        except Exception:
            # אם אין פונקציה set_password
            new_user.password = password
        db.session.add(new_user)
        db.session.commit()
        print(f"✅ Created teacher: {email}, password={password}")
