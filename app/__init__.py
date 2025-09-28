from flask import Flask

def create_app():
    app = Flask(__name__)

    from app.routes.webhook import webhook_bp
    
    app.register_blueprint(webhook_bp)

    return app
