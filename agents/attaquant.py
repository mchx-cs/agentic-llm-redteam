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

Ce module FOURNIT les briques ; c'est planificateur.py qui CHOISIT, selon la
fiche de la cible, lesquelles assembler et dans quel ordre. `generer_payloads()`
ne sert donc plus qu'à produire le catalogue complet, sans tenir compte du
contexte (utile pour collecter des échanges à étiqueter).

ÉTAT ACTUEL : seule la technique "controle" (anodine) a des modèles. Les
familles OWASP sont déclarées mais vides : une technique sans modèle est
écartée par le planificateur, qui le signale dans son plan.
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
