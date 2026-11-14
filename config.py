"""
config.py — The project's single switching point.

HERE, and nowhere else, is where we decide whether the models run locally
(Ollama) or through a remote API (OpenAI, Groq…). Moving from one to the
other = changing one PROFILE_* line below. The rest of the code does not even
know who it is talking to: that is the whole point.

Note on the names: the Python identifiers are English, the ENVIRONMENT
VARIABLE names are not yet. A `.env` key is a configuration contract — it
lives on machines this repository never sees — so renaming one needs a
deprecation path, and that is a pass of its own.
"""

import json
import os
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

PROFILES = {
    # --- LOCAL profile: Ollama, free, no key ---
    # Ollama exposes an OpenAI-shaped API on port 11434.
    "local": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",          # ignored by Ollama, but the SDK wants it
        "modele": "llama3.2",         # run `ollama pull llama3.2` first
    },

    # --- API profile: a remote provider (OpenAI as the example) ---
    # The key is read from an environment variable (never hard-coded).
    "api": {
        "base_url": "https://api.openai.com/v1",
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        # The model is read from the environment like the key: no name frozen
        # into the code, which would go stale as releases come out.
        "modele": os.environ.get("OPENAI_MODEL", ""),
        # As for groq: remote APIs cap throughput, the SDK waits the
        # announced delay then retries, at most this many times.
        "relances": 8,
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
        "modele": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        # The free tier caps tokens per minute: past that, the API answers
        # "retry in X ms". The SDK waits that delay then retries, at most this
        # many times (a bounded loop, never an infinite one).
        "relances": 8,
    },
}

# >>> THE TWO SWITCHES <<<
# Both are set in .env (outside git): nobody needs to edit a git-tracked file
# to change provider. "local" by default, so the repository runs with no key
# at all.

# The default profile: the TARGET's, and that of any call which does not name
# one. Careful: attacking a remote API would breach the provider's terms of
# use (see "Cadre légal" in CLAUDE.md). The target stays local.
ACTIVE_PROFILE = os.environ.get("PROFIL_ACTIF", "local")

# The JUDGE's profile (and the reconnaissance analyst's), kept separate so the
# judge can run on a different model from the target it judges — a judge
# identical to its target shares its blind spots.
JUDGE_PROFILE = os.environ.get("PROFIL_ARBITRE", "local")

_unknown_profiles = [name for name in (ACTIVE_PROFILE, JUDGE_PROFILE)
                     if name not in PROFILES]
if _unknown_profiles:
    # A typo in .env would otherwise give a bare KeyError, a long way from
    # here, on the first call to a model.
    raise ValueError(
        f"Profil inconnu dans .env : {', '.join(_unknown_profiles)}. "
        f"Profils disponibles : {', '.join(PROFILES)}."
    )


# >>> THE TARGET: WHICH SYSTEM WE TEST <<<
# "leurre" (default) = the local toy chatbot; "mock" = deterministic, no
# model; an http(s) URL = a real endpoint. Overridden by --cible on the
# command line (see cibles/__init__.py).
TARGET = os.environ.get("CIBLE", "leurre")


# >>> A CAMPAIGN'S BUDGET <<<
# A circuit breaker, not an economy: at the current scale a campaign costs
# pennies. What is dangerous is the loop that runs away — an adaptive agent
# with no guard, a replay inside a replay, a cascade of retries. The caps are
# therefore wide but FINITE. `0` or empty = no limit, to be used only in full
# knowledge of what that means.
def _int_from_env(name, default):
    value = int(os.environ.get(name, default))
    return value if value > 0 else None


CALL_BUDGET = _int_from_env("BUDGET_APPELS", 200)
TOKEN_BUDGET = _int_from_env("BUDGET_TOKENS", 500_000)


def _json_from_env(name, default):
    """Reads an environment variable holding JSON."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{name} dans .env n'est pas du JSON valide : {error}"
        ) from error


# Description of an HTTP target. Every application exposes a different shape:
# rather than guessing, we describe it here. The defaults match the simplest
# case, {"message": "..."} → {"reply": "..."}.
HTTP_TARGET = {
    # Headers, authentication included. Example in .env:
    #   CIBLE_ENTETES={"Authorization": "Bearer xxx"}
    "entetes": _json_from_env("CIBLE_ENTETES", {}),
    # Template of the body sent; "{message}" is replaced by the payload.
    #   CIBLE_CORPS={"messages":[{"role":"user","content":"{message}"}]}
    "corps": _json_from_env("CIBLE_CORPS", {"message": "{message}"}),
    # Where to read the text in the JSON reply, as a dotted path.
    #   CIBLE_CHEMIN_REPONSE=choices.0.message.content
    "chemin_reponse": os.environ.get("CIBLE_CHEMIN_REPONSE", "reply"),
    # Without a timeout, a silent target would block the campaign for ever.
    "delai": float(os.environ.get("CIBLE_DELAI", "60")),
}
