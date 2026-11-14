"""
payloads/valider.py — Checks the library before a campaign is launched.

The library is a DATA file, edited by hand or fed from an outside source
(garak, phase 7). A mistake in it is silent: a forgotten `{objectif}` would
always send the same text, a misspelled prerequisite would never be
evaluated, and a duplicate identifier would make the reports unreadable. None
of that raises an exception — it just produces a campaign that does not test
what you think.

Hence this command, to be run after every change:

    python -m payloads.valider

It exits with code 1 if something is wrong, so it can be chained in a script
or in continuous integration.
"""

import json
import re
import sys

from agents.attaquant import (SNAPSHOT_AGE_SUSPECT, LIBRARY_FILE,
                              TRANSFORMATIONS)

# The accepted OWASP families. An unknown family is not necessarily a mistake
# — the list evolves — but it deserves to be flagged.
KNOWN_FAMILIES = {
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

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9-]+$")


def _known_prerequisites():
    # Imported here: the planner imports the attacker, and this avoids an
    # import cycle at module load.
    from agents.planificateur import PREREQUISITES
    return set(PREREQUISITES)


def valider(library):
    """Returns (errors, warnings): two lists of messages."""
    errors, warnings = [], []
    known_prerequisites = _known_prerequisites()

    techniques = library.get("techniques")
    objectives = library.get("objectifs")
    if not isinstance(techniques, list) or not isinstance(objectives, list):
        return ["La bibliothèque doit contenir les listes 'techniques' et "
                "'objectifs'."], []

    # --- Techniques ---------------------------------------------------------
    seen = set()
    for number, technique in enumerate(techniques, start=1):
        name = technique.get("id") or f"technique n°{number}"

        missing = [f for f in ("id", "famille_owasp", "description",
                               "prerequis", "modeles") if f not in technique]
        if missing:
            errors.append(f"{name} : champ(s) manquant(s) — "
                          f"{', '.join(missing)}.")
            continue

        if not IDENTIFIER_PATTERN.match(technique["id"]):
            errors.append(f"{name} : l'identifiant doit être en minuscules, "
                          f"chiffres et tirets.")
        if technique["id"] in seen:
            errors.append(f"{name} : identifiant en double.")
        seen.add(technique["id"])

        for prerequisite in technique["prerequis"]:
            if prerequisite not in known_prerequisites:
                # The planner would silently ignore this prerequisite, and the
                # technique would be launched against targets where it makes
                # no sense at all.
                errors.append(
                    f"{name} : prérequis '{prerequisite}' inconnu du "
                    f"planificateur. Connus : "
                    f"{', '.join(sorted(known_prerequisites))}.")

        family = technique["famille_owasp"]
        if family is not None and family not in KNOWN_FAMILIES:
            warnings.append(
                f"{name} : famille OWASP '{family}' non reconnue. "
                f"Faute de frappe, ou liste à mettre à jour ?")

        for template in technique["modeles"]:
            if not isinstance(template, str) or not template.strip():
                errors.append(f"{name} : un modèle est vide.")
            elif "{objectif}" not in template:
                # Without the marker, the technique would always send the same
                # text, whatever we are trying to obtain.
                errors.append(
                    f"{name} : le modèle {template[:40]!r} ne contient pas "
                    f"'{{objectif}}' — il ignorerait l'objectif visé.")
            else:
                try:
                    template.format(objectif="X")
                except (KeyError, IndexError) as error:
                    errors.append(
                        f"{name} : accolade non échappée dans "
                        f"{template[:40]!r} ({error}). Doubler les accolades "
                        f"littérales.")

        # Complete payloads (from garak) carry NO `{objectif}`: they are whole
        # prompts. They therefore have no business in `modeles`, and we only
        # check that they are text.
        for payload in technique.get("payloads_complets", []):
            if not isinstance(payload, str) or not payload.strip():
                errors.append(f"{name} : un payload complet est vide.")

        if (not technique["modeles"] and not technique.get("payloads_complets")
                and technique["famille_owasp"]):
            warnings.append(
                f"{name} : aucun modèle ni payload, la technique ne sera "
                f"jamais lancée (le planificateur le signalera dans le "
                f"rapport).")

    # --- Objectives ---------------------------------------------------------
    seen = set()
    for number, objective in enumerate(objectives, start=1):
        name = objective.get("id") or f"objectif n°{number}"
        if not objective.get("formulation"):
            errors.append(f"{name} : formulation vide.")
        if objective.get("id") in seen:
            errors.append(f"{name} : identifiant en double.")
        seen.add(objective.get("id"))

    if not any(t.get("modeles") or t.get("payloads_complets")
               for t in techniques):
        warnings.append(
            "Aucune technique n'a de modèle ni de payload : une campagne "
            "n'enverra rien.")

    # Freshness of the garak snapshot: it releases roughly every 37 days
    # (median measured on 2026-11-10 over its last twelve versions), so past
    # two months a version has probably been missed. We flag, we do not block.
    age = (library.get("_garak") or {}).get("age_jours")
    if age is not None and age > SNAPSHOT_AGE_SUSPECT:
        warnings.append(
            f"instantané garak vieux de {age} jours : une resynchronisation "
            f"vaut sans doute le coup (voir payloads/exporter_garak.py).")

    return errors, warnings


def main():
    # We validate the library AS THE CAMPAIGN WILL SEE IT, garak snapshot
    # included: a badly translated probe must be caught here, not halfway
    # through a campaign.
    from agents.attaquant import load_library

    library = load_library()
    errors, warnings = valider(library)

    techniques = library.get("techniques", [])
    usable = [t for t in techniques
              if t.get("modeles") or t.get("payloads_complets")]
    objectives = len(library.get("objectifs", []))
    combinations = len(TRANSFORMATIONS) * (
        sum(len(t.get("modeles", [])) for t in usable) * objectives
        + sum(len(t.get("payloads_complets", [])) for t in usable))

    source = ""
    if library.get("_garak"):
        garak = library["_garak"]
        age = garak.get("age_jours")
        source = (f"\n  dont {garak['sondes']} sonde(s) garak "
                  f"{garak['version']}, exportées le {garak['exporte_le']}"
                  + (f" (il y a {age} jour(s))" if age is not None else ""))

    print(f"{LIBRARY_FILE.name} : {len(techniques)} technique(s), "
          f"dont {len(usable)} utilisable(s) — {combinations} payload(s) "
          f"au catalogue.{source}")

    for message in warnings:
        print(f"  [!]  {message}")
    for message in errors:
        print(f"  [X]  {message}")

    if errors:
        print(f"\n{len(errors)} erreur(s) : la bibliothèque n'est pas prête.")
        return 1
    print("\nBibliothèque valide.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
