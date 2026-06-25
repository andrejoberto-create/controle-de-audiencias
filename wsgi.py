import os
from app import app, db, Usuario
from werkzeug.security import generate_password_hash

def create_tables():
    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(role='admin').first():
            admin = Usuario(
                nome='Administrador',
                login='admin',
                role='admin',
                ativo=True
            )
            admin.senha = generate_password_hash('admin123', method='pbkdf2:sha256')
            db.session.add(admin)
            db.session.commit()
            print("Admin criado: login=admin senha=admin123")

create_tables()

# Inicia scheduler apenas se não for ambiente multi-worker
try:
    from flask_apscheduler import APScheduler
    from app import check_notifications, scheduler
    if not scheduler.running:
        scheduler.api_enabled = True
        scheduler.init_app(app)
        scheduler.add_job(id='check_notifs', func=check_notifications,
                          trigger='interval', minutes=1)
        scheduler.start()
except Exception as e:
    print(f"Scheduler não iniciado: {e}")

if __name__ == '__main__':
    app.run()
