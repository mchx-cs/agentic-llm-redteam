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

KEPT past the switch, deliberately. The French prose it was written for is
gone, but what remains is French DATA that will never be translated — the
judge's instruction, the demo target's system prompt and replies, the labelled
corpus, the refusal patterns — and that is exactly what a future rename pass
could damage silently. The glossary's rename procedure names it as step 2.
"""
import pathlib
import re
import subprocess
import sys

ACCENTS = re.compile(r"[éèêëàâçùûîïôœ]", re.IGNORECASE)

words = sys.argv[1:]
if not words:
    sys.exit("give at least one identifier")

files = subprocess.run(["git", "ls-files", "*.py", "*.md", "*.json"],
                          capture_output=True, text=True,
                          check=True).stdout.split()

suspects = 0
for name in files:
    path = pathlib.Path(name)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        continue
    for number, line in enumerate(lines, start=1):
        if not ACCENTS.search(line):
            continue
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", line):
                print(f"{name}:{number}: {line.strip()[:140]}")
                suspects += 1
                break

print(f"\n{suspects} line(s) to re-read.")
sys.exit(1 if suspects else 0)
