from flask import Flask, jsonify, request, render_template
import os
import sqlite3
import jwt
import datetime
import hmac
from prometheus_client import Counter, start_http_server
from prometheus_flask_exporter import PrometheusMetrics
from flask_limiter import Limiter

app = Flask(__name__, static_folder="static")
metrics = PrometheusMetrics(app, path=None)
ECHECS_LOGIN = Counter("rpg_api_login_echecs", "Tentatives de connexion refusees sur /login")

FAIRE_CONFIANCE_TRUE_CLIENT_IP = os.environ.get("TRUST_TRUE_CLIENT_IP") == "1"


def ip_client():
    if FAIRE_CONFIANCE_TRUE_CLIENT_IP:
        ip = request.headers.get("True-Client-IP")
        if ip:
            return ip
    return request.remote_addr


limiter = Limiter(ip_client, app=app, storage_uri="memory://")


def read_secret(env_name, file_path):
    if file_path and os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            value = f.read().strip()
    else:
        value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(
            f"Secret manquant : {env_name} (ni fichier {file_path}, ni variable d'environnement)"
        )
    return value


TOKEN_SECRET = read_secret("API_SECRET_KEY", "/etc/secrets/API_SECRET_KEY")
ADMIN_USER = read_secret("ADMIN_USERNAME", "/etc/secrets/ADMIN_USERNAME")
ADMIN_PASSWORD = read_secret("ADMIN_PASSWORD", "/etc/secrets/ADMIN_PASSWORD")
DATABASE = os.environ.get("API_DB_PATH", "database.db")

ACTIONS_DISPONIBLES = ["JOKE", "COMPLIMENT", "DANCE", "PET", "DISCUSS", "OBSERVE", "INSULT", "THREATEN"]
ACTIONS_PAR_CATEGORIE = {
    "NORMAL": 2,
    "MINIBOSS": 3,
    "BOSS": 4
}


