"""
payloads/validate.py — Checks the library before a campaign is launched.

The library is a DATA file, edited by hand or fed from an outside source
(garak, phase 7). A mistake in it is silent: a forgotten `{objectif}` would
always send the same text, a misspelled prerequisite would never be
evaluated, and a duplicate identifier would make the reports unreadable. None
of that raises an exception — it just produces a campaign that does not test
what you think.

Hence this command, to be run after every change:

    python -m payloads.validate

It exits with code 1 if something is wrong, so it can be chained in a script
or in continuous integration.
"""

import json
import re
import sys

from agents.attacker import (SNAPSHOT_AGE_SUSPECT, LIBRARY_FILE,
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
    from agents.planner import PREREQUISITES
    return set(PREREQUISITES)


def validate(library):
    """Returns (errors, warnings): two lists of messages."""
    errors, warnings = [], []
    known_prerequisites = _known_prerequisites()

    techniques = library.get("techniques")
    objectives = library.get("objectives")
    if not isinstance(techniques, list) or not isinstance(objectives, list):
        return ["The library must hold the lists 'techniques' and "
                "'objectives'."], []

    # --- Techniques ---------------------------------------------------------
    seen = set()
    for number, technique in enumerate(techniques, start=1):
        name = technique.get("id") or f"technique n°{number}"

        missing = [f for f in ("id", "owasp_family", "description",
                               "prerequisites", "templates") if f not in technique]
        if missing:
            errors.append(f"{name}: missing field(s) — "
                          f"{', '.join(missing)}.")
            continue

        if not IDENTIFIER_PATTERN.match(technique["id"]):
            errors.append(f"{name}: the identifier must be lowercase, "
                          f"digits and hyphens.")
        if technique["id"] in seen:
            errors.append(f"{name}: duplicate identifier.")
        seen.add(technique["id"])

        for prerequisite in technique["prerequisites"]:
            if prerequisite not in known_prerequisites:
                # The planner would silently ignore this prerequisite, and the
                # technique would be launched against targets where it makes
                # no sense at all.
                errors.append(
                    f"{name}: prerequisite '{prerequisite}' unknown to the "
                    f"planner. Known: "
                    f"{', '.join(sorted(known_prerequisites))}.")

        family = technique["owasp_family"]
        if family is not None and family not in KNOWN_FAMILIES:
            warnings.append(
                f"{name}: OWASP family '{family}' not recognised. A typo, "
                f"or a list to update?")

        for template in technique["templates"]:
            if not isinstance(template, str) or not template.strip():
                errors.append(f"{name}: a template is empty.")
            elif "{objectif}" not in template:
                # Without the marker, the technique would always send the same
                # text, whatever we are trying to obtain.
                errors.append(
                    f"{name}: the template {template[:40]!r} does not hold "
                    f"'{{objectif}}' — it would ignore the objective.")
            else:
                try:
                    template.format(objectif="X")
                except (KeyError, IndexError) as error:
                    errors.append(
                        f"{name}: unescaped brace in {template[:40]!r} "
                        f"({error}). Double any literal braces.")

        # Complete payloads (from garak) carry NO `{objectif}`: they are whole
        # prompts. They therefore have no business in `modeles`, and we only
        # check that they are text.
        for payload in technique.get("complete_payloads", []):
            if not isinstance(payload, str) or not payload.strip():
                errors.append(f"{name}: a complete payload is empty.")

        if (not technique["templates"] and not technique.get("complete_payloads")
                and technique["owasp_family"]):
            warnings.append(
                f"{name}: no template and no payload, the technique will "
                f"never be launched (the planner will say so in the "
                f"report).")

    # --- Objectives ---------------------------------------------------------
    seen = set()
    for number, objective in enumerate(objectives, start=1):
        name = objective.get("id") or f"objectif n°{number}"
        if not objective.get("wording"):
            errors.append(f"{name}: empty wording.")
        if objective.get("id") in seen:
            errors.append(f"{name}: duplicate identifier.")
        seen.add(objective.get("id"))

    if not any(t.get("templates") or t.get("complete_payloads")
               for t in techniques):
        warnings.append(
            "No technique has a template or a payload: a campaign will "
            "send nothing.")

    # Freshness of the garak snapshot: it releases roughly every 37 days
    # (median measured on 2026-11-10 over its last twelve versions), so past
    # two months a version has probably been missed. We flag, we do not block.
    age = (library.get("_garak") or {}).get("age_days")
    if age is not None and age > SNAPSHOT_AGE_SUSPECT:
        warnings.append(
            f"garak snapshot {age} days old: a resynchronisation is "
            f"probably worth it (see payloads/garak_export.py).")

    return errors, warnings


def main():
    # We validate the library AS THE CAMPAIGN WILL SEE IT, garak snapshot
    # included: a badly translated probe must be caught here, not halfway
    # through a campaign.
    from agents.attacker import load_library

    library = load_library()
    errors, warnings = validate(library)

    techniques = library.get("techniques", [])
    usable = [t for t in techniques
              if t.get("templates") or t.get("complete_payloads")]
    objectives = len(library.get("objectives", []))
    combinations = len(TRANSFORMATIONS) * (
        sum(len(t.get("templates", [])) for t in usable) * objectives
        + sum(len(t.get("complete_payloads", [])) for t in usable))

    source = ""
    if library.get("_garak"):
        garak = library["_garak"]
        age = garak.get("age_days")
        source = (f"\n  of which {garak['probes']} garak probe(s) "
                  f"{garak['version']}, exported on {garak['exported_at']}"
                  + (f" ({age} day(s) ago)" if age is not None else ""))

    print(f"{LIBRARY_FILE.name}: {len(techniques)} technique(s), "
          f"{len(usable)} of them usable — {combinations} payload(s) in the "
          f"catalogue.{source}")

    for message in warnings:
        print(f"  [!]  {message}")
    for message in errors:
        print(f"  [X]  {message}")

    if errors:
        print(f"\n{len(errors)} error(s): the library is not ready.")
        return 1
    print("\nLibrary valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
