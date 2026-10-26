import urllib.request
import json
import os

API_URL = os.environ.get("RPG_API_URL", "https://rpg-pipeline.onrender.com") + "/monstres"
CSV_PATH = os.path.join(os.path.dirname(__file__), "rpg-source", "monsters.csv")

print("Connexion a l'API en ligne...")

try:
    with urllib.request.urlopen(API_URL, timeout=10) as reponse:  # nosec B310 - API_URL est une constante codee en dur, pas une entree utilisateur  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        monstres_api = json.loads(reponse.read().decode())
    if not isinstance(monstres_api, list) or len(monstres_api) == 0:
        raise ValueError("l'API a renvoye une liste vide ou invalide")

    monstres_locaux = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne:
                    champs = ligne.split(";")
                    if len(champs) >= 6:
                        monstres_locaux.append(champs[1])

    noms_api = [m["nom"] for m in monstres_api]
    ajoutes = [m for m in monstres_api if m["nom"] not in monstres_locaux]
    supprimes = [nom for nom in monstres_locaux if nom not in noms_api]

    if not ajoutes and not supprimes:
        print("Aucun changement detecte - le CSV est deja a jour")
    else:
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            for m in monstres_api:
                actions = f"{m.get('act1', '-')};{m.get('act2', '-')};{m.get('act3', '-')};{m.get('act4', '-')}"
                f.write(f"{m['categorie']};{m['nom']};{m['hp']};{m['atk']};{m['def']};{m['mercy']};{actions}\n")

        if ajoutes:
            print(f"{len(ajoutes)} monstre(s) ajoute(s) : {', '.join([m['nom'] for m in ajoutes])}")
        if supprimes:
            print(f"{len(supprimes)} monstre(s) supprime(s) : {', '.join(supprimes)}")
        print("Le fichier monsters.csv a ete mis a jour")

except Exception as e:
    print(f"Impossible de contacter l'API : {e}")
    print("On joue avec les donnees locales")
