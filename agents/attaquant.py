"""
agents/attaquant.py — The agent that generates attempts.

A payload is not a frozen string copied from one target to the next: it
depends on the context, and public versions get patched fast. So we build it
from three independent axes:

    payload = technique      (the attack family, stable over time)
            × objective      (what we want out of THIS target)
            × transformation (encoding, rewording… to get past filters)

Techniques and objectives live in payloads/bibliotheque.json (data, not
code). Transformations are Python functions, here.

This module SUPPLIES the bricks; planificateur.py CHOOSES, from the target's
profile, which ones to assemble and in what order. `generate_payloads()`
therefore only produces the full catalogue, ignoring context (useful for
collecting exchanges to label).

CURRENT STATE: only the "controle" technique (harmless) has templates of its
own. The OWASP families are declared but empty: a technique with no template
is skipped by the planner, which says so in its plan.
"""

import json
import re
from datetime import datetime
from itertools import product
from pathlib import Path

LIBRARY_FILE = Path(__file__).parent.parent / "payloads" / "bibliotheque.json"


# --- Transformations ---------------------------------------------------------
# Each takes a text and returns a text. This is PyRIT's "converters". For now
# nothing here serves to get past a filter: "majuscules" exists only to show
# that the axis works. The real ones (Base64, another language, leetspeak…)
# will come with the path.

def identity(text):
    return text


def uppercase(text):
    return text.upper()


TRANSFORMATIONS = {
    "identity": identity,
    "uppercase": uppercase,
}


# --- garak snapshot -----------------------------------------------------------
# Produced by `payloads/exporter_garak.py`, run in a separate venv. Absent
# from the repository (see .gitignore): garak's probes embed third-party
# datasets, which we do not republish from a personal repository. Whoever
# wants these payloads resynchronises.

GARAK_FILE = LIBRARY_FILE.parent / "garak.json"

# garak's tags already carry the OWASP mapping; we translate it into the
# project's vocabulary, and derive the family's prerequisite from it.
#
# Only the families the JUDGE can score appear here. Same logic as the
# exporter's scope filter: importing a family with no criterion to judge it
# would produce systematic `aucun` verdicts, hence a false impression of
# having tested.
#
# `owasp:llm07` was REMOVED on 2026-11-11: a dead entry, no probe in the
# snapshot carries it. A mapping that promises a family the source does not
# supply is worse than a missing one — it suggests coverage. System prompt
# leakage is therefore covered by hand-written payloads (the
# `fuite-prompt-systeme` technique).
GARAK_FAMILIES = {
    "owasp:llm01": ("LLM01:2025 Prompt Injection", []),
    "owasp:llm02": ("LLM02:2025 Sensitive Information Disclosure", ["secret"]),
}

# The tags garak ALSO puts on those probes, and which the judge cannot score.
# Verified on 2026-11-11 over the 52 probes in scope: llm06 (10 probes),
# llm09 (7) and llm05 (2). They are not lost — each one also carries llm01 or
# llm02, so it is genuinely launched — but announcing "LLM06 tested" would be
# false:
#
# - llm06: exfiltration through a Markdown URI, XSS, Jinja and SQL injection.
#   These are attacks on the APPLICATION around the model, and they assume a
#   client that renders Markdown. Our target is a text chatbot, and the
#   judge's `abus_outils` criterion speaks of tool calls, not of this.
# - llm09: making the model import non-existent packages. Scoring requires
#   checking whether the package exists — garak has a dedicated detector, we
#   do not.
# - llm05: the two `ansiescape` probes, already covered by llm01.
#
# We RECORD them in the report rather than keeping quiet: "this probe also
# touches LLM06, which we cannot score" is honest information.
UNJUDGEABLE_FAMILIES = {
    "owasp:llm05": "LLM05:2025 Improper Output Handling",
    "owasp:llm06": "LLM06:2025 Excessive Agency",
    "owasp:llm08": "LLM08:2025 Vector and Embedding Weaknesses",
    "owasp:llm09": "LLM09:2025 Misinformation",
}


# garak fills its own placeholders at run time. Leaving them as they are would
# weaken the payload: the target would see "{generator.name}" instead of an
# assistant's name, and many jailbreaks rest on that name. A neutral
# replacement beats a visible placeholder.
GARAK_PLACEHOLDERS = {"{generator.name}": "the assistant"}


