"""
config.py — The project's single switching point.

HERE, and nowhere else, is where we decide whether the models run locally
(Ollama) or through a remote API (OpenAI, Groq…). Moving from one to the
other = changing one PROFILE_* line below. The rest of the code does not even
know who it is talking to: that is the whole point.

Note on the names: a `.env` key is a configuration CONTRACT. It lives on
machines this repository never sees, and nothing in git can migrate them. So
each one is read under its English name FIRST and under the French name it
carried until 2026-11-15 as a fallback: an existing `.env` keeps working, and
says once on stderr which lines to rename. See `LEGACY_ENV` below.
"""

import json
import os
import sys
from pathlib import Path


def _load_env_file():
    """
    Reads the .env file at the project root, if it exists, and puts its
    variables into the environment.

    Why a .env file: the API key goes straight from the provider's console to
    that file, without passing through a terminal, a chat or the code. It is
    listed in .gitignore: it never leaves for GitHub.

    A variable already set in the environment wins: the file only ever
    supplies a default.
    """
    path = Path(__file__).parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


# To be done BEFORE building the profiles, which read the environment.
_load_env_file()


# >>> THE DEPRECATION PATH FOR THE KEY NAMES <<<
# Keys the project renamed when it switched to English, new name -> old name.
# The provider keys (OPENAI_API_KEY, GROQ_MODEL…) are not here: they were
# never French, and two of them follow each provider's own convention.
LEGACY_ENV = {
    "TARGET": "CIBLE",
    "TARGET_HEADERS": "CIBLE_ENTETES",
    "TARGET_BODY": "CIBLE_CORPS",
    "TARGET_RESPONSE_PATH": "CIBLE_CHEMIN_REPONSE",
    "TARGET_TIMEOUT": "CIBLE_DELAI",
    "ACTIVE_PROFILE": "PROFIL_ACTIF",
    "JUDGE_PROFILE": "PROFIL_ARBITRE",
    "CALL_BUDGET": "BUDGET_APPELS",
    "TOKEN_BUDGET": "BUDGET_TOKENS",
}

# Filled while the module body reads the environment, reported once at the end.
# A list, not a print on the spot: nine separate warnings for one stale .env
# would bury the campaign's own first lines.
_legacy_in_use = []


def _from_env(name, default=None):
    """
    Reads a configuration key, falling back to the French name it had before.

    The new name WINS when both are set. Anything else would be surprising:
    someone who adds the new line to an old `.env` means it to take effect,
    and the stale line is exactly what they are in the middle of replacing.
    """
    if name in os.environ:
        return os.environ[name]
    old = LEGACY_ENV.get(name)
    if old and old in os.environ:
        _legacy_in_use.append((old, name))
        return os.environ[old]
    return default


PROFILES = {
    # --- LOCAL profile: Ollama, free, no key ---
    # Ollama exposes an OpenAI-shaped API on port 11434.
    "local": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",          # ignored by Ollama, but the SDK wants it
        "model": "llama3.2",         # run `ollama pull llama3.2` first
    },

    # --- API profile: a remote provider (OpenAI as the example) ---
    # The key is read from an environment variable (never hard-coded).
    "api": {
        "base_url": "https://api.openai.com/v1",
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        # The model is read from the environment like the key: no name frozen
        # into the code, which would go stale as releases come out.
        "model": os.environ.get("OPENAI_MODEL", ""),
        # As for groq: remote APIs cap throughput, the SDK waits the
        # announced delay then retries, at most this many times.
        "retries": 8,
    },

    # --- GROQ profile: a remote API with a free tier ---
    # Used for the JUDGE only, and only on fictional data. Never as the target
    # of real attacks: providers' terms of use forbid getting around their
    # guardrails (see "Cadre légal" in CLAUDE.md).
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        # A model from a different family than the target (llama3.2): a judge
        # that is not the same model does not share its blind spots (Phase 4).
        # Replaceable through GROQ_MODEL, without touching the code.
        "model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        # The free tier caps tokens per minute: past that, the API answers
        # "retry in X ms". The SDK waits that delay then retries, at most this
        # many times (a bounded loop, never an infinite one).
        "retries": 8,
    },
}

