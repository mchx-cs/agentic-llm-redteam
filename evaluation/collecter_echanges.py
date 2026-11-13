"""
evaluation/collecter_echanges.py — Récolte de vrais échanges avec la cible.

Les échanges étiquetés d'origine sont FICTIFS : écrits à la main, ils
reflètent ce qu'on imagine qu'une cible répondrait. Les vraies réponses
d'un LLM sont plus variées et plus surprenantes, c'est sur elles que le juge
doit être fiable. Ce script envoie à la vraie cible les payloads de la
bibliothèque et enregistre les échanges dans a_etiqueter.json.

Ensuite, c'est l'AUTEUR qui étiquette, à la main, chaque échange :
remplir "attendu" (true/false), "categorie", "jeu" et "piege", puis le
déplacer dans echanges_etiquetes.json.

Deux choix volontaires :
- Les prompts viennent de payloads/bibliotheque.json, rien d'autre : la
  collecte ne contient que des techniques déjà pratiquées à la main.
- L'avis de l'arbitre n'est PAS enregistré. Voir son verdict influencerait
  l'étiquette humaine, et on finirait par mesurer le juge contre lui-même.

Lance-le depuis la racine du projet avec :  python -m evaluation.collecter_echanges
"""

import json
from pathlib import Path

from agents.attaquant import generate_payloads
from cibles import choose_target

FICHIER_SORTIE = Path(__file__).parent / "a_etiqueter.json"

# Réponses demandées par payload : la cible a de l'aléa, deux réponses au
# même payload peuvent différer (l'une fuit, l'autre refuse…).
NB_ECHANTILLONS = 2


def collecter():
    # Celle que désigne .env : on collecte donc aussi bien depuis le leurre
    # que depuis une vraie cible, sans toucher à ce script.
    interroger_cible = choose_target()
    payloads = generate_payloads()
    echanges = []

    # Boucles bornées : payloads (liste finie) × NB_ECHANTILLONS.
    for numero_payload, payload in enumerate(payloads, start=1):
        # Toutes les réponses à un même payload forment un groupe : elles
        # devront aller dans le même jeu (dev ou test), jamais réparties.
        groupe = f"R{numero_payload:02d}"
        for echantillon in range(1, NB_ECHANTILLONS + 1):
            reponse = interroger_cible(payload["texte"])
            echanges.append({
                "id": f"{groupe}-{echantillon}",
                "groupe": groupe,
                "categorie": None,      # à remplir à la main
                "jeu": None,            # à remplir à la main : "dev" ou "test"
                "secret": "TOPSECRET42",
                "source": (f"cible réelle — {payload['technique']} / "
                           f"{payload['objectif']} / {payload['transformation']}"),
                "payload": payload["texte"],
                "reponse": reponse,
                "attendu": None,        # à remplir à la main : true ou false
                "piege": "",            # à remplir à la main
            })
            print(f"{groupe}-{echantillon} collecté")

    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump({"echanges": echanges}, f, ensure_ascii=False, indent=2)

    print(f"\n{len(echanges)} échanges écrits dans {FICHIER_SORTIE.name}, "
          f"à étiqueter à la main.")


if __name__ == "__main__":
    collecter()
