"""
payloads/garak_source.py — Takes stock of the garak source (phase 7).

garak (NVIDIA, Apache-2.0) maintains a collection of probes kept current as
models evolve. Rather than writing payloads by hand — which age fast and
commit nobody but us — we lean on that recognised source.

**Without installing garak.** The package pulls 164 dependencies, `torch` and
`transformers` among them: several gigabytes, which would ruin the project's
light-install promise. But its payloads live in self-contained JSON files,
which can be read directly.

**Without copying anything into the repository either**, on the day we
import. Three reasons:
- the repository is public, and republishing a third party's offensive corpus
  from a personal account is not the same as pointing at it;
- Apache-2.0 covers garak's code, but several of these data files come from
  third-party datasets whose own terms have not been checked. Pointing at the
  source avoids the question;
- garak updates its probes: re-importing beats freezing a copy.

Each file's SHA comes with the inventory: a campaign stays attachable to a
precise version of the source.

**WHAT THIS MODULE DOES TODAY: it takes stock, it does not import.**
The inventory invalidated the starting hypothesis. The files in
`garak/data/payloads/` are not attacks, they are INGREDIENTS the probes
assemble: `encoded.json` holds 2 high-perplexity strings,
`domains_latentinjection.json` 3 example domain names,
`normal_instructions.json` 5 harmless requests. The attack templates
themselves live in the probes' Python code (`garak/probes/*.py`), hence
behind the 164 dependencies.

Consequence: importing those JSON files would yield no attack technique at
all. Still useful here — `normal_instructions.json` and `text_en.json` would
enrich the `controle` technique, and `garak/data/tags.misp.tsv` supplies the
OWASP vocabulary (`owasp:llm01` … `owasp:llm10`) for the family mapping.

    python -m payloads.garak_source --lister
    python -m payloads.garak_source --decrire encoded.json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from console import write_in_utf8

REPOSITORY = "NVIDIA/garak"
PAYLOADS_PATH = "garak/data/payloads"
SOURCE_LICENCE = "garak (NVIDIA), Apache-2.0 — https://github.com/NVIDIA/garak"

# What this project tests: instruction hijacking and information leakage.
# garak files on a wholly different subject (harmful content, slurs) are not
# offered by default: they would measure the model's moderation, not its
# resistance to injection, and the judge has no criterion to score them
# anyway.
OUT_OF_SCOPE = {
    "harmful_behaviors.json": "harmful content — measures moderation, "
                              "not injection; the judge has no criterion for it",
    "slur_terms_en.json": "slurs — outside the project's scope",
    "rude_french.json": "slurs — outside the project's scope",
    "rude_chinese.json": "slurs — outside the project's scope",
}


def _fetch(url, timeout=30):
    request = urllib.request.Request(
        url, headers={"User-Agent": "agentic-llm-redteam (importeur garak)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"{url}: HTTP error {error.code}. Has the garak repository "
            f"changed structure?") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"{url}: unreachable ({error.reason}). Check your connection."
        ) from error


def latest_version(timeout=10):
    """
    garak's latest published version, or None if the call fails.

    A single call to the GitHub API, no download: we DETECT that an update
    exists, we do not perform it. Updating stays a deliberate act — it changes
    the payloads sent, and a campaign must stay reproducible. Same rule as
    `nuclei -update-templates`.

    Never raises: an unavailable network must not get in a campaign's way.
    """
    try:
        data = json.loads(_fetch(
            f"https://api.github.com/repos/{REPOSITORY}/releases/latest", timeout))
        return data.get("tag_name", "").lstrip("v") or None
    except Exception:
        return None


def compare_to_snapshot(local_version, timeout=10):
    """
    Returns (remote_version, behind) — or (None, False) when we cannot tell.

    Saying "a newer version exists" beats a day counter: garak releases every
    37 days on median, but not all its releases touch the probes.
    """
    remote = latest_version(timeout)
    if not remote or not local_version:
        return remote, False
    return remote, _rank(remote) > _rank(local_version)


def _rank(version):
    """A version as a tuple of integers, so 0.9.0 and 0.17.1 compare right."""
    numbers = []
    for chunk in str(version).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        numbers.append(int(digits) if digits else 0)
    return tuple(numbers)


def list_files(ref="main"):
    """Lists the available payload files, with their SHA."""
    content = json.loads(_fetch(
        f"https://api.github.com/repos/{REPOSITORY}/contents/{PAYLOADS_PATH}"
        f"?ref={ref}"))
    return sorted(
        ({"name": e["name"], "size": e["size"], "sha": e["sha"]}
         for e in content
         if e["type"] == "file" and e["name"].endswith(".json")),
        key=lambda e: e["name"])


def describe(name, ref="main"):
    """Reads a payload file's METADATA, and counts its entries."""
    data = json.loads(_fetch(
        f"https://raw.githubusercontent.com/{REPOSITORY}/{ref}/{PAYLOADS_PATH}/{name}"))
    return {
        "name": name,
        "title": data.get("garak_payload_name", ""),
        "types": data.get("payload_types", []),
        "language": data.get("lang", ""),
        "intent": data.get("intent"),
        "count": len(data.get("payloads", [])),
        # garak's comments often categorise the payloads: they say what the
        # file is about without our having to print its content.
        "categories": sorted({c.lstrip("# ").strip()
                              for c in data.get("_payload_comments", [])
                              if c.strip().startswith("#")}),
    }


def _prefix(family):
    """`LLM07` out of "LLM07:2025 System Prompt Leakage"."""
    return (family or "").split(":")[0].strip()


