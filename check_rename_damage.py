# -*- coding: utf-8 -*-
"""
check_rename_damage.py — Finds an ENGLISH identifier dropped into a FRENCH
sentence by a rename pass.

This is the worst of the hazards the glossary lists, because the test suite
stays GREEN: renaming `prochain` to `next_attempt` rewrote twelve French
sentences, including two strings rendered into the client-facing report and a
target reply pinned VERBATIM in a test. A test whose data is falsified no
longer tests what it claims.

Run it after every rename pass, naming the identifiers you just introduced:

    python check_rename_damage.py history ask_llm call_log

Exit code 1 when there is something to re-read. It reports lines, never
rewrites them: deciding whether `ask_llm` legitimately appears inside a
French comment is a reading job, not a substitution.

TEMPORARY. This script exists for the French-to-English switch and goes away
with the last French sentence it has to protect.
"""
import pathlib
import re
import subprocess
import sys

ACCENTS = re.compile(r"[éèêëàâçùûîïôœ]", re.IGNORECASE)

mots = sys.argv[1:]
if not mots:
    sys.exit("donne au moins un identifiant")

files = subprocess.run(["git", "ls-files", "*.py", "*.md", "*.json"],
                          capture_output=True, text=True,
                          check=True).stdout.split()

suspects = 0
for nom in files:
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
