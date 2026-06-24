import os, json
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                          logout_user, login_required, current_user)
from flask_apscheduler import APScheduler
from werkzeug.security import generate_password_hash, check_password_hash

# ── App & DB ──────────────────────────────────────────────────

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'audiencias-pf-dev-2026')

DATABASE_URL = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(os.path.dirname(__file__), 'audiencias.db')}")
# Render usa postgres:// mas SQLAlchemy 1.4+ exige postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para continuar.'
login_manager.login_message_category = 'warning'

# ── Modelos ───────────────────────────────────────────────────

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id       = db.Column(db.Integer, primary_key=True)
    nome     = db.Column(db.String(120), nullable=False)
    matricula= db.Column(db.String(20))
    login    = db.Column(db.String(60), unique=True, nullable=False)
    senha    = db.Column(db.String(256), nullable=False)
    role     = db.Column(db.String(20), default='colaborador')  # admin | colaborador
    ativo    = db.Column(db.Boolean, default=True)
    criado_em= db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, raw):
        self.senha = generate_password_hash(raw, method='pbkdf2:sha256')

    def check_senha(self, raw):
        return check_password_hash(self.senha, raw)

    @property
    def is_admin(self):
        return self.role == 'admin'


class Audiencia(db.Model):
    __tablename__ = 'audiencias'
    id              = db.Column(db.Integer, primary_key=True)
    policial        = db.Column(db.String(120), nullable=False)
    matricula       = db.Column(db.String(20))
    numero_processo = db.Column(db.String(80))
    vara            = db.Column(db.String(120))
    local_audiencia = db.Column(db.String(200))
    data_audiencia  = db.Column(db.Date, nullable=False)
    hora_audiencia  = db.Column(db.String(5), nullable=False)
    tipo            = db.Column(db.String(60))
    observacoes     = db.Column(db.Text)
    criado_por_id   = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    criado_em       = db.Column(db.DateTime, default=datetime.utcnow)
    criado_por      = db.relationship('Usuario', backref='audiencias')


class NotificacaoEnviada(db.Model):
    __tablename__ = 'notificacoes_enviadas'
    id           = db.Column(db.Integer, primary_key=True)
    audiencia_id = db.Column(db.Integer, db.ForeignKey('audiencias.id'), nullable=False)
    tipo         = db.Column(db.String(10), nullable=False)
    enviada_em   = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('audiencia_id', 'tipo'),)


class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'
    id        = db.Column(db.Integer, primary_key=True)
    endpoint  = db.Column(db.Text, unique=True, nullable=False)
    p256dh    = db.Column(db.Text, nullable=False)
    auth      = db.Column(db.Text, nullable=False)
    usuario_id= db.Column(db.Integer, db.ForeignKey('usuarios.id'))


# ── Auth helpers ──────────────────────────────────────────────

@login_manager.user_loader
def load_user(uid):
    return Usuario.query.get(int(uid))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Web Push ──────────────────────────────────────────────────

BASE_DIR = os.path.dirname(__file__)
KEY_FILE = os.path.join(BASE_DIR, 'vapid_keys.json')
VAPID = {}
if os.path.exists(KEY_FILE):
    with open(KEY_FILE) as f:
        VAPID = json.load(f)

VAPID_CLAIMS = {"sub": "mailto:admin@pf.gov.br"}


def send_push(sub_info, title, body, tag=''):
    if not VAPID:
        return
    try:
        from pywebpush import webpush, WebPushException
        webpush(subscription_info=sub_info,
                data=json.dumps({"title": title, "body": body, "tag": tag}),
                vapid_private_key=VAPID.get('private_key', ''),
                vapid_claims=VAPID_CLAIMS)
    except Exception:
        pass


