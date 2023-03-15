from sqlalchemy import exists
from app.user.models import db, User

if not db.session.query(exists(User.id)).scalar():
    user = User(email='admin@slog.ai', active=True)
    user.hash_password('mihailoconte')
    db.session.add(user)
    db.session.commit()
else:
    print("User table is not empty, skipping seeding.")
