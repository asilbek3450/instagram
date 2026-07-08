from app import create_app, db
from app.models.user import User

app = create_app()
with app.app_context():
    existing = User.query.filter_by(email='asilbek').first()
    if not existing:
        admin = User(email='asilbek', role='admin', is_verified=True)
        admin.set_password('asilbekinstatrack23')
        db.session.add(admin)
        db.session.commit()
        print("Admin user 'asilbek' created successfully.")
    else:
        existing.role = 'admin'
        existing.set_password('asilbekinstatrack23')
        existing.is_verified = True
        db.session.commit()
        print("Admin user 'asilbek' updated successfully.")
