from prometheus_client import REGISTRY
import pytest
import jwt
import datetime
import sys
import os
import tempfile


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module
from app import app as flask_app
from app import read_secret
from app import get_db

SECRET = "cle-de-test-uniquement-pour-pytest-0123456789"  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret

@pytest.fixture(autouse=True)
def secrets_de_test(monkeypatch):
    monkeypatch.setattr(app_module, "ADMIN_USER", "admin")
    monkeypatch.setattr(app_module, "ADMIN_PASSWORD", "password")
    monkeypatch.setattr(app_module, "TOKEN_SECRET", "cle-de-test-uniquement-pour-pytest-0123456789")


@pytest.fixture(autouse=True)
def reinitialiser_limiteur():
    app_module.limiter.reset()


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    flask_app.config["TESTING"] = True  # nosemgrep: python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_TESTING
    flask_app.config["DATABASE"] = db_path

    with flask_app.app_context():
        db = get_db()
        db.execute("""
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
        db.commit()

    with flask_app.test_client() as client:
        yield client

@pytest.fixture
def token_valide():
    return jwt.encode( # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        {"username": "admin", "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)},
        SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def token_expire():
    return jwt.encode( # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        {"username": "admin", "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )


def test_index(client):
    assert client.get("/").status_code == 200


def test_get_actions(client):
    reponse = client.get("/actions")
    assert reponse.status_code == 200
    data = reponse.get_json()
    assert "JOKE" in data
    assert "DANCE" in data


def test_login_succes(client):
    reponse = client.post("/login", json={"username": "admin", "password": "password"})
    assert reponse.status_code == 200
    assert "token" in reponse.get_json()


def test_login_mauvais_mot_de_passe(client):
    assert client.post("/login", json={"username": "admin", "password": "mauvais"}).status_code == 401


def test_login_mauvais_username(client):
    assert client.post("/login", json={"username": "inconnu", "password": "password"}).status_code == 401


def test_login_sans_donnees(client):
    assert client.post("/login", json=None, content_type="application/json").status_code == 400

def test_login_sans_mot_de_passe(client):
    assert client.post("/login", json={"username": "admin"}).status_code == 401


def test_ajouter_monstre_sans_donnees(client, token_valide):
    reponse = client.post(
        "/monstres",
        json=None,
        content_type="application/json",
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_json_liste(client, token_valide):
    reponse = client.post(
        "/monstres",
        json=["pas", "un", "objet"],
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400

def test_get_monstres(client):
    reponse = client.get("/monstres")
    assert reponse.status_code == 200
    assert isinstance(reponse.get_json(), list)


def test_get_monstre_introuvable(client):
    assert client.get("/monstres/monstre_qui_nexiste_pas_xyz").status_code == 404


def test_get_monstre_existant(client, token_valide):
    client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "Slime", "hp": "20", "atk": "5", "def": "3", "mercy": "30", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    reponse = client.get("/monstres/Slime")
    assert reponse.status_code == 200
    assert reponse.get_json()["nom"] == "Slime"


def test_get_monstre_insensible_casse(client, token_valide):
    client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "Dragon", "hp": "100", "atk": "20", "def": "15", "mercy": "10", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert client.get("/monstres/dragon").status_code == 200


def test_ajouter_monstre_sans_token(client):
    reponse = client.post("/monstres", json={
        "categorie": "NORMAL", "nom": "TestMonstre",
        "hp": "10", "atk": "5", "def": "3", "mercy": "50",
        "act1": "JOKE", "act2": "DANCE",
    })
    assert reponse.status_code == 401


def test_ajouter_monstre_token_expire(client, token_expire):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_expire}"},
    )
    assert reponse.status_code == 401


def test_ajouter_monstre_token_invalide(client):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": "Bearer tokenbidon"},
    )
    assert reponse.status_code == 401


def test_ajouter_monstre_normal_succes(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "Goblin", "hp": "15", "atk": "4", "def": "2", "mercy": "40", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 201


def test_ajouter_monstre_miniboss_succes(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "MINIBOSS", "nom": "OrcChef", "hp": "80", "atk": "15", "def": "10", "mercy": "20", "act1": "JOKE", "act2": "DANCE", "act3": "PET"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 201


def test_ajouter_monstre_boss_succes(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "BOSS", "nom": "DarkLord", "hp": "500", "atk": "50", "def": "40", "mercy": "5", "act1": "JOKE", "act2": "DANCE", "act3": "PET", "act4": "DISCUSS"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 201


def test_ajouter_monstre_categorie_invalide(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "INVALID", "nom": "TestMonstre", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_hp_negatif(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "-5", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_hp_zero(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "0", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_hp_non_numerique(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "abc", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_actions_dupliquees(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "JOKE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_action_invalide(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "FAKEACTION"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_trop_peu_actions(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_champ_manquant(client, token_valide):
    reponse = client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "TestMonstre", "hp": "10", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 400


def test_ajouter_monstre_doublon(client, token_valide):
    payload = {"categorie": "NORMAL", "nom": "Duplicata", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"}
    headers = {"Authorization": f"Bearer {token_valide}"}
    client.post("/monstres", json=payload, headers=headers)
    assert client.post("/monstres", json=payload, headers=headers).status_code == 409


def test_supprimer_monstre_sans_token(client):
    assert client.delete("/monstres/nimportequoi").status_code == 401


def test_supprimer_monstre_introuvable(client, token_valide):
    reponse = client.delete(
        "/monstres/monstre_qui_nexiste_pas_xyz",
        headers={"Authorization": f"Bearer {token_valide}"},
    )
    assert reponse.status_code == 404


def test_supprimer_monstre_succes(client, token_valide):
    headers = {"Authorization": f"Bearer {token_valide}"}
    client.post(
        "/monstres",
        json={"categorie": "NORMAL", "nom": "ASupprimer", "hp": "10", "atk": "5", "def": "3", "mercy": "50", "act1": "JOKE", "act2": "DANCE"},
        headers=headers,
    )
    assert client.delete("/monstres/ASupprimer", headers=headers).status_code == 200
    assert client.get("/monstres/ASupprimer").status_code == 404


def test_headers_securite_presents(client):
    reponse = client.get("/monstres")
    assert "X-Content-Type-Options" in reponse.headers
    assert "X-Frame-Options" in reponse.headers
    assert "Content-Security-Policy" in reponse.headers
    assert "Strict-Transport-Security" in reponse.headers


def test_headers_securite_valeurs(client):
    reponse = client.get("/monstres")
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("route", ["/", "/actions", "/monstres", "/monstres/inconnu"])
def test_no_store_sur_les_routes_non_statiques(client, route):
    reponse = client.get(route)
    assert "no-store" in reponse.headers.get("Cache-Control", "")


def test_no_store_sur_le_login(client):
    reponse = client.post("/login", json={"username": "admin", "password": "password"})
    assert reponse.status_code == 200
    assert "no-store" in reponse.headers.get("Cache-Control", "")


def test_fichiers_statiques_en_cache(client):
    reponse = client.get("/static/style.css")
    assert reponse.status_code == 200
    assert reponse.headers["Cache-Control"] == "public, max-age=3600"


def test_read_secret_lit_la_variable_env_si_aucun_fichier(monkeypatch):
    monkeypatch.setenv("MA_VAR_TEST", "valeur-env")
    resultat = read_secret("MA_VAR_TEST", "/chemin/qui/nexiste/pas")
    assert resultat == "valeur-env"


def test_read_secret_priorise_le_fichier_sur_la_variable_env(tmp_path, monkeypatch):
    fichier = tmp_path / "mon-secret"
    fichier.write_text("valeur-du-fichier\n")
    monkeypatch.setenv("MA_VAR_TEST", "valeur-env")
    resultat = read_secret("MA_VAR_TEST", str(fichier))
    assert resultat == "valeur-du-fichier"


def test_read_secret_nettoie_espaces_et_retours_ligne(tmp_path):
    fichier = tmp_path / "mon-secret"
    fichier.write_text("  Xk9$mQ2!vL8pR4#nW7zT3@  \n\n")
    resultat = read_secret("MA_VAR_INEXISTANTE", str(fichier))
    assert resultat == "Xk9$mQ2!vL8pR4#nW7zT3@"


def test_read_secret_refuse_sans_secret(monkeypatch):
    monkeypatch.delenv("MA_VAR_INEXISTANTE", raising=False)
    with pytest.raises(RuntimeError):
        read_secret("MA_VAR_INEXISTANTE", "/chemin/qui/nexiste/pas")


def test_read_secret_refuse_un_fichier_vide(tmp_path, monkeypatch):
    monkeypatch.delenv("MA_VAR_INEXISTANTE", raising=False)
    fichier = tmp_path / "secret-vide"
    fichier.write_text("")
    with pytest.raises(RuntimeError):
        read_secret("MA_VAR_INEXISTANTE", str(fichier))


def test_read_secret_fonctionne_sans_chemin_de_fichier(monkeypatch):
    monkeypatch.setenv("MA_VAR_TEST", "valeur-env")
    resultat = read_secret("MA_VAR_TEST", None)
    assert resultat == "valeur-env"


def test_echec_login_incremente_le_compteur(client):
    avant = REGISTRY.get_sample_value("rpg_api_login_echecs_total")
    client.post("/login", json={"username": "admin", "password": "mauvais"})
    apres = REGISTRY.get_sample_value("rpg_api_login_echecs_total")
    assert apres == avant + 1


def test_pas_de_route_metrics_publique(client):
    assert client.get("/metrics").status_code == 404



def test_login_bloque_apres_5_tentatives(client):
    for _ in range(5):
        client.post("/login", json={"username": "admin", "password": "mauvais"})
    reponse = client.post("/login", json={"username": "admin", "password": "mauvais"})
    assert reponse.status_code == 429


def test_true_client_ip_ignore_par_defaut(client):
    for i in range(5):
        client.post("/login", json={"username": "admin", "password": "mauvais"},
                    headers={"True-Client-IP": f"203.0.113.{i}"})
    reponse = client.post("/login", json={"username": "admin", "password": "mauvais"},
                          headers={"True-Client-IP": "203.0.113.99"})
    assert reponse.status_code == 429


def test_true_client_ip_utilise_si_active(client, monkeypatch):
    monkeypatch.setattr(app_module, "FAIRE_CONFIANCE_TRUE_CLIENT_IP", True)
    for _ in range(5):
        client.post("/login", json={"username": "admin", "password": "mauvais"},
                    headers={"True-Client-IP": "203.0.113.1"})
    reponse = client.post("/login", json={"username": "admin", "password": "mauvais"},
                          headers={"True-Client-IP": "203.0.113.2"})
    assert reponse.status_code == 401
