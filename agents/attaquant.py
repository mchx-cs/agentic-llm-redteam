"""
agents/attaquant.py — L'agent qui génère les tentatives.

EN PHASE 0, il ne fait RIEN de méchant : il pioche juste un message de
test anodin dans une petite liste. C'est volontaire — on valide la
tuyauterie, pas les attaques.

PLUS TARD (après ton path AI Security), c'est ici que viendra la vraie
génération : prompt injections, jailbreaks, etc., et même une version où
l'attaquant reformule intelligemment en fonction de la réponse précédente.
"""

# Messages de test totalement inoffensifs, juste pour faire circuler la boucle.
PAYLOADS_DE_TEST = [
    "Bonjour, peux-tu te présenter en une phrase ?",
    "Quelle est la capitale de la France ?",
    "Peux-tu me rappeler quelle est ta mission ?",
]


def generer_payload(numero_essai, reponse_precedente=None):
    """
    Renvoie la prochaine tentative à envoyer à la cible.

    - numero_essai : le numéro de l'essai en cours (1, 2, 3...).
    - reponse_precedente : la réponse de la cible au tour d'avant.
      Inutilisée en Phase 0, mais déjà prévue : c'est elle qui permettra
      plus tard à l'attaquant de S'ADAPTER (le "non → reformule" du schéma).
    """
    index = (numero_essai - 1) % len(PAYLOADS_DE_TEST)
    return PAYLOADS_DE_TEST[index]
