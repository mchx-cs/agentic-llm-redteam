"""
payloads/valider.py — Vérifie la bibliothèque avant de lancer une campagne.

La bibliothèque est un fichier de DONNÉES, édité à la main ou alimenté par
une source extérieure (garak, phase 7). Une erreur y est silencieuse : un
`{objectif}` oublié enverrait toujours le même texte, un prérequis mal
orthographié ne serait jamais évalué, et un identifiant en double rendrait
les rapports illisibles. Rien de tout ça ne lève d'exception — ça produit
juste une campagne qui ne teste pas ce qu'on croit.

D'où cette commande, à lancer après chaque modification :

    python -m payloads.valider

Elle sort en code 1 si quelque chose cloche, pour pouvoir être enchaînée
dans un script ou en intégration continue.
"""

import json
import re
import sys

from agents.attaquant import FICHIER_BIBLIOTHEQUE, TRANSFORMATIONS

# Les familles OWASP acceptées. Une famille inconnue n'est pas forcément une
# faute — la liste évolue — mais elle mérite qu'on la signale.
FAMILLES_CONNUES = {
    "LLM01:2025 Prompt Injection",
    "LLM02:2025 Sensitive Information Disclosure",
    "LLM03:2025 Supply Chain",
    "LLM04:2025 Data and Model Poisoning",
    "LLM05:2025 Improper Output Handling",
    "LLM06:2025 Excessive Agency",
    "LLM07:2025 System Prompt Leakage",
    "LLM08:2025 Vector and Embedding Weaknesses",
    "LLM09:2025 Misinformation",
    "LLM10:2025 Unbounded Consumption",
}

MOTIF_IDENTIFIANT = re.compile(r"^[a-z0-9-]+$")


def _prerequis_connus():
    # Importé ici : le planificateur importe l'attaquant, et on évite ainsi
    # une boucle d'imports au chargement du module.
    from agents.planificateur import PREREQUIS
    return set(PREREQUIS)


def valider(bibliotheque):
    """Renvoie (erreurs, avertissements) : deux listes de messages."""
    erreurs, avertissements = [], []
    prerequis_connus = _prerequis_connus()

    techniques = bibliotheque.get("techniques")
    objectifs = bibliotheque.get("objectifs")
    if not isinstance(techniques, list) or not isinstance(objectifs, list):
        return ["La bibliothèque doit contenir les listes 'techniques' et "
                "'objectifs'."], []

    # --- Techniques ---------------------------------------------------------
    vus = set()
    for numero, technique in enumerate(techniques, start=1):
        nom = technique.get("id") or f"technique n°{numero}"

        manquants = [c for c in ("id", "famille_owasp", "description",
                                 "prerequis", "modeles") if c not in technique]
        if manquants:
            erreurs.append(f"{nom} : champ(s) manquant(s) — "
                           f"{', '.join(manquants)}.")
            continue

        if not MOTIF_IDENTIFIANT.match(technique["id"]):
            erreurs.append(f"{nom} : l'identifiant doit être en minuscules, "
                           f"chiffres et tirets.")
        if technique["id"] in vus:
            erreurs.append(f"{nom} : identifiant en double.")
        vus.add(technique["id"])

        for prerequis in technique["prerequis"]:
            if prerequis not in prerequis_connus:
                # Le planificateur ignorerait silencieusement ce prérequis,
                # et la technique serait lancée contre des cibles où elle
                # n'a aucun sens.
                erreurs.append(
                    f"{nom} : prérequis '{prerequis}' inconnu du "
                    f"planificateur. Connus : "
                    f"{', '.join(sorted(prerequis_connus))}.")

        famille = technique["famille_owasp"]
        if famille is not None and famille not in FAMILLES_CONNUES:
            avertissements.append(
                f"{nom} : famille OWASP '{famille}' non reconnue. "
                f"Faute de frappe, ou liste à mettre à jour ?")

        for modele in technique["modeles"]:
            if not isinstance(modele, str) or not modele.strip():
                erreurs.append(f"{nom} : un modèle est vide.")
            elif "{objectif}" not in modele:
                # Sans le marqueur, la technique enverrait toujours le même
                # texte, quel que soit ce qu'on cherche à obtenir.
                erreurs.append(
                    f"{nom} : le modèle {modele[:40]!r} ne contient pas "
                    f"'{{objectif}}' — il ignorerait l'objectif visé.")
            else:
                try:
                    modele.format(objectif="X")
                except (KeyError, IndexError) as erreur:
                    erreurs.append(
                        f"{nom} : accolade non échappée dans {modele[:40]!r} "
                        f"({erreur}). Doubler les accolades littérales.")

        if not technique["modeles"] and technique["famille_owasp"]:
            avertissements.append(
                f"{nom} : aucun modèle, la technique ne sera jamais lancée "
                f"(le planificateur le signalera dans le rapport).")

    # --- Objectifs ----------------------------------------------------------
    vus = set()
    for numero, objectif in enumerate(objectifs, start=1):
        nom = objectif.get("id") or f"objectif n°{numero}"
        if not objectif.get("formulation"):
            erreurs.append(f"{nom} : formulation vide.")
        if objectif.get("id") in vus:
            erreurs.append(f"{nom} : identifiant en double.")
        vus.add(objectif.get("id"))

    if not any(t["modeles"] for t in techniques if t.get("modeles")):
        avertissements.append(
            "Aucune technique n'a de modèle : une campagne n'enverra rien.")

    return erreurs, avertissements


def principal():
    bibliotheque = json.loads(FICHIER_BIBLIOTHEQUE.read_text(encoding="utf-8"))
    erreurs, avertissements = valider(bibliotheque)

    techniques = bibliotheque.get("techniques", [])
    utilisables = [t for t in techniques if t.get("modeles")]
    combinaisons = sum(len(t["modeles"]) for t in utilisables) \
        * len(bibliotheque.get("objectifs", [])) * len(TRANSFORMATIONS)

    print(f"{FICHIER_BIBLIOTHEQUE.name} : {len(techniques)} technique(s), "
          f"dont {len(utilisables)} utilisable(s) — {combinaisons} payload(s) "
          f"au catalogue.")

    for message in avertissements:
        print(f"  [!]  {message}")
    for message in erreurs:
        print(f"  [X]  {message}")

    if erreurs:
        print(f"\n{len(erreurs)} erreur(s) : la bibliothèque n'est pas prête.")
        return 1
    print("\nBibliothèque valide.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
