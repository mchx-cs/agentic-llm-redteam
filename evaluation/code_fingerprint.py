"""
evaluation/code_fingerprint.py — a digest of the modules a campaign's
behaviour depends on, so a resumed measurement cannot mix two versions of
them.

WHY THIS EXISTS. `measure_modes` resumes an interrupted run, and it refuses to
resume across a change of target, protocol, arms, scope or JUDGE. Each of
those answers a way the figure could be CORRUPTED rather than merely stale.
One was missing, and it was found the moment it mattered: on 2026-11-25, with
a 20-pair run in flight, the refusal patterns, the tool marker and the
replay's value test were all about to be widened. Nothing in the protocol
block would have noticed.

The pairs already on disk were measured by one version of
`agents/adaptation.py`; the pairs after a resume would be measured by
another. Adaptation chooses which payload goes next, so that is not a
cosmetic difference — it is two measurements under one sign test, which is
the pooling this project refuses for defence levels, for formats, for
languages and for judges.

WHAT IS IN THE DIGEST, and the list is a DECISION rather than "every file".
A digest over the whole repository would change on a docstring and refuse
every legitimate resume, which is the guard that cries wrong until people
stop reading it. So: the modules whose text decides what a campaign SENDS and
how its outcome is COUNTED.

WHAT IS NOT IN IT: the judge's instruction, which `judge_identity` and the
protocol's own fields already cover; the report's rendering, which cannot
change a count; and the targets, which are named by `target` already.

A CAVEAT, stated because it is the honest limit: this is a digest of file
TEXT, so it changes on a comment. That is the safe direction — a refused
resume costs an hour, a pooled measurement costs the result — and the message
says plainly that a comment is enough to trip it, so an operator is not left
hunting for a behaviour change that is not there.
"""

import hashlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The modules whose TEXT decides what a campaign sends and how its outcome is
#: counted. Each line says why it is here, because a list nobody can justify
#: becomes a list nobody dares shorten.
WATCHED = (
    # Chooses the next attempt from the replies: its patterns decide the order.
    "agents/adaptation.py",
    # Decides which attempts exist at all, and in what order.
    "agents/planner.py",
    # EN AMONT DU PLANIFICATEUR, et ajoute le 2026-11-27 : `objectives_for`
    # construit les objectifs depuis le PROFIL, donc le jeu de sondes et le
    # prompt de l'analyste decident de ce qu'une campagne envoie. Ce jour-la
    # `RECON_BUDGET` est passe de 6 a 7 -- une reprise aurait mesure ses
    # premieres paires avec six sondes et les suivantes avec sept, sous un
    # seul test des signes, et le compte de requetes par campagne change
    # avec lui.
    "agents/reconnaissance.py",
    # Builds the payload text from technique x objective x transformation.
    "agents/attacker.py",
    # Decides whether a disclosed value is replayable, hence `high` severity.
    "agents/verifier.py",
    # The attempt loop, the denominator states, the deliveries.
    "main.py",
    # The denominator itself: which states are scorable.
    "stats.py",
    # The payloads. A data file, and the one most likely to move.
    "payloads/library.json",
)


def code_fingerprint(watched=WATCHED):
    """
    A short digest of the watched files, or None if any is missing.

    None rather than a partial digest: a digest computed over a different set
    of files is a digest of something else, and comparing it would be worse
    than not comparing. A caller that gets None says so instead of claiming a
    match.
    """
    digest = hashlib.sha256()
    for name in watched:
        path = ROOT / name
        if not path.exists():
            return None
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
