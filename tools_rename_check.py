# -*- coding: utf-8 -*-
"""
Détecte les dégâts d'une passe de renommage : un identifiant ANGLAIS tombé
dans une phrase FRANÇAISE.

C'est le pire des dangers listés au glossaire, parce que la suite de tests
reste VERTE : renommer `prochain` en `next_attempt` avait réécrit douze
phrases françaises, dont une réponse de cible épinglée VERBATIM dans un test.
Un test dont la donnée est falsifiée ne teste plus ce qu'il prétend.

Usage : python -I degats_renommage.py <identifiant> [<identifiant> ...]
"""
import pathlib
import re
import subprocess
import sys

ACCENTS = re.compile(r"[éèêëàâçùûîïôœ]", re.IGNORECASE)

mots = sys.argv[1:]
if not mots:
    sys.exit("donne au moins un identifiant")

fichiers = subprocess.run(["git", "ls-files", "*.py", "*.md", "*.json"],
                          capture_output=True, text=True,
                          check=True).stdout.split()

suspects = 0
for nom in fichiers:
    chemin = pathlib.Path(nom)
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        continue
    for numero, ligne in enumerate(lignes, start=1):
        if not ACCENTS.search(ligne):
            continue
        for mot in mots:
            if re.search(rf"\b{re.escape(mot)}\b", ligne):
                print(f"{nom}:{numero}: {ligne.strip()[:140]}")
                suspects += 1
                break

print(f"\n{suspects} ligne(s) à relire.")
sys.exit(1 if suspects else 0)
