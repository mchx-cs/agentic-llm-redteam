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

# On construit le client une seule fois, à partir du profil actif.
_cfg = PROFILS[PROFIL_ACTIF]
_client = OpenAI(base_url=_cfg["base_url"], api_key=_cfg["api_key"])


def demander_au_llm(message, systeme=None, modele=None, temperature=None,
                    format_json=False):
    """
    Envoie un message à un LLM et renvoie sa réponse (du texte).

    - message     : le texte qu'on envoie (ce que dit l'utilisateur).
    - systeme     : instructions de cadrage optionnelles (le "rôle" du LLM).
    - modele      : pour forcer un modèle précis ; sinon celui du profil actif.
    - temperature : 0 = réponses quasi déterministes. Indispensable pour un
                    juge : un verdict qui change d'un lancement à l'autre ne
                    se mesure pas. None = valeur par défaut du fournisseur.
    - format_json : force le modèle à produire du JSON valide. Plus fiable que
                    de deviner OUI/NON dans une phrase libre.
    """
    modele = modele or _cfg["modele"]

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
        # Format OpenAI, compris aussi par Ollama.
        options["response_format"] = {"type": "json_object"}

    reponse = _client.chat.completions.create(
        model=modele,
        messages=messages,
        **options,
    )
    return reponse.choices[0].message.content
