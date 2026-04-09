import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

# --- Configurazione Iniziale ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chiave-super-segreta-da-cambiare')

# Configurazione Database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///condo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Modelli del Database ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    condominio_nome = db.Column(db.String(120), nullable=False)
    scadenze = db.relationship('Scadenza', backref='utente', lazy=True)

class Scadenza(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    condomino_email = db.Column(db.String(120), nullable=False)
    condomino_nome = db.Column(db.String(80), nullable=False)
    descrizione = db.Column(db.String(200), nullable=False)
    importo = db.Column(db.Float, nullable=False)
    data_scadenza = db.Column(db.Date, nullable=False)
    stato = db.Column(db.String(20), default='non pagato')

# --- Helper per il Login ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Funzione per Inviare Email (Modificata) ---
def invia_email_promemoria(scadenza, user_email, user_password):
    # Questa funzione sarà chiamata dallo scheduler
    # user_email e user_password saranno presi dal database dell'utente loggato
    # Per semplicità, al momento usiamo una configurazione fissa, ma l'ideale è salvarle per ogni user.
    # Per ora, usiamo le variabili d'ambiente per il mittente.
    mittente_email = os.environ.get('MAIL_USERNAME')
    mittente_password = os.environ.get('MAIL_PASSWORD')
    if not mittente_email or not mittente_password:
        print("Errore: Credenziali email non configurate.")
        return

    oggetto = f"Promemoria scadenza condominiale - {scadenza.descrizione}"
    corpo = f"""Gentile {scadenza.condomino_nome},

Le ricordiamo che il pagamento di {scadenza.descrizione} di €{scadenza.importo:.2f} scade il {scadenza.data_scadenza}.

La invitiamo a saldare quanto prima.

Cordiali saluti,
Amministratore del Condominio {scadenza.utente.condominio_nome}
"""
    msg = MIMEMultipart()
    msg['From'] = mittente_email
    msg['To'] = scadenza.condomino_email
    msg['Subject'] = oggetto
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(mittente_email, mittente_password)
            server.send_message(msg)
        print(f"Promemoria inviato a {scadenza.condomino_email} per scadenza ID {scadenza.id}")
    except Exception as e:
        print(f"Errore invio email per scadenza {scadenza.id}: {e}")

# --- Funzione Schedulata (Da eseguire ogni giorno) ---
def invia_promemoria_programmati():
    print("Esecuzione controllo promemoria...")
    with app.app_context():
        oggi = datetime.now().date()
        data_limite = oggi + timedelta(days=5)
        scadenze_da_inviare = Scadenza.query.filter(
            Scadenza.stato == 'non pagato',
            Scadenza.data_scadenza >= oggi,
            Scadenza.data_scadenza <= data_limite
        ).all()
        for scadenza in scadenze_da_inviare:
            user = User.query.get(scadenza.user_id)
            # Recupera le credenziali email dell'utente dal database (da implementare)
            # Per ora, usiamo una variabile d'ambiente fissa.
            invia_email_promemoria(scadenza, None, None)
        print(f"Controllo completato. Promemoria inviati per {len(scadenze_da_inviare)} scadenze.")

# --- Avvio Scheduler ---
scheduler = BackgroundScheduler()
scheduler.add_job(invia_promemoria_programmati, 'interval', days=1)
scheduler.start()

# --- Rotte dell'App ---
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'] # Attenzione: password in chiaro!
        user = User.query.filter_by(username=username).first()
        if user and user.password == password: # Da migliorare con hashing!
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Credenziali non valide', 'danger')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    scadenze = Scadenza.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', scadenze=scadenze)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# ... (Aggiungi qui le rotte per aggiungere/modificare/eliminare scadenze) ...
# Le rotte per aggiungere, modificare, eliminare scadenze sono simili a prima,
# ma filtrando per current_user.id e salvando user_id nella nuova scadenza.
# Te le fornisco nel prossimo passaggio per non appesantire.

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)