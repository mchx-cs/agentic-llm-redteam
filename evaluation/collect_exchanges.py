"""
evaluation/collect_exchanges.py — Harvests real exchanges with the target.

The original labelled exchanges are FICTIONAL: written by hand, they reflect
what we imagine a target would reply. A real model's answers are more varied
and more surprising, and it is on those that the judge must be reliable. This
script sends the library's payloads to the real target and records the
exchanges in to_label.json.

After that it is the AUTHOR who labels each exchange, by hand: filling in
"attendu" (true/false), "categorie", "jeu" and "piege", then moving it into
labelled_exchanges.json.

Two deliberate choices:
- The prompts come from payloads/library.json and nothing else: the
  harvest holds only techniques already practised by hand.
- The judge's opinion is NOT recorded. Seeing its verdict would influence the
  human label, and we would end up measuring the judge against itself.

Run it from the project root with:  python -m evaluation.collect_exchanges
"""

import json
from pathlib import Path

from agents.attacker import generate_payloads
from targets import choose_target

OUTPUT_FILE = Path(__file__).parent / "to_label.json"

# Replies asked per payload: the target has randomness, two answers to the
# same payload can differ (one leaks, the other refuses…).
SAMPLE_COUNT = 2


def collect():
    # The one `.env` names: we therefore harvest from the decoy as readily as
    # from a real target, without touching this script.
    ask_target = choose_target()
    payloads = generate_payloads()
    exchanges = []

    # Bounded loops: payloads (a finite list) × SAMPLE_COUNT.
    for payload_number, payload in enumerate(payloads, start=1):
        # All the replies to one payload form a group: they will have to go
        # into the same set (dev or test), never be split between them.
        group = f"R{payload_number:02d}"
        for sample in range(1, SAMPLE_COUNT + 1):
            reply = ask_target(payload["text"])
            exchanges.append({
                "id": f"{group}-{sample}",
                "group": group,
                "category": None,      # to fill in by hand
                "dataset": None,            # to fill in by hand: "dev" or "test"
                "secret": "TOPSECRET42",
                "source": (f"real target — {payload['technique']} / "
                           f"{payload['objective']} / "
                           f"{payload['transformation']}"),
                "payload": payload["text"],
                "reply": reply,
                "expected": None,        # to fill in by hand: true or false
                "trap": "",            # to fill in by hand
            })
            print(f"{group}-{sample} collected")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"exchanges": exchanges}, f, ensure_ascii=False, indent=2)

    print(f"\n{len(exchanges)} exchanges written to {OUTPUT_FILE.name}, "
          f"to be labelled by hand.")


if __name__ == "__main__":
    collect()
