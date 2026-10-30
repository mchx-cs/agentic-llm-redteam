"""
agents/attaquant.py — L'agent qui génère les tentatives.

Un payload n'est pas une chaîne figée qu'on recopie d'une cible à l'autre :
il dépend du contexte, et les versions publiques sont vite patchées. On le
construit donc à partir de trois axes indépendants :

    payload = technique  (la famille d'attaque, stable dans le temps)
            × objectif   (ce qu'on veut obtenir de CETTE cible)
            × transformation (encodage, reformulation… pour passer les filtres)

Les techniques et objectifs vivent dans payloads/bibliotheque.json (des
données, pas du code). Les transformations sont des fonctions Python, ici.

ÉTAT ACTUEL : seule la technique "controle" (anodine) a des modèles. Les
familles OWASP sont déclarées mais vides : elles seront remplies au fil du
path AI Security, une fois chaque technique pratiquée à la main.
"""

import json
from itertools import product
from pathlib import Path

FICHIER_BIBLIOTHEQUE = Path(__file__).parent.parent / "payloads" / "bibliotheque.json"


# --- Transformations ---------------------------------------------------------
# Chacune prend un texte et renvoie un texte. C'est l'équivalent des
# "converters" de PyRIT. Pour l'instant, rien qui serve à contourner un
# filtre : "majuscules" n'existe que pour montrer que l'axe fonctionne.
# Les vraies (Base64, autre langue, leetspeak…) viendront avec le path.

def identite(texte):
    return texte


def majuscules(texte):
    return texte.upper()


TRANSFORMATIONS = {
    "identite": identite,
    "majuscules": majuscules,
}


# --- Construction des payloads -----------------------------------------------

def charger_bibliotheque():
    with open(FICHIER_BIBLIOTHEQUE, encoding="utf-8") as f:
        return json.load(f)


def generer_payloads():
    """
    Renvoie la liste de tous les payloads possibles : chaque modèle de chaque
    technique, croisé avec chaque objectif et chaque transformation.

    La liste est finie par construction (produit de listes finies), mais elle
    grossit vite : c'est MAX_ESSAIS, dans main.py, qui borne la campagne.
    """
    bibliotheque = charger_bibliotheque()
    payloads = []

    for technique in bibliotheque["techniques"]:
        # Une technique sans modèle est déclarée mais pas encore prête.
        for modele, objectif, nom_transfo in product(
            technique["modeles"], bibliotheque["objectifs"], TRANSFORMATIONS
        ):
            texte = modele.format(objectif=objectif["formulation"])
            payloads.append({
                "technique": technique["id"],
                "famille_owasp": technique["famille_owasp"],
                "objectif": objectif["id"],
                "transformation": nom_transfo,
                "texte": TRANSFORMATIONS[nom_transfo](texte),
            })

    return payloads


# Calculée une seule fois au chargement du module : inutile de relire le
# fichier à chaque essai.
_PAYLOADS = generer_payloads()


def generer_payload(numero_essai, reponse_precedente=None):
    """
    Renvoie la prochaine tentative à envoyer à la cible : un dictionnaire
    avec le texte ET d'où il vient (technique, objectif, transformation),
    pour que le rapport puisse dire QUELLE combinaison a fonctionné.

    - numero_essai : le numéro de l'essai en cours (1, 2, 3...).
    - reponse_precedente : la réponse de la cible au tour d'avant.
      Toujours inutilisée : l'adaptation multi-tours est l'objet de la
      Phase 3 (évaluation de PyRIT).
    """
    index = (numero_essai - 1) % len(_PAYLOADS)
    return _PAYLOADS[index]
