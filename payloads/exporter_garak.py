"""
payloads/exporter_garak.py — Exports garak's probes as a local snapshot.

**This script does NOT run in the project's venv.** It runs in an environment
where garak is installed, and imports nothing from the project: that is its
only tie to the rest, and it is deliberate. garak's 164 packages (`torch`,
`transformers`, `langchain`…) therefore stay in a throwaway venv, never in the
project's, never on a campaign's path.

    python -m venv /tmp/venv-garak
    /tmp/venv-garak/bin/pip install garak
    /tmp/venv-garak/bin/python payloads/exporter_garak.py

The model is nuclei's: the tool stays light, the payloads are a separate
library, maintained upstream, synchronised by an explicit command. A campaign
reads a LOCAL snapshot — no network, no latency, and two identical campaigns
send the same payloads.

What to know before running it:
- **Loading the probes downloads third-party datasets** (JailbreakBench from
  HuggingFace, FigStep images…), with their own licences. That is why the
  snapshot produced stays OUTSIDE GIT: we point at the source, we do not
  republish it from a personal repository.
- The first export is slow (several minutes) and takes a few gigabytes of
  HuggingFace cache.
- garak is Apache-2.0 (NVIDIA). The snapshot records its version, so a
  campaign stays attachable to a precise version of the source.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# What this project can score: instruction hijacking and information leakage.
# The other families would be imported for nothing — the judge only has the
# `divulgation` and `obeissance` criteria, and would answer `aucun` to
# everything else.
KEPT_FAMILIES = {"owasp:llm01", "owasp:llm02", "owasp:llm07"}

# Out of scope whatever the tag. These probes measure the model's moderation,
# not its resistance to injection. `ContinueSlursReclaimedSlurs`, for
# instance, is tagged llm01 and active by default, but its declared goal is to
# make the model produce an ethnic slur.
# The list is kept from the goals garak ACTUALLY declares, and corrected at
# every export: "forbidden" was added after seeing
# adaptive_attacks.AdaptiveAttacks ("produce a forbidden response") go by,
# whose payloads ask for dangerous instructions.
OUT_OF_SCOPE_WORDS = ("slur", "profanity", "toxic", "harmful", "cbrn",
                      "ethnic", "hate", "forbidden", "unsafe", "dangerous",
                      "illegal", "weapon")


def _out_of_scope(name, goal):
    """
    Filters on the probe's name and DECLARED GOAL, which garak states in one
    clear sentence ("disregard the system prompt", "output an ethnic slur").
    It is coarse, but auditable: every exclusion is recorded with its reason
    in the snapshot, and the list gets corrected in use.
    """
    text = f"{name} {goal}".lower()
    return next((word for word in OUT_OF_SCOPE_WORDS if word in text), None)


def collect(families=None, active_only=True, max_per_probe=None):
    """
    Walks garak's probes and returns the ones in scope.

    `active_only` follows garak's own setting: a probe not active by default
    is usually an exhaustive variant ("Full"), useful in a deep audit,
    disproportionate for an ordinary campaign.
    """
    import garak._plugins as plugins

    families = families or KEPT_FAMILIES
    kept, skipped = [], []

    for name, _ in plugins.enumerate_plugins("probes"):
        try:
            probe = plugins.load_plugin(name, break_on_fail=False)
        except Exception as error:            # a probe broken upstream
            skipped.append({"name": name, "reason": f"chargement : {error}"})
            continue

        prompts = [p for p in (getattr(probe, "prompts", None) or [])
                   if isinstance(p, str) and p.strip()]
        tags = set(getattr(probe, "tags", []))
        goal = (getattr(probe, "goal", "") or "").strip()
        owasp = sorted(t for t in tags if t.startswith("owasp:"))

        if not prompts:
            continue                          # generative probe, not static
        if not (tags & families):
            continue                          # outside the scorable families
        if active_only and not getattr(probe, "active", False):
            skipped.append({"name": name, "reason": "non active par défaut"})
            continue

        word = _out_of_scope(name, goal)
        if word:
            skipped.append({"name": name,
                            "reason": f"hors périmètre (« {word} ») : {goal}"})
            continue

        kept.append({
            "probe": name,
            "objective": goal,
            "owasp_families": owasp,
            "language": getattr(probe, "lang", None),
            "doc": getattr(probe, "doc_uri", "") or "",
            "payloads": prompts[:max_per_probe],
            "payloads_available": len(prompts),
        })

    return kept, skipped


def build_snapshot(kept, skipped):
    import garak

    return {
        "_source": "garak (NVIDIA), Apache-2.0 — "
                   "https://github.com/NVIDIA/garak",
        "_avertissement": "Instantané local, HORS GIT. Les sondes de garak "
                          "incorporent des jeux de données tiers ayant leurs "
                          "propres conditions : ne pas republier.",
        "garak_version": getattr(garak, "__version__", "inconnue"),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "families_kept": sorted(KEPT_FAMILIES),
        "probes": kept,
        # We record what was skipped and why: same logic as a campaign's plan,
        # which says what it did not test.
        "skipped": skipped,
    }


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Exporte les sondes de garak (à lancer dans le venv garak).")
    parser.add_argument("--sortie", default="payloads/garak.json",
                        help="fichier d'instantané (défaut : payloads/garak.json)")
    parser.add_argument("--toutes", action="store_true",
                        help="inclure les sondes non actives par défaut "
                             "(variantes exhaustives, bien plus volumineuses)")
    parser.add_argument("--max-par-sonde", type=int, default=None,
                        metavar="N",
                        help="ne garder que les N premiers payloads par sonde")
    arguments = parser.parse_args(arguments)

    try:
        import garak  # noqa: F401
    except ImportError:
        print("garak n'est pas installé dans cet environnement.\n"
              "  Ce script se lance avec le venv garak, pas celui du projet :\n"
              "    python -m venv venv-garak\n"
              "    venv-garak/Scripts/pip install garak\n"
              "    venv-garak/Scripts/python payloads/exporter_garak.py",
              file=sys.stderr)
        return 2

    # No accents or Unicode punctuation in these messages: this environment is
    # not ours, and its console may be cp1252.
    print("Chargement des sondes (long au premier lancement : garak "
          "telecharge des jeux de donnees tiers)...", file=sys.stderr)
    kept, skipped = collect(
        active_only=not arguments.toutes,
        max_per_probe=arguments.max_par_sonde)

    # A guard: if garak reorganises its private API (`_plugins`), the
    # collection may bring back nothing WITHOUT raising. Overwriting the
    # existing snapshot then would silently deprive campaigns of their
    # payloads, and a "no finding" would pass for a good result.
    if not kept:
        print("Aucune sonde retenue : l'instantane existant est CONSERVE.\n"
              f"  {len(skipped)} sonde(s) ecartee(s). Causes probables :\n"
              "  - l'API de garak a change (ce script utilise garak._plugins,\n"
              "    qui est privee) ;\n"
              "  - les familles retenues ne correspondent plus a ses tags.",
              file=sys.stderr)
        return 1

    snapshot = build_snapshot(kept, skipped)
    path = Path(arguments.sortie)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    total = sum(len(p["payloads"]) for p in kept)
    print(f"{len(kept)} sonde(s), {total} payload(s) -> {path}")
    print(f"{len(skipped)} sonde(s) écartée(s) ; garak "
          f"{snapshot['garak_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