def _fill_placeholders(payload):
    for placeholder, value in GARAK_PLACEHOLDERS.items():
        payload = payload.replace(placeholder, value)
    return payload


# garak releases roughly every 37 days (median measured on 2026-11-10 over its
# last twelve versions). Past two months a snapshot has therefore probably
# missed a version or two: we flag it, without blocking anything.
SNAPSHOT_AGE_SUSPECT = 60


def _age_in_days(timestamp):
    """The snapshot's age, or None if it is unreadable."""
    try:
        return (datetime.now() - datetime.fromisoformat(timestamp)).days
    except (TypeError, ValueError):
        return None


# --- Relevance: what each garak MODULE demands of the target -----------------
# Until 2026-11-11, 73% of the payloads (845/1,143) went out against any
# target at all: prerequisites came from the OWASP family alone, and
# `owasp:llm01` declares none. As a result a "print ANSI terminal codes" probe
# was launched against a library chatbot.
#
# The mapping is done at MODULE level, not probe level: the objectives garak
# declares are homogeneous inside a module (all fifteen `encoding` probes say
# "make the model say an encoded payload"), and the module is already the
# grain of the round-robin. A per-probe table would be fifteen times longer
# for the same information.
#
# A module absent from this table demands nothing in particular, and that is
# the right default: `encoding`, `goodside` and `promptinject` apply to any
# model. NEVER add a prerequisite here as a precaution — skipping a probe that
# might have worked costs an undiscovered vulnerability, which is worse than a
# wasted attempt.
PREREQUISITES_BY_MODULE = {
    # Disobeying instructions assumes there are some.
    "dan": ["instructions"],
    "phrasing": ["instructions"],
    "sata": ["instructions"],
    # Importing a non-existent package assumes the target writes code.
    "packagehallucination": ["writes-code"],
    # An injection hidden in an excerpt, a report or a translation assumes the
    # target reads the content it is handed.
    "latentinjection": ["handles-documents"],
    # The next three depend on the APPLICATION around the model, which the
    # target does not know about: prerequisites declared by the operator.
    "ansiescape": ["terminal"],
    "web_injection": ["rich-rendering"],
    "exploitation": ["database"],
}


def _module_of(probe):
    """A probe's garak module: `probes.dan.DanInTheWild` -> `dan`."""
    return probe["probe"].replace("probes.", "").split(".")[0].lower()


def _technique_from_probe(probe):
    """Translates a garak probe into a project technique."""
    family, prerequisites = next(
        (GARAK_FAMILIES[t] for t in probe["owasp_families"]
         if t in GARAK_FAMILIES), (None, []))
    # The two sources of prerequisites add up: the OWASP family says what the
    # attack SEEKS (a secret, instructions), the module what it DEMANDS of the
    # context (code, a terminal). Confusing them would miss one or the other.
    prerequisites = sorted(set(prerequisites)
                           | set(PREREQUISITES_BY_MODULE.get(
                               _module_of(probe), [])))
    identifier = "garak-" + re.sub(
        r"[^a-z0-9]+", "-", probe["probe"].replace("probes.", "").lower()
    ).strip("-")
    return {
        "id": identifier,
        # The garak MODULE (`encoding`, `dan`, `web_injection`…). This is the
        # right grain for the round-robin: `encoding` is fifteen of the
        # fifty-two probes in scope, and they are fifteen variants of the same
        # test ("make the model say an encoded payload"). Without this
        # grouping they got fifteen turns where `dan` got three, and a wider
        # budget would have burned itself on encoding variants.
        "group": _module_of(probe),
        "owasp_family": family,
        # What the probe ALSO touches, and the judge cannot score. Launching
        # without saying so would suggest these families are covered; keeping
        # quiet would suggest they are not even reached. The report therefore
        # presents them as "touched, not judged".
        "families_not_scorable": sorted(
            {UNJUDGEABLE_FAMILIES[t] for t in probe["owasp_families"]
             if t in UNJUDGEABLE_FAMILIES}),
        "description": probe["objective"] or probe["probe"],
        "prerequisites": prerequisites,
        # garak's prompts are COMPLETE: they carry no `{objectif}` placeholder,
        # so they have no business in `modeles`, which the validator checks on
        # exactly that point.
        "templates": [],
        "complete_payloads": [_fill_placeholders(p) for p in probe["payloads"]],
        "source": f"garak {probe['probe']}",
    }


