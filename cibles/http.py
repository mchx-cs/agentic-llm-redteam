"""
cibles/http.py — Viser un vrai endpoint.

C'est l'adaptateur qui fait passer l'outil de « il se teste lui-même » à
« il vise une cible réelle ». Il parle à n'importe quelle application qui
accepte du JSON et renvoie du JSON, sans rien coder en dur : la forme de la
requête et l'endroit où lire la réponse se décrivent dans `.env`.

Pourquoi `urllib` et pas `requests` : le projet tient à sa dépendance
unique (`openai`). Un POST JSON en bibliothèque standard coûte une vingtaine
de lignes de plus, et évite une installation à qui clone le dépôt.

Rappel du cadre légal (voir CLAUDE.md) : pointer cet adaptateur vers un
système tiers sans autorisation écrite est un délit. La phase 9 rendra ce
contrôle explicite dans le code ; pour l'instant, c'est à l'opérateur.
"""

import json
import urllib.error
import urllib.request

# Jeton remplacé par le payload dans le corps de la requête.
MARQUEUR_MESSAGE = "{message}"


def _extraire(donnees, chemin):
    """
    Suit un chemin pointé dans une réponse JSON.

    "reply" → donnees["reply"]
    "choices.0.message.content" → donnees["choices"][0]["message"]["content"]

    Les API de chatbot imbriquent toutes leur texte différemment : plutôt que
    de deviner, on laisse l'opérateur décrire le chemin.
    """
    courant = donnees
    for morceau in chemin.split("."):
        if isinstance(courant, list):
            if not morceau.isdigit():
                raise ValueError(
                    f"Chemin '{chemin}' : '{morceau}' n'est pas un indice, "
                    f"alors que la réponse contient une liste à cet endroit."
                )
            courant = courant[int(morceau)]
        elif isinstance(courant, dict):
            if morceau not in courant:
                raise ValueError(
                    f"Chemin '{chemin}' : clé '{morceau}' absente. "
                    f"Clés disponibles : {', '.join(courant) or 'aucune'}."
                )
            courant = courant[morceau]
        else:
            raise ValueError(
                f"Chemin '{chemin}' : impossible de descendre dans "
                f"'{morceau}', la valeur est un {type(courant).__name__}."
            )
    return courant


def _injecter(gabarit, message):
    """
    Place le message dans le gabarit de corps, à la place du marqueur.

    On travaille sur la structure déjà désérialisée, pas sur du texte : ainsi
    un payload contenant des guillemets ou des retours à la ligne ne casse
    pas le JSON, et ne peut pas non plus en injecter.
    """
    if isinstance(gabarit, dict):
        return {cle: _injecter(valeur, message) for cle, valeur in gabarit.items()}
    if isinstance(gabarit, list):
        return [_injecter(valeur, message) for valeur in gabarit]
    if gabarit == MARQUEUR_MESSAGE:
        return message
    return gabarit


def construire_cible_http(url, entetes=None, corps=None, chemin_reponse=None,
                          delai=None):
    """
    Renvoie une fonction `interroger(message) -> str` qui vise `url`.

    Les paramètres non fournis sont lus dans `.env` (voir config.py) :
    - entetes        : en-têtes HTTP, dont l'authentification ;
    - corps          : gabarit JSON du corps, où "{message}" sera remplacé ;
    - chemin_reponse : où lire le texte dans la réponse JSON ;
    - delai          : secondes avant abandon.
    """
    from config import CIBLE_HTTP

    entetes = {**CIBLE_HTTP["entetes"], **(entetes or {})}
    corps = corps if corps is not None else CIBLE_HTTP["corps"]
    chemin_reponse = chemin_reponse or CIBLE_HTTP["chemin_reponse"]
    delai = delai or CIBLE_HTTP["delai"]

    def interroger(message):
        donnees = json.dumps(_injecter(corps, message)).encode("utf-8")
        requete = urllib.request.Request(
            url, data=donnees, method="POST",
            headers={"Content-Type": "application/json", **entetes},
        )

        try:
            with urllib.request.urlopen(requete, timeout=delai) as reponse:
                brut = reponse.read().decode("utf-8")
        except urllib.error.HTTPError as erreur:
            # Le corps d'une erreur HTTP contient souvent l'explication utile
            # (clé refusée, format invalide, quota) : on la remonte.
            detail = erreur.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(
                f"Cible {url} : erreur HTTP {erreur.code}.\n  {detail}"
            ) from erreur
        except urllib.error.URLError as erreur:
            raise RuntimeError(
                f"Cible {url} : injoignable ({erreur.reason}).\n"
                f"  Vérifie l'URL, le réseau, et que la cible est démarrée."
            ) from erreur

        try:
            texte = _extraire(json.loads(brut), chemin_reponse)
        except json.JSONDecodeError as erreur:
            raise RuntimeError(
                f"Cible {url} : réponse illisible (JSON attendu).\n"
                f"  Reçu : {brut[:200]}"
            ) from erreur
        except ValueError as erreur:
            # Chemin de réponse mal décrit : l'erreur dit déjà quoi corriger.
            raise RuntimeError(f"Cible {url} : {erreur}") from erreur

        if not isinstance(texte, str):
            raise RuntimeError(
                f"Cible {url} : '{chemin_reponse}' donne un "
                f"{type(texte).__name__}, pas du texte."
            )
        return texte

    return interroger
