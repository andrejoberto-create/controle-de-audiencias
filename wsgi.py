import os
import traceback

print("=== Iniciando wsgi.py ===")

try:
    from app import app, db, Usuario
    print("✓ app importado")
except Exception as e:
    print(f"ERRO ao importar app: {e}")
    traceback.print_exc()
    raise

try:
    with app.app_context():
        db.create_all()
        print("✓ tabelas criadas")
        if not Usuario.query.filter_by(role='admin').first():
            from werkzeug.security import generate_password_hash
            admin = Usuario(
                nome='Administrador', login='admin',
                role='admin', ativo=True
            )
            admin.senha = generate_password_hash('admin123', method='pbkdf2:sha256')
            db.session.add(admin)
            db.session.commit()
            print("✓ admin criado")
        else:
            print("✓ admin já existe")
except Exception as e:
    print(f"ERRO ao inicializar banco: {e}")
    traceback.print_exc()

try:
    from flask_apscheduler import APScheduler
    from app import check_notifications
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.add_job(id='check_notifs', func=check_notifications,
                      trigger='interval', minutes=1)
    scheduler.start()
    print("✓ scheduler iniciado")
except Exception as e:
    print(f"Scheduler não iniciado (não crítico): {e}")

print("=== wsgi.py pronto ===")

if __name__ == '__main__':
    app.run()