def get_db():
    db_path = app.config.get("DATABASE", DATABASE)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db_existe = os.path.exists(DATABASE)
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS monstres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categorie TEXT,
            nom TEXT,
            hp TEXT,
            atk TEXT,
            def TEXT,
            mercy TEXT,
            act1 TEXT,
            act2 TEXT,
            act3 TEXT,
            act4 TEXT
        )
    """)
    conn.commit()

    if not db_existe:
        with open("monsters.csv", "r", encoding="utf-8-sig") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue

                champs = ligne.split(";")

                if len(champs) >= 6:
                    if len(champs) > 6:
                        act1 = champs[6]
                    else:
                        act1 = "-"

                    if len(champs) > 7:
                        act2 = champs[7]
                    else:
                        act2 = "-"

                    if len(champs) > 8:
                        act3 = champs[8]
                    else:
                        act3 = "-"

                    if len(champs) > 9:
                        act4 = champs[9]
                    else:
                        act4 = "-"

                    conn.execute(
                        "INSERT INTO monstres (categorie, nom, hp, atk, def, mercy, act1, act2, act3, act4) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (champs[0], champs[1], champs[2], champs[3], champs[4], champs[5], act1, act2, act3, act4)
                    )

        conn.commit()
    conn.close()

def verifier_token():
    auth = request.headers.get("Authorization")
    if not auth:
        return False
    if not auth.startswith("Bearer "):
        return False

    token = auth.split(" ")[1]

    try:
        jwt.decode(token, TOKEN_SECRET, algorithms=["HS256"])
        return True
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False

@app.after_request
def ajouter_headers_securite(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self'; "     # response.headers["X-Frame-Options"] = "DENY"
        "font-src 'self'; "
        "connect-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

    if request.path.startswith("/static/") and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    return response

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/actions", methods=["GET"])
def get_actions():
    return jsonify(ACTIONS_DISPONIBLES)


@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute;20 per hour;50 per day")
def login():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"erreur": "Donnees manquantes"}), 400

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        ECHECS_LOGIN.inc()
        return jsonify({"erreur": "Identifiants incorrects"}), 401

    utilisateur_ok = hmac.compare_digest(username.encode("utf-8"), ADMIN_USER.encode("utf-8"))
    mot_de_passe_ok = hmac.compare_digest(password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))

    if not (utilisateur_ok and mot_de_passe_ok):
        ECHECS_LOGIN.inc()
        return jsonify({"erreur": "Identifiants incorrects"}), 401

    token = jwt.encode(
        {
            "username": username,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
        },
        TOKEN_SECRET,
        algorithm="HS256"
    )

    return jsonify({"token": token})


@app.route("/monstres", methods=["GET"])
def get_monstres():
    conn = get_db()
    monstres = conn.execute("SELECT * FROM monstres").fetchall()
    conn.close()

    resultat = []
    for m in monstres:
        resultat.append(dict(m))

    return jsonify(resultat)


@app.route("/monstres/<nom>", methods=["GET"])
def get_monstre(nom):
    conn = get_db()
    monstre = conn.execute(
        "SELECT * FROM monstres WHERE LOWER(nom) = LOWER(?)", (nom,)
    ).fetchone()
    conn.close()

    if monstre is None:
        return jsonify({"erreur": "Monstre introuvable"}), 404

    return jsonify(dict(monstre))


@app.route("/monstres", methods=["POST"])
def ajouter_monstre():
    if not verifier_token():
        return jsonify({"erreur": "Non autorise"}), 401

    data = request.json
    if not isinstance(data, dict):
        return jsonify({"erreur": "Donnees manquantes"}), 400

    champs_requis = ["categorie", "nom", "hp", "atk", "def", "mercy", "act1", "act2"]
    for champ in champs_requis:
        if not data.get(champ):
            return jsonify({"erreur": f"Le champ {champ} est manquant ou vide"}), 400

    categories_valides = ["NORMAL", "MINIBOSS", "BOSS"]
    if data["categorie"].upper() not in categories_valides:
        return jsonify({"erreur": "La categorie doit etre NORMAL, MINIBOSS ou BOSS"}), 400

    champs_numeriques = ["hp", "atk", "def", "mercy"]
    for champ in champs_numeriques:
        try:
            valeur = int(data[champ])
            if valeur <= 0:
                return jsonify({"erreur": f"Le champ {champ} doit etre un nombre positif"}), 400
        except ValueError:
            return jsonify({"erreur": f"Le champ {champ} doit etre un nombre"}), 400

    nb_actions = ACTIONS_PAR_CATEGORIE[data["categorie"].upper()]
    actions = []
    for i in range(4):
        actions.append(data.get(f"act{i+1}", "-"))

    actions_renseignees = []
    for a in actions[:nb_actions]:
        if a and a != "-":
            actions_renseignees.append(a)

    if len(actions_renseignees) != nb_actions:
        return jsonify({"erreur": f"Un {data['categorie']} doit avoir exactement {nb_actions} actions"}), 400

    if len(actions_renseignees) != len(set(actions_renseignees)):
        return jsonify({"erreur": "Les actions doivent etre toutes differentes"}), 400

    for action in actions_renseignees:
        if action not in ACTIONS_DISPONIBLES:
            return jsonify({"erreur": f"Action {action} invalide"}), 400

    conn = get_db()

    existant = conn.execute(
        "SELECT * FROM monstres WHERE LOWER(nom) = LOWER(?)", (data["nom"],)
    ).fetchone()

    if existant:
        conn.close()
        return jsonify({"erreur": f"{data['nom']} existe deja"}), 409

    conn.execute(
        "INSERT INTO monstres (categorie, nom, hp, atk, def, mercy, act1, act2, act3, act4) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (data["categorie"], data["nom"], data["hp"], data["atk"], data["def"], data["mercy"],
         actions[0], actions[1], actions[2], actions[3])
    )
    conn.commit()
    conn.close()

    return jsonify({"message": f"{data['nom']} ajoute"}), 201


@app.route("/monstres/<nom>", methods=["DELETE"])
def supprimer_monstre(nom):
    if not verifier_token():
        return jsonify({"erreur": "Non autorise"}), 401

    conn = get_db()
    resultat = conn.execute(
        "DELETE FROM monstres WHERE LOWER(nom) = LOWER(?)", (nom,)
    ).rowcount
    conn.commit()
    conn.close()

    if resultat == 0:
        return jsonify({"erreur": "Monstre introuvable"}), 404

    return jsonify({"message": f"{nom} supprime"})


if __name__ == "__main__":
    init_db()
    start_http_server(9100)
    app.run(host="0.0.0.0", port=5000)  # nosec B104 - necessaire pour accepter les connexions depuis Docker/Kubernetes  # nosemgrep: python.flask.security.audit.app-run-param-config.avoid_app_run_with_bad_host
