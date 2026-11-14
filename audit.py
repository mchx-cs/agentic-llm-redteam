"""
audit.py — Under what mandate we tested, and what we actually sent.

Two halves of one requirement: being able to prove that what we did was
authorised, and being able to show exactly what we did.

1. **The authorisation.** The project's legal framing says LLM red teaming is
   lawful only against a system you own or are explicitly authorised to test.
   Until now that was a sentence in a file; here, it is the code refusing to
   start.

2. **The audit trail.** A JSONL file, written AS IT GOES, recording every
   exchange with the target. Writing continuously rather than at the end is
   not a detail: if the campaign falls over, we keep the trace of what has
   already been sent — and that is precisely when we need it.

The level of demand follows the risk: the bundled decoy and the deterministic
target ask for nothing, since they are yours and run locally. A remote
endpoint does require a mandate. Imposing the same form on both would mostly
teach people to click without reading.
"""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

AUTHORISATION_FILE = "autorisation.json"

REQUIRED_FIELDS = ("target", "authorised_by", "reference", "start", "end")

# A local target is yours by construction: no mandate to produce.
_LOCAL_MARKERS = ("localhost", "127.0.0.1", "[::1]")


class MissingAuthorisation(RuntimeError):
    """No valid mandate for this target: the campaign does not start."""


def is_local(target_name):
    """
    A target bundled with the project, or served from this machine.

    The named targets of the `cibles` package are yours by construction: they
    run locally and hold nothing but fictional secrets. The list is asked of
    `cibles` rather than copied here — otherwise it would drift, and a bundled
    target would end up demanding a mandate (which happened with `demo` on
    2026-11-11, breaking the one-command demonstration).
    """
    from cibles import is_bundled_target

    if is_bundled_target(target_name):
        return True
    return any(marker in target_name for marker in _LOCAL_MARKERS)


def _date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise MissingAuthorisation(
            f"Autorisation : '{field}' doit être une date AAAA-MM-JJ, "
            f"reçu {value!r}."
        ) from None


def load_authorisation(path=AUTHORISATION_FILE):
    """Reads the authorisation file, or says exactly what is missing."""
    path = Path(path)
    if not path.exists():
        raise MissingAuthorisation(
            f"Aucune autorisation trouvée ({path}).\n"
            f"  Copie autorisation.example.json, remplis-la, et relance.\n"
            f"  Tester un système tiers sans mandat écrit est un délit."
        )
    try:
        authorisation = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MissingAuthorisation(
            f"{path} n'est pas du JSON valide : {error}") from error

    missing = [f for f in REQUIRED_FIELDS if not authorisation.get(f)]
    if missing:
        raise MissingAuthorisation(
            f"{path} : champ(s) manquant(s) — {', '.join(missing)}.")
    return authorisation


def check_scope(authorisation, target_name, today=None):
    """
    Checks that the mandate REALLY covers this target, today.

    The two checks that matter: a mandate for one target is not valid for
    another, and an expired mandate is worth nothing. Without them, the file
    would be no more than a tick box.
    """
    today = today or date.today()

    scope = authorisation["target"]
    if scope not in target_name:
        raise MissingAuthorisation(
            f"L'autorisation couvre '{scope}', or la campagne vise "
            f"'{target_name}'.\n"
            f"  Un mandat pour une cible ne vaut pas pour une autre."
        )

    start = _date(authorisation["start"], "start")
    end = _date(authorisation["end"], "end")
    if not start <= today <= end:
        raise MissingAuthorisation(
            f"L'autorisation court du {start} au {end}, or nous sommes le "
            f"{today}.\n"
            f"  Tester hors de la fenêtre convenue n'est pas couvert."
        )
    return authorisation


def require_mandate(target_name, path=AUTHORISATION_FILE):
    """
    Returns the mandate covering `target_name`, or None if the target is
    local.

    This is the campaign's front door: it raises rather than letting an
    uncovered attack go out.
    """
    if is_local(target_name):
        return None
    return check_scope(load_authorisation(path), target_name)