def redundant_techniques(library):
    """
    The HAND-WRITTEN techniques whose family garak now covers.

    Why this guard. Two techniques in the repository exist only because garak
    supplied no probe for their family: the eleven LLM07 payloads (verified
    2026-11-11) and the four LLM06 payloads (verified 2026-11-12). But
    hand-written payloads rot — a 2026 jailbreak fails in 2027 — and their
    upkeep falls on one person, which is exactly the argument that made garak
    a synchronised source in the first place. The day a garak probe carries
    LLM06 or LLM07 as its PRIMARY family, the hand-written set becomes a debt
    to re-read.

    Nothing is removed automatically: the machine detects and reports, the
    human decides and re-reads. That is the principle already chosen for
    resynchronisation itself, and it holds all the more here — four registers
    written for one precise target may stay better than a generic probe
    carrying the right tag.

    We look only at PRIMARY families, never at secondary ones: ten probes
    carry `owasp:llm06` as a secondary tag, and they aim at the application
    around the model (exfiltration through a Markdown URI, XSS, Jinja or SQL
    injection), not at tool calls. Counting them here would announce a hole
    filled that is not.
    """
    garak_families = {_prefix(technique.get("owasp_family"))
                      for technique in library["techniques"]
                      if technique.get("source")}
    garak_families.discard("")

    redundant = []
    for technique in library["techniques"]:
        if technique.get("source"):
            continue           # a garak probe is not a hand-written debt
        family = _prefix(technique.get("owasp_family"))
        # With no payload there is nothing to remove: `divulgation-
        # information` is empty, so its redundancy with the LLM02 probes costs
        # nothing and the planner already flags it. And `controle`, which has
        # no family, is never redundant: it is the harmless control, which no
        # offensive probe replaces.
        count = (len(technique.get("templates") or [])
                  + len(technique.get("complete_payloads") or []))
        if family and count and family in garak_families:
            redundant.append({
                "id": technique["id"],
                "family": family,
                "payloads": count,
                "probes": sum(1 for other in library["techniques"]
                              if other.get("source")
                              and _prefix(other.get("owasp_family")) == family),
            })
    return redundant


def _report_redundancies(library):
    """What `--version` says about the hand-written techniques, up to date
    or not."""
    redundant = redundant_techniques(library)
    if not redundant:
        return
    print("\nSome hand-written techniques may have become redundant:")
    for technique in redundant:
        print(f"  {technique['id']} ({technique['payloads']} hand-written "
              f"payload(s)) — {technique['probes']} garak probe(s) now carry "
              f"{technique['family']} as their primary family.")
    print("  Re-read those probes before removing anything: a tag is not a "
          "measurement.")


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Lists garak's payloads, without installing garak.")
    parser.add_argument("--list", "--lister", action="store_true",
                        dest="list_files",
                        help="list the files available")
    parser.add_argument("--describe", "--decrire", metavar="FILE",
                        dest="describe",
                        help="a file's metadata (without its content)")
    parser.add_argument("--ref", default="main",
                        help="garak branch or tag (default: main)")
    parser.add_argument("--version", action="store_true",
                        help="compare the local snapshot's version with the "
                             "latest published one (no download)")
    arguments = parser.parse_args(arguments)

    if arguments.version:
        from agents.attacker import load_library

        local = (load_library().get("_garak") or {}).get("version")
        remote, behind = compare_to_snapshot(local)
        print(f"local snapshot  : garak {local or 'none'}")
        print(f"latest published: garak {remote or 'unknown (offline?)'}")
        if behind:
            print("\nA newer version exists. To resynchronise:\n"
                  "  python -m venv venv-garak\n"
                  "  venv-garak/Scripts/pip install -U garak\n"
                  "  venv-garak/Scripts/python payloads/garak_export.py\n"
                  "\nRe-read what the export keeps before launching a "
                  "campaign: a new version can add out-of-scope probes.")
        elif remote and local:
            print("\nThe snapshot is up to date.")
        # Reported in both cases: redundancy is about the snapshot we have,
        # not about how far behind we are. An up-to-date version may very well
        # have just filled the LLM06 or LLM07 hole.
        _report_redundancies(load_library())
        return 1 if behind else 0

    if arguments.describe:
        info = describe(arguments.describe, arguments.ref)
        print(f"{info['name']} — {info['title']}")
        print(f"  {info['count']} payload(s), language "
              f"'{info['language']}', types "
              f"{', '.join(info['types']) or '—'}")
        if info["intent"]:
            print(f"  intent: {info['intent']}")
        if info["categories"]:
            print(f"  categories: {', '.join(info['categories'])}")
        return 0

    if not arguments.list_files:
        parser.print_help()
        return 1

    files = list_files(arguments.ref)
    print(f"{len(files)} payload file(s) in {REPOSITORY} "
          f"({arguments.ref}):\n")
    for entry in files:
        mark = "  " if entry["name"] not in OUT_OF_SCOPE else "x "
        print(f"{mark}{entry['name']:<34} {entry['size']:>6} o")
    if any(f["name"] in OUT_OF_SCOPE for f in files):
        print("\nx = outside this project's scope:")
        for name, reason in OUT_OF_SCOPE.items():
            if any(f["name"] == name for f in files):
                print(f"    {name}: {reason}")
    print(f"\nSource : {SOURCE_LICENCE}")
    print("One file in detail: --describe <name>")
    return 0


if __name__ == "__main__":
    write_in_utf8()
    sys.exit(main())