# >>> THE TWO SWITCHES <<<
# Both are set in .env (outside git): nobody needs to edit a git-tracked file
# to change provider. "local" by default, so the repository runs with no key
# at all.

# The default profile: the TARGET's, and that of any call which does not name
# one. Careful: attacking a remote API would breach the provider's terms of
# use (see "Cadre légal" in CLAUDE.md). The target stays local.
ACTIVE_PROFILE = _from_env("ACTIVE_PROFILE", "local")

# The JUDGE's profile (and the reconnaissance analyst's), kept separate so the
# judge can run on a different model from the target it judges — a judge
# identical to its target shares its blind spots.
JUDGE_PROFILE = _from_env("JUDGE_PROFILE", "local")

_unknown_profiles = [name for name in (ACTIVE_PROFILE, JUDGE_PROFILE)
                     if name not in PROFILES]
if _unknown_profiles:
    # A typo in .env would otherwise give a bare KeyError, a long way from
    # here, on the first call to a model.
    raise ValueError(
        f"Unknown profile in .env: {', '.join(_unknown_profiles)}. "
        f"Available profiles: {', '.join(PROFILES)}."
    )


# >>> THE TARGET: WHICH SYSTEM WE TEST <<<
# "decoy" (default) = the local toy chatbot; "mock" = deterministic, no
# model; an http(s) URL = a real endpoint. Overridden by --cible on the
# command line (see targets/__init__.py).
TARGET = _from_env("TARGET", "decoy")


# >>> A CAMPAIGN'S BUDGET <<<
# A circuit breaker, not an economy: at the current scale a campaign costs
# pennies. What is dangerous is the loop that runs away — an adaptive agent
# with no guard, a replay inside a replay, a cascade of retries. The caps are
# therefore wide but FINITE. `0` or empty = no limit, to be used only in full
# knowledge of what that means.
def _int_from_env(name, default):
    value = int(_from_env(name, default))
    return value if value > 0 else None


CALL_BUDGET = _int_from_env("CALL_BUDGET", 200)
TOKEN_BUDGET = _int_from_env("TOKEN_BUDGET", 500_000)


def _json_from_env(name, default):
    """Reads an environment variable holding JSON."""
    raw = _from_env(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{name} in .env is not valid JSON: {error}"
        ) from error


# Description of an HTTP target. Every application exposes a different shape:
# rather than guessing, we describe it here. The defaults match the simplest
# case, {"message": "..."} → {"reply": "..."}.
HTTP_TARGET = {
    # Headers, authentication included. Example in .env:
    #   TARGET_HEADERS={"Authorization": "Bearer xxx"}
    "headers": _json_from_env("TARGET_HEADERS", {}),
    # Template of the body sent; "{message}" is replaced by the payload.
    #   TARGET_BODY={"messages":[{"role":"user","content":"{message}"}]}
    "body": _json_from_env("TARGET_BODY", {"message": "{message}"}),
    # Where to read the text in the JSON reply, as a dotted path.
    #   TARGET_RESPONSE_PATH=choices.0.message.content
    "response_path": _from_env("TARGET_RESPONSE_PATH", "reply"),
    # Without a timeout, a silent target would block the campaign for ever.
    "timeout": float(_from_env("TARGET_TIMEOUT", "60")),
}


# Said ONCE, after every key has been read, and on stderr — a note about the
# configuration has no business in a report that gets piped to a file.
if _legacy_in_use:
    print(
        "Note: your .env still uses the key name(s) this project carried "
        "before it switched to English. They keep working; rename them when "
        "convenient:",
        file=sys.stderr)
    for old, new in _legacy_in_use:
        print(f"  {old} -> {new}", file=sys.stderr)
