from app import db
from app.models.user import User
from flask_jwt_extended import create_access_token, create_refresh_token
from datetime import datetime

class AuthService:
    @staticmethod
    def register_user(email, password, role='user'):
        if not email or not password:
            raise ValueError("Email and password are required")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            raise ValueError("User with this email already exists")

        user = User(email=email, role=role, is_verified=False)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def login_user(email, password):
        if not email or not password:
            raise ValueError("Email and password are required")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            raise ValueError("Invalid email or password")

        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        return {
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }

    @staticmethod
    def verify_email(user_id):
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        
        user.is_verified = True
        db.session.commit()
        return user

    @staticmethod
    def get_user_profile(user_id):
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        return user.to_dict()

    @staticmethod
    def update_profile(user_id, email, password=None):
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")

        if email and email != user.email:
            existing = User.query.filter_by(email=email).first()
            if existing:
                raise ValueError("Email is already in use by another user")
            user.email = email

        if password:
            user.set_password(password)

        db.session.commit()
        return user.to_dict()
