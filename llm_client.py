"""
llm_client.py — LA couche d'abstraction.

Tout le projet parle aux LLM UNIQUEMENT à travers la fonction
`demander_au_llm()` d'ici. Aucun agent n'appelle Ollama ou une API
directement. Résultat : le jour où tu changes de fournisseur, tu ne
touches qu'à config.py, et ce fichier — rien d'autre ne bouge.

C'est le garde-fou anti-"code en dur partout" dont on avait parlé.
"""

from openai import (APIConnectionError, AuthenticationError, NotFoundError,
                    OpenAI, RateLimitError)
from config import PROFILS, PROFIL_ACTIF

# Les profils locaux : ceux dont le serveur tourne sur la machine. Le conseil
# à donner diffère (« lance Ollama » plutôt que « vérifie ta connexion »).
_HOTES_LOCAUX = ("localhost", "127.0.0.1")

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

    try:
        reponse = _client_pour(profil).chat.completions.create(
            model=modele,
            messages=messages,
            **options,
        )
    except (APIConnectionError, NotFoundError, AuthenticationError,
            RateLimitError) as erreur:
        # Les trois pannes de configuration les plus courantes. Le SDK les
        # signale par "Connection error." ou un code HTTP : on les traduit en
        # une consigne exploitable, en nommant le profil et le modèle fautifs.
        raise RuntimeError(_message_d_erreur(profil, modele, erreur)) from erreur

    return reponse.choices[0].message.content


def _message_d_erreur(profil, modele, erreur):
    """Transforme une erreur du SDK en consigne claire pour l'utilisateur."""
    cfg = PROFILS[profil]
    url = cfg["base_url"]
    entete = f"Profil '{profil}' (modèle '{modele}', {url}) :"
    local = any(hote in url for hote in _HOTES_LOCAUX)

    if isinstance(erreur, APIConnectionError):
        if local:
            return (f"{entete} le serveur ne répond pas.\n"
                    f"  Ollama est-il lancé ? Vérifie avec : ollama list\n"
                    f"  S'il est éteint, lance : ollama serve")
        return (f"{entete} impossible de joindre le serveur.\n"
                f"  Vérifie ta connexion et l'adresse 'base_url' dans config.py.")

    if isinstance(erreur, RateLimitError):
        # Le SDK relance tout seul sur les limites par minute (voir "relances"
        # dans config.py). S'il abandonne, c'est que le quota JOURNALIER est
        # atteint : relancer n'y changera rien, il faut attendre ou basculer.
        return (f"{entete} quota du fournisseur atteint.\n"
                f"  Attends la fenêtre indiquée, ou repasse l'arbitre en local\n"
                f"  (PROFIL_ARBITRE=local dans .env).\n"
                f"  Détail du fournisseur : {erreur}")

    if isinstance(erreur, NotFoundError):
        if local:
            return (f"{entete} ce modèle n'est pas installé.\n"
                    f"  Télécharge-le avec : ollama pull {modele}")
        return (f"{entete} ce modèle est inconnu du fournisseur.\n"
                f"  Vérifie son nom exact (variable d'environnement du profil).")

    return (f"{entete} clé d'API refusée.\n"
            f"  Vérifie la clé dans le fichier .env à la racine du projet.")
