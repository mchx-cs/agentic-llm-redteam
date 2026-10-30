"""
llm_client.py — LA couche d'abstraction.

Tout le projet parle aux LLM UNIQUEMENT à travers la fonction
`demander_au_llm()` d'ici. Aucun agent n'appelle Ollama ou une API
directement. Résultat : le jour où tu changes de fournisseur, tu ne
touches qu'à config.py, et ce fichier — rien d'autre ne bouge.

C'est le garde-fou anti-"code en dur partout" dont on avait parlé.
"""

from openai import OpenAI
from config import PROFILS, PROFIL_ACTIF

# Un client par profil, construit au premier usage puis réutilisé. Plusieurs
# profils peuvent servir dans une même campagne : la cible en local, le juge
# sur une API distante, par exemple.
_clients = {}


def _client_pour(profil):
    if profil not in _clients:
        cfg = PROFILS[profil]
        if not cfg["api_key"]:
            # Échouer tôt, avec un message clair, plutôt que de laisser
            # l'API renvoyer une erreur d'authentification obscure.
            raise RuntimeError(
                f"Profil '{profil}' : clé d'API absente. Définis-la dans le "
                f"fichier .env à la racine du projet (voir config.py)."
            )
        _clients[profil] = OpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            # Relances automatiques en cas de limite de débit (erreur 429) :
            # 2 par défaut dans le SDK, plus pour les offres gratuites.
            max_retries=cfg.get("relances", 2),
        )
    return _clients[profil]


def demander_au_llm(message, systeme=None, modele=None, temperature=None,
                    format_json=False, profil=None):
    """
    Envoie un message à un LLM et renvoie sa réponse (du texte).

    - message     : le texte qu'on envoie (ce que dit l'utilisateur).
    - systeme     : instructions de cadrage optionnelles (le "rôle" du LLM).
    - modele      : pour forcer un modèle précis ; sinon celui du profil.
    - temperature : 0 = réponses quasi déterministes. Indispensable pour un
                    juge : un verdict qui change d'un lancement à l'autre ne
                    se mesure pas. None = valeur par défaut du fournisseur.
    - format_json : force le modèle à produire du JSON valide. Plus fiable que
                    de deviner OUI/NON dans une phrase libre.
    - profil      : le profil de config.py à utiliser ; sinon PROFIL_ACTIF.
    """
    profil = profil or PROFIL_ACTIF
    modele = modele or PROFILS[profil]["modele"]

    messages = []
    if systeme:
        messages.append({"role": "system", "content": systeme})
    messages.append({"role": "user", "content": message})

    # On n'envoie que les options demandées, pour laisser au fournisseur
    # ses valeurs par défaut dans le cas général.
    options = {}
    if temperature is not None:
        options["temperature"] = temperature
    if format_json:
        # Format OpenAI, compris aussi par Ollama et Groq.
        options["response_format"] = {"type": "json_object"}

    reponse = _client_pour(profil).chat.completions.create(
        model=modele,
        messages=messages,
        **options,
    )
    return reponse.choices[0].message.content
