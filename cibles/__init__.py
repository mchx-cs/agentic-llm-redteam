"""
cibles/ — Les systèmes testés, et le choix entre eux.

Jusqu'ici la cible était codée en dur : l'outil ne pouvait tester que
lui-même. Chaque cible est maintenant un ADAPTATEUR, et tous respectent le
même contrat, délibérément minimal :

    interroger(message: str) -> str

C'est ce contrat qui permet à `reconnaissance.py` et `verificateur.py` de
recevoir la cible en paramètre, et aux tests d'utiliser des cibles simulées
en quelques lignes.

Trois adaptateurs :
- `leurre` : le chatbot-jouet local, avec un secret factice à protéger.
  C'est la cible par défaut, pour que le dépôt tourne sans configuration.
- `mock`   : déterministe, sans aucun LLM. Instantanée, gratuite, toujours
  identique : c'est elle qui rend possibles des tests de bout en bout.
- `http`   : un vrai endpoint, décrit dans `.env`. C'est l'adaptateur qui
  fait passer l'outil de « il se teste lui-même » à « il vise une cible ».

Un mot sur la règle « aucun appel direct à un fournisseur de LLM » : elle
vise les modèles QUE NOUS utilisons (arbitre, analyste, leurre), pour qu'ils
restent interchangeables depuis `config.py`. La cible, elle, est un système
tiers arbitraire — souvent une application, pas un modèle nu — et
l'adaptateur `http` l'appelle donc directement. C'est volontaire.
"""

from cibles.http import construire_cible_http
from cibles.leurre import interroger_leurre
from cibles.mock import interroger_mock

# Les cibles sans configuration : on les choisit par leur nom.
CIBLES_NOMMEES = {
    "leurre": interroger_leurre,
    "mock": interroger_mock,
}


def choisir_cible(nom=None):
    """
    Renvoie la fonction d'interrogation correspondant à `nom`.

    - un nom connu ("leurre", "mock") ;
    - une URL (http:// ou https://) → adaptateur HTTP configuré par .env ;
    - None → la valeur de CIBLE dans .env, sinon le leurre local.
    """
    from config import CIBLE  # importé ici pour éviter un import circulaire

    nom = nom or CIBLE

    if nom in CIBLES_NOMMEES:
        return CIBLES_NOMMEES[nom]

    if nom.startswith(("http://", "https://")):
        return construire_cible_http(nom)

    raise ValueError(
        f"Cible inconnue : '{nom}'. Attendu : "
        f"{', '.join(CIBLES_NOMMEES)}, ou une URL http(s)."
    )