def notify_all(title, body, tag=''):
    for s in PushSubscription.query.all():
        send_push({"endpoint": s.endpoint,
                   "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                  title, body, tag)


# ── Scheduler ─────────────────────────────────────────────────

def check_notifications():
    with app.app_context():
        now = datetime.now()
        intervals = {
            '2dias': (timedelta(days=2),  '2 dias'),
            '1dia':  (timedelta(days=1),  '1 dia'),
            '1hora': (timedelta(hours=1), '1 hora'),
        }
        hoje = now.date()
        audiencias = Audiencia.query.filter(Audiencia.data_audiencia >= hoje).all()
        for aud in audiencias:
            try:
                dt = datetime.combine(aud.data_audiencia,
                                      datetime.strptime(aud.hora_audiencia, '%H:%M').time())
            except ValueError:
                continue
            for tipo, (delta, label) in intervals.items():
                if datetime.combine(hoje - timedelta(days=1), datetime.min.time()) > dt:
                    continue
                janela_ini = dt - delta - timedelta(minutes=5)
                janela_fim = dt - delta + timedelta(minutes=5)
                if janela_ini <= now <= janela_fim:
                    ja = NotificacaoEnviada.query.filter_by(
                        audiencia_id=aud.id, tipo=tipo).first()
                    if not ja:
                        titulo = f"⚖️ Audiência em {label}"
                        corpo  = (f"{aud.policial}\n"
                                  f"{aud.vara or 'Vara não informada'}\n"
                                  f"{aud.data_audiencia.strftime('%d/%m/%Y')} às {aud.hora_audiencia}")
                        notify_all(titulo, corpo, tag=f"aud-{aud.id}-{tipo}")
                        db.session.add(NotificacaoEnviada(audiencia_id=aud.id, tipo=tipo))
                        db.session.commit()


scheduler = APScheduler()


# ── Rotas de autenticação ─────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        user = Usuario.query.filter_by(login=request.form['login']).first()
        if user and user.ativo and user.check_senha(request.form['senha']):
            login_user(user, remember=True)
            return redirect(request.args.get('next') or url_for('index'))
        flash('Login ou senha inválidos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── Rotas principais ──────────────────────────────────────────

@app.route('/')
@login_required
def index():
    audiencias = Audiencia.query.order_by(
        Audiencia.data_audiencia.asc(), Audiencia.hora_audiencia.asc()).all()
    hoje = datetime.now().date()
    vapid_public = VAPID.get('public_key', '')
    return render_template('index.html', audiencias=audiencias,
                           hoje=hoje, vapid_public=vapid_public)


@app.route('/audiencia/nova', methods=['POST'])
@login_required
def nova_audiencia():
    d = request.form
    aud = Audiencia(
        policial=d['policial'], matricula=d.get('matricula'),
        numero_processo=d.get('numero_processo'), vara=d.get('vara'),
        local_audiencia=d.get('local_audiencia'),
        data_audiencia=datetime.strptime(d['data_audiencia'], '%Y-%m-%d').date(),
        hora_audiencia=d['hora_audiencia'], tipo=d.get('tipo'),
        observacoes=d.get('observacoes'), criado_por_id=current_user.id
    )
    db.session.add(aud)
    db.session.commit()
    flash('Audiência cadastrada com sucesso!', 'success')
    return redirect(url_for('index'))


@app.route('/audiencia/<int:id>/editar', methods=['POST'])
@login_required
def editar_audiencia(id):
    aud = Audiencia.query.get_or_404(id)
    if not current_user.is_admin and aud.criado_por_id != current_user.id:
        abort(403)
    d = request.form
    aud.policial        = d['policial']
    aud.matricula       = d.get('matricula')
    aud.numero_processo = d.get('numero_processo')
    aud.vara            = d.get('vara')
    aud.local_audiencia = d.get('local_audiencia')
    aud.data_audiencia  = datetime.strptime(d['data_audiencia'], '%Y-%m-%d').date()
    aud.hora_audiencia  = d['hora_audiencia']
    aud.tipo            = d.get('tipo')
    aud.observacoes     = d.get('observacoes')
    NotificacaoEnviada.query.filter_by(audiencia_id=id).delete()
    db.session.commit()
    flash('Audiência atualizada.', 'success')
    return redirect(url_for('index'))


@app.route('/audiencia/<int:id>/excluir', methods=['POST'])
@login_required
@admin_required
def excluir_audiencia(id):
    aud = Audiencia.query.get_or_404(id)
    NotificacaoEnviada.query.filter_by(audiencia_id=id).delete()
    db.session.delete(aud)
    db.session.commit()
    flash('Audiência excluída.', 'info')
    return redirect(url_for('index'))


@app.route('/audiencia/<int:id>/json')
@login_required
def audiencia_json(id):
    aud = Audiencia.query.get_or_404(id)
    return jsonify({
        'id': aud.id, 'policial': aud.policial, 'matricula': aud.matricula,
        'numero_processo': aud.numero_processo, 'vara': aud.vara,
        'local_audiencia': aud.local_audiencia,
        'data_audiencia': aud.data_audiencia.strftime('%Y-%m-%d'),
        'hora_audiencia': aud.hora_audiencia, 'tipo': aud.tipo,
        'observacoes': aud.observacoes
    })


# ── Gerenciamento de usuários (admin) ─────────────────────────

@app.route('/usuarios')
@login_required
@admin_required
def usuarios():
    lista = Usuario.query.order_by(Usuario.nome).all()
    return render_template('usuarios.html', usuarios=lista)


@app.route('/usuarios/novo', methods=['POST'])
@login_required
@admin_required
def novo_usuario():
    d = request.form
    if Usuario.query.filter_by(login=d['login']).first():
        flash('Login já existe.', 'danger')
        return redirect(url_for('usuarios'))
    u = Usuario(nome=d['nome'], matricula=d.get('matricula'),
                login=d['login'], role=d.get('role', 'colaborador'))
    u.set_senha(d['senha'])
    db.session.add(u)
    db.session.commit()
    flash(f'Usuário {u.nome} criado.', 'success')
    return redirect(url_for('usuarios'))


@app.route('/usuarios/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_usuario(id):
    u = Usuario.query.get_or_404(id)
    if u.id == current_user.id:
        flash('Você não pode desativar sua própria conta.', 'danger')
    else:
        u.ativo = not u.ativo
        db.session.commit()
        flash(f'Usuário {"ativado" if u.ativo else "desativado"}.', 'info')
    return redirect(url_for('usuarios'))


@app.route('/usuarios/<int:id>/reset-senha', methods=['POST'])
@login_required
@admin_required
def reset_senha(id):
    u = Usuario.query.get_or_404(id)
    nova = request.form.get('nova_senha', '')
    if len(nova) < 4:
        flash('Senha muito curta (mínimo 4 caracteres).', 'danger')
    else:
        u.set_senha(nova)
        db.session.commit()
        flash(f'Senha de {u.nome} redefinida.', 'success')
    return redirect(url_for('usuarios'))


# ── Minha conta ────────────────────────────────────────────────

@app.route('/minha-conta', methods=['POST'])
@login_required
def minha_conta():
    d = request.form
    atual = d.get('senha_atual', '')
    nova  = d.get('nova_senha', '')
    if not current_user.check_senha(atual):
        flash('Senha atual incorreta.', 'danger')
    elif len(nova) < 4:
        flash('Nova senha muito curta.', 'danger')
    else:
        current_user.set_senha(nova)
        db.session.commit()
        flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('index'))


# ── Push Notifications ────────────────────────────────────────

@app.route('/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    data = request.get_json()
    sub = PushSubscription.query.filter_by(endpoint=data['endpoint']).first()
    if not sub:
        sub = PushSubscription(endpoint=data['endpoint'],
                                p256dh=data['keys']['p256dh'],
                                auth=data['keys']['auth'],
                                usuario_id=current_user.id)
        db.session.add(sub)
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/push/test', methods=['POST'])
@login_required
@admin_required
def push_test():
    notify_all('🔔 Teste — Audiências PF',
               'Notificações funcionando corretamente!', tag='teste')
    return jsonify({'ok': True})


@app.route('/vapid-public-key')
def vapid_public_key():
    return VAPID.get('public_key', ''), 200, {'Content-Type': 'text/plain'}


# ── API: dados para sync ───────────────────────────────────────

@app.route('/api/audiencias')
@login_required
def api_audiencias():
    audiencias = Audiencia.query.order_by(
        Audiencia.data_audiencia.asc(), Audiencia.hora_audiencia.asc()).all()
    return jsonify([{
        'id': a.id, 'policial': a.policial,
        'data': a.data_audiencia.strftime('%Y-%m-%d'),
        'hora': a.hora_audiencia, 'vara': a.vara,
        'tipo': a.tipo, 'criado_por': a.criado_por.nome if a.criado_por else '—'
    } for a in audiencias])


# ── Inicialização ─────────────────────────────────────────────

def init_app():
    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(role='admin').first():
            admin = Usuario(nome='Administrador', login='admin', role='admin', ativo=True)
            admin.set_senha('admin123')
            db.session.add(admin)
            db.session.commit()
            print("👤  Admin criado — login: admin / senha: admin123  (TROQUE A SENHA!)")


if __name__ == '__main__':
    init_app()
    scheduler.api_enabled = True
    scheduler.init_app(app)
    scheduler.add_job(id='check_notifs', func=check_notifications,
                      trigger='interval', minutes=1)
    scheduler.start()
    print("\n✅  Sistema de Audiências PF iniciado!")
    print("🌐  http://localhost:5001\n")
    app.run(debug=False, host='0.0.0.0', port=5001, use_reloader=False)