# --- Chain of custody (OWASP manual §7.3) ------------------------------------
# "Tag each artifact with a unique Case ID […]. Calculate a SHA-256 hash of
# raw evidence at collection."
#
# What these digests do, and what they do not: they let us show that a trail
# was not retouched between its production and its delivery, and cite a piece
# of evidence by its digest without copying a client's verbatim reply. They do
# NOT constitute write-once retention — the manual requires that too, and it
# is a matter of infrastructure, not of code.

def digest(content):
    """SHA-256 of a text, in hexadecimal."""
    if content is None:
        content = ""
    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()


def _case_id(target):
    """
    The case identifier: timestamped, readable, and stable for one campaign.

    Derived rather than random: an operator who sees "20261112-174500-demo"
    knows which campaign it is without cross-referencing anything. A UUID
    would be unique but mute.
    """
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", str(target)).strip("-").lower()[:40]
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{clean or 'target'}"


def verify_seal(path):
    """
    Has a sealed trail been modified since it was closed?

    Returns (intact, explanation). Useful on an engagement: if a report is
    contested, we must be able to show the trace has not moved.
    """
    path = Path(path)
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l]
    if not lines:
        return (False, "Piste vide.")

    try:
        # The seal hashes the trail's raw BYTES, so modernising the parsed
        # dict to find `digest` changes nothing about the hash: an older
        # sealed trail still verifies.
        from migration import modernise

        last = modernise(json.loads(lines[-1]))
    except json.JSONDecodeError:
        return (False, "Dernière ligne illisible : piste tronquée ou altérée.")

    if last.get("type") != "seal":
        return (False, "Piste non scellée : la campagne ne s'est pas "
                       "terminée proprement, ou le sceau a été retiré.")

    # The seal covers everything that precedes it, line breaks included.
    before_seal = "".join(line + "\n" for line in lines[:-1])
    computed = digest(before_seal)
    if computed == last.get("digest"):
        return (True, f"Piste intacte ({last.get('case_id', 'sans ID')}).")
    return (False, "Empreinte NON concordante : la piste a été modifiée "
                   "après sa clôture.")