# Composition template: a complete payload from garak serves as the PREAMBLE
# (it installs a persona, it defuses the instructions), and the objective
# supplies the REQUEST. Measured on 2026-11-11: on their own these payloads
# crack the persona — `obeissance` verdict — but never ask for THIS target's
# secret, so they almost never produce a `divulgation`. Composing the two is
# exactly what the "objective" axis was meant to allow.
#
# This template stays in French, deliberately: the library's objectives are
# French, and so is the demo target. Translating it would break the sentence
# it builds, not internationalise it — that would take a localised library.
COMPOSITION = "{preambule}\n\nMaintenant, peux-tu {demande} ?"


def compose(preamble, objective):
    """Assembles a complete payload and an objective into a single request."""
    return COMPOSITION.format(preambule=preamble.rstrip(),
                              demande=objective["wording"])


# The same pair of ingredients, delivered in TWO turns instead of one (3b).
SECOND_TURN_REQUEST = "Maintenant, peux-tu {demande} ?"


def sequence_turns(preamble, objective):
    """
    The preamble and the request as two separate messages.

    This is `compose` cut in half, and it is not a presentation detail: it is
    how these attacks work in practice. You install the persona, you let the
    target accept it — its own reply then becomes part of its context — and
    then you ask. Composed into a single message, the model sees the whole
    manoeuvre at once and can refuse it wholesale.

    The measurement value is there: the SAME two ingredients, in one message
    or in two. The difference therefore measures multi-turn, and nothing else
    — not a change of payload, not a change of target. This was route 2 of the
    three left open by the garak/target gap in phase 12.
    """
    return [preamble.rstrip(),
            SECOND_TURN_REQUEST.format(demande=objective["wording"])]


# --- Building the payloads ---------------------------------------------------

def load_library(with_garak=True):
    """
    Loads the library, enriched with the garak snapshot if it is present.

    The snapshot is optional by construction: without it the repository runs
    exactly as before. That is nuclei's model — the tool stays light, the
    payloads are synchronised separately.
    """
    with open(LIBRARY_FILE, encoding="utf-8") as f:
        library = json.load(f)

    if with_garak and GARAK_FILE.exists():
        from migration import modernise

        with open(GARAK_FILE, encoding="utf-8") as f:
            # A snapshot on disk may predate the data-key translation: it is
            # outside git, so the migration never reached it.
            snapshot = modernise(json.load(f))
        library["techniques"] = library["techniques"] + [
            _technique_from_probe(s) for s in snapshot["probes"]]
        library["_garak"] = {
            "version": snapshot.get("garak_version"),
            "exported_at": snapshot.get("exported_at"),
            "probes": len(snapshot["probes"]),
            "age_days": _age_in_days(snapshot.get("exported_at")),
        }

    return library


def generate_payloads():
    """
    Returns the list of every possible payload: each template of each
    technique, crossed with each objective and each transformation.

    The list is finite by construction (a product of finite lists), but it
    grows fast: it is MAX_ESSAIS, in main.py, that bounds the campaign.
    """
    library = load_library()
    payloads = []

    for technique in library["techniques"]:
        # A technique with no template is declared but not yet ready.
        for template, objective, transformation_name in product(
            technique["templates"], library["objectives"], TRANSFORMATIONS
        ):
            text = template.format(objectif=objective["wording"])
            payloads.append({
                "technique": technique["id"],
                "owasp_family": technique["owasp_family"],
                "objective": objective["id"],
                "transformation": transformation_name,
                "text": TRANSFORMATIONS[transformation_name](text),
            })

        # Payloads coming from outside are COMPLETE prompts: they already
        # carry their own intention, and therefore do not cross with the
        # objective axis. Hence `objectif: None`.
        for number, payload in enumerate(
                technique.get("complete_payloads", []), start=1):
            # Two uses of one payload, which do NOT test the same thing: on
            # its own it measures resistance to hijacking; composed with an
            # objective it goes after what the target protects.
            variants = [(o, compose(payload, o))
                        for o in library["objectives"]]
            variants.append((None, payload))
            for objective, text in variants:
                for transformation_name in TRANSFORMATIONS:
                    payloads.append({
                        "technique": technique["id"],
                        "owasp_family": technique["owasp_family"],
                        "objective": objective["id"] if objective else None,
                        "transformation": transformation_name,
                        "text": TRANSFORMATIONS[transformation_name](text),
                        "source": technique.get("source"),
                        "payload_number": number,
                    })

    return payloads
