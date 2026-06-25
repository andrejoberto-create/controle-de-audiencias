from app import app, init_app, scheduler, check_notifications

with app.app_context():
    init_app()

if not scheduler.running:
    scheduler.api_enabled = True
    scheduler.init_app(app)
    scheduler.add_job(id='check_notifs', func=check_notifications,
                      trigger='interval', minutes=1)
    scheduler.start()

if __name__ == '__main__':
    app.run()
