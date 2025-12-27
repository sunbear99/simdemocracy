from flask import Flask
from config import Config
from app.extensions import db

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Initialize Database
    db.init_app(app)

    # 2. Create Tables (if they don't exist)
    with app.app_context():
        # This imports models so SQLAlchemy knows what to build
        from app import models 
        db.create_all()

    # 3. Register Blueprints (The Routes)
    from app.routes import main, auth, admin
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)

    return app