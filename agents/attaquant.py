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
import re
from datetime import datetime
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


# --- Instantané garak ---------------------------------------------------------
# Produit par `payloads/exporter_garak.py`, lancé dans un venv séparé. Absent
# du dépôt (voir .gitignore) : les sondes de garak incorporent des jeux de
# données tiers, qu'on ne republie pas depuis un dépôt personnel. Qui veut
# ces payloads resynchronise.

FICHIER_GARAK = FICHIER_BIBLIOTHEQUE.parent / "garak.json"

# Les tags de garak portent déjà la correspondance OWASP ; on la traduit dans
# le vocabulaire du projet, et on en déduit le prérequis de la famille.
FAMILLES_GARAK = {
    "owasp:llm01": ("LLM01:2025 Prompt Injection", []),
    "owasp:llm02": ("LLM02:2025 Sensitive Information Disclosure", ["secret"]),
    "owasp:llm07": ("LLM07:2025 System Prompt Leakage", ["consignes"]),
}


# garak remplit ses propres emplacements à l'exécution. Les laisser tels
# quels affaiblirait le payload : la cible verrait « {generator.name} » au
# lieu d'un nom d'assistant, et bien des jailbreaks reposent sur ce nom.
# Un remplacement neutre est préférable à un emplacement visible.
EMPLACEMENTS_GARAK = {"{generator.name}": "the assistant"}


def _remplir(payload):
    for marqueur, valeur in EMPLACEMENTS_GARAK.items():
        payload = payload.replace(marqueur, valeur)
    return payload


# garak publie environ tous les 37 jours (médiane mesurée le 2026-11-10 sur
# ses douze dernières versions). Au-delà de deux mois, un instantané a donc
# probablement manqué une version ou deux : on le signale, sans rien bloquer.
AGE_INSTANTANE_SUSPECT = 60


def _age_en_jours(horodatage):
    """Âge de l'instantané, ou None s'il est illisible."""
    try:
        return (datetime.now() - datetime.fromisoformat(horodatage)).days
    except (TypeError, ValueError):
        return None


def _technique_depuis_sonde(sonde):
    """Traduit une sonde garak en technique du projet."""
    famille, prerequis = next(
        (FAMILLES_GARAK[t] for t in sonde["familles_owasp"]
         if t in FAMILLES_GARAK), (None, []))
    identifiant = "garak-" + re.sub(
        r"[^a-z0-9]+", "-", sonde["sonde"].replace("probes.", "").lower()
    ).strip("-")
    return {
        "id": identifiant,
        "famille_owasp": famille,
        "description": sonde["objectif"] or sonde["sonde"],
        "prerequis": prerequis,
        # Les prompts de garak sont COMPLETS : ils ne comportent pas
        # d'emplacement `{objectif}`, et n'ont donc rien à faire dans
        # `modeles`, que le validateur contrôle sur ce point.
        "modeles": [],
        "payloads_complets": [_remplir(p) for p in sonde["payloads"]],
        "source": f"garak {sonde['sonde']}",
    }


# --- Construction des payloads -----------------------------------------------

def charger_bibliotheque(avec_garak=True):
    """
    Charge la bibliothèque, enrichie de l'instantané garak s'il est présent.

    L'instantané est optionnel par construction : sans lui, le dépôt tourne
    exactement comme avant. C'est le modèle de nuclei — l'outil reste léger,
    les payloads se synchronisent à part.
    """
    with open(FICHIER_BIBLIOTHEQUE, encoding="utf-8") as f:
        bibliotheque = json.load(f)

    if avec_garak and FICHIER_GARAK.exists():
        with open(FICHIER_GARAK, encoding="utf-8") as f:
            instantane = json.load(f)
        bibliotheque["techniques"] = bibliotheque["techniques"] + [
            _technique_depuis_sonde(s) for s in instantane["sondes"]]
        bibliotheque["_garak"] = {
            "version": instantane.get("version_garak"),
            "exporte_le": instantane.get("exporte_le"),
            "sondes": len(instantane["sondes"]),
            "age_jours": _age_en_jours(instantane.get("exporte_le")),
        }

    return bibliotheque


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

        # Les payloads venus de l'extérieur sont des prompts COMPLETS : ils
        # portent déjà leur propre intention, et ne se croisent donc pas avec
        # l'axe des objectifs. D'où `objectif: None`.
        for numero, payload in enumerate(
                technique.get("payloads_complets", []), start=1):
            for nom_transfo in TRANSFORMATIONS:
                payloads.append({
                    "technique": technique["id"],
                    "famille_owasp": technique["famille_owasp"],
                    "objectif": None,
                    "transformation": nom_transfo,
                    "texte": TRANSFORMATIONS[nom_transfo](payload),
                    "source": technique.get("source"),
                    "numero_payload": numero,
                })

    return payloads
