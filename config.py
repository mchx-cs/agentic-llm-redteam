"""
config.py — Le point de bascule unique du projet.

C'est ICI, et nulle part ailleurs, qu'on décide si les LLM tournent
en local (Ollama) ou via une API distante (OpenAI, etc.).
Changer de l'un à l'autre = changer la seule ligne PROFIL_ACTIF ci-dessous.
Le reste du code ne sait même pas à qui il parle : c'est tout l'intérêt.
"""

import os

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
    },
}

# >>> LA SEULE LIGNE À CHANGER POUR BASCULER <<<
PROFIL_ACTIF = "local"
