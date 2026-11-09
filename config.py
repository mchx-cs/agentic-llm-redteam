"""
config.py — Le point de bascule unique du projet.

C'est ICI, et nulle part ailleurs, qu'on décide si les LLM tournent
en local (Ollama) ou via une API distante (OpenAI, Groq…).
Changer de l'un à l'autre = changer une ligne PROFIL_* ci-dessous.
Le reste du code ne sait même pas à qui il parle : c'est tout l'intérêt.
"""

import os
from pathlib import Path


def _charger_fichier_env():
    """
    Lit le fichier .env à la racine du projet, s'il existe, et place ses
    variables dans l'environnement.

    Pourquoi un fichier .env : la clé d'API va directement de la console du
    fournisseur à ce fichier, sans transiter par un terminal, un chat ou le
    code. Il est listé dans .gitignore : il ne part jamais sur GitHub.

    Une variable déjà définie dans l'environnement est prioritaire : le
    fichier ne sert que de valeur par défaut.
    """
    fichier = Path(__file__).parent / ".env"
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        nom, valeur = ligne.split("=", 1)
        os.environ.setdefault(nom.strip(), valeur.strip().strip("\"'"))


# À faire AVANT de construire les profils, qui lisent l'environnement.
_charger_fichier_env()

PROFILS = {
    # --- Profil LOCAL : Ollama, gratuit, aucune clé ---
    # Ollama expose une API au format OpenAI sur le port 11434.
    "local": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",          # ignorée par Ollama, mais le SDK l'exige
        "modele": "llama3.2",         # fais d'abord : ollama pull llama3.2
    },

    # --- Profil API : un fournisseur distant (exemple OpenAI) ---
    # La clé est lue depuis une variable d'environnement (jamais en dur).
    "api": {
        "base_url": "https://api.openai.com/v1",
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        # Le modèle est lu, comme la clé, depuis l'environnement : pas de nom
        # figé dans le code, qui deviendrait obsolète au fil des sorties.
        "modele": os.environ.get("OPENAI_MODEL", ""),
        # Comme pour groq : les API distantes plafonnent le débit, le SDK
        # attend le délai annoncé puis relance, au plus ce nombre de fois.
        "relances": 8,
    },

    # --- Profil GROQ : API distante avec offre gratuite ---
    # Utilisé pour l'ARBITRE uniquement, et seulement sur des données
    # fictives. Jamais comme cible d'attaques réelles : les conditions
    # d'utilisation des fournisseurs interdisent de contourner leurs
    # garde-fous (voir "Cadre légal" dans CLAUDE.md).
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        # Modèle d'une autre famille que la cible (llama3.2) : un juge qui
        # n'est pas le même modèle ne partage pas ses angles morts (Phase 4).
        # Remplaçable par la variable GROQ_MODEL, sans toucher au code.
        "modele": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        # L'offre gratuite plafonne les tokens par minute : au-delà, l'API
        # répond "réessayez dans X ms". Le SDK attend ce délai puis relance,
        # au plus ce nombre de fois (boucle bornée, jamais infinie).
        "relances": 8,
    },
}

# >>> LES DEUX LEVIERS DE BASCULE <<<
# Tous deux se règlent dans .env (hors git) : personne n'a besoin de modifier
# un fichier suivi par git pour changer de fournisseur. "local" par défaut,
# pour que le dépôt tourne sans aucune clé.

# Profil par défaut : celui de la CIBLE et de tout appel qui n'en précise pas.
# Attention : attaquer une API distante violerait les conditions d'utilisation
# du fournisseur (voir "Cadre légal" dans CLAUDE.md). La cible reste locale.
PROFIL_ACTIF = os.environ.get("PROFIL_ACTIF", "local")

# Profil de l'ARBITRE (et de l'analyste de reconnaissance), séparé pour que le
# juge puisse tourner sur un autre modèle que la cible qu'il juge — un juge
# identique à sa cible partage ses angles morts.
PROFIL_ARBITRE = os.environ.get("PROFIL_ARBITRE", "local")

_profils_inconnus = [nom for nom in (PROFIL_ACTIF, PROFIL_ARBITRE)
                     if nom not in PROFILS]
if _profils_inconnus:
    # Une faute de frappe dans .env donnerait sinon un KeyError nu, très loin
    # d'ici, au premier appel au LLM.
    raise ValueError(
        f"Profil inconnu dans .env : {', '.join(_profils_inconnus)}. "
        f"Profils disponibles : {', '.join(PROFILS)}."
    )