class AuditTrail:
    """
    A replayable log of the exchanges with the target, written as it goes.

    We record what was sent to the CLIENT's system, not our internal calls to
    the judge: that is what must be showable if the campaign is contested. The
    model calls themselves are counted by `llm_client`.

    Each line is a self-contained JSON object (JSONL format): the file stays
    readable even if the campaign is interrupted halfway through.
    """

    def __init__(self, path, target, authorisation=None, context=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The unique case identifier the OWASP manual requires (§7.3, "Case
        # Identification"). Derived from the timestamp and the target, hence
        # reproducible and readable — not an opaque UUID you would have to
        # cross-reference with something else.
        self.case_id = _case_id(target)
        self._exchanges = 0
        self._file = self.path.open("a", encoding="utf-8")
        self._write({
            "type": "campaign_start",
            "case_id": self.case_id,
            "target": target,
            # None for a local target: we say so explicitly, rather than
            # letting it look like a mandate missing by oversight.
            "authorisation": authorisation or "cible locale, aucun mandat requis",
            # What we DO control of the test environment, and what we do not.
            # See `telemetry()`.
            "environment": context or {},
        })

    def _write(self, entry):
        entry = {"timestamp": datetime.now().isoformat(timespec="seconds"),
                 **entry}
        self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Flushed at once: a campaign that falls over must leave its trace.
        self._file.flush()

    def record_exchange(self, phase, sent, received, truncated=False):
        """
        One round trip with the target: reconnaissance, attack or replay.

        Every exchange carries the SHA-256 digest of what was sent and what
        was received (manual §7.3, "Integrity Hashing"). The content is logged
        right beside it, so the digest does not protect against an alteration
        of the whole file — the seal takes care of that. It serves something
        else: citing a piece of evidence in a report, or in an exchange with
        the client, without copying a verbatim reply.
        """
        self._exchanges += 1
        self._write({"type": "exchange", "phase": phase, "sent": sent,
                     "received": received, "truncated": truncated,
                     "sent_digest": digest(sent),
                     "received_digest": digest(received)})

    def record_verdict(self, attempt, verdict):
        self._write({"type": "verdict", "attempt": attempt,
                     "enfreint": verdict["reussi"],
                     "critere": verdict["critere"],
                     "votes": verdict.get("votes")})

    def close(self, status, log):
        """
        Closes the trail and SEALS it.

        The final digest covers everything that precedes it: it lets us show
        that a trail produced on an engagement was not retouched afterwards.
        It is computed before being written, so it does not include itself —
        otherwise the seal would be impossible to verify.
        """
        self._write({"type": "campaign_end", "status": status,
                     "calls": log.get("calls"),
                     "tokens": log.get("tokens"),
                     "exchanges_logged": self._exchanges})
        self._file.flush()
        seal = digest(self.path.read_text(encoding="utf-8"))
        self._write({"type": "seal", "case_id": self.case_id,
                     "algorithm": "sha256", "digest": seal})
        self._file.close()
        return seal

    def trace(self, phase, ask_target):
        """
        Wraps a target so every exchange is recorded.

        The target stays a `message -> str` function: the agents that receive
        it do not even know it is being traced.
        """
        def ask(message):
            reply = ask_target(message)
            self.record_exchange(phase, message, reply)
            return reply
        return ask


# --- Telemetry: what we control, and what we do not --------------------------
# Manual §7.3, "Runtime & Environment Telemetry": model name, version,
# provider, endpoint, generation parameters, context state… and then, the
# sentence that matters for us:
#
#     "Residual Non-Determinism: If sampling parameters or backend routing
#     cannot be locked, explicitly note the potential for variance during
#     replay."
#
# A black-box red teamer knows NOTHING of their target's configuration:
# neither its model, nor its temperature, nor its system prompt — that is
# precisely what they are looking for. Claiming to record it would be
# inventing. So we record what we know (our own side, and what we sent), and
# we DECLARE what we do not, because unexplained variance on replay would
# otherwise read as a defect of the measurement.

def telemetry(target_name, target_profile=None):
    """The test environment, known side and unknown side."""
    from agents.arbitre import VOTE_COUNT
    from agents.verificateur import REPLAY_COUNT
    from config import ACTIVE_PROFILE, JUDGE_PROFILE, PROFILES

    judge = PROFILES.get(JUDGE_PROFILE, {})
    return {
        # What WE run: entirely known, hence entirely recorded.
        "our_models": {
            "judge": {
                "profile": JUDGE_PROFILE,
                "model": judge.get("model"),
                "base_url": judge.get("base_url"),
                "temperature": 0,
                "votes_per_verdict": VOTE_COUNT,
            },
            "active_profile": ACTIVE_PROFILE,
        },
        "target": {
            "name": target_name,
            "http_profile": target_profile,
            # The target's generation parameters are OUT of our reach in a
            # black-box test. Saying so is information; omitting it would
            # suggest we had pinned them.
            "generation_parameters": "inconnus (test en boîte noire)",
        },
        "residual_non_determinism": [
            "La cible choisit ses propres paramètres d'échantillonnage : deux "
            "campagnes identiques peuvent donner des verdicts différents.",
            "L'arbitre lui-même n'est pas déterministe à température 0 "
            f"(mesuré) : d'où {VOTE_COUNT} votes par verdict.",
            f"Une divulgation est rejouée {REPLAY_COUNT} fois, ce qui mesure la "
            "reproductibilité sans l'éliminer.",
        ],
    }
