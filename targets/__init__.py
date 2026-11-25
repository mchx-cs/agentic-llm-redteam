"""
targets/ — The systems under test, and the choice between them.

The target used to be hard-coded: the tool could only test itself. Each target
is now an ADAPTER, and they all honour the same deliberately minimal contract:

    interroger(message: str) -> str

That contract is what lets `reconnaissance.py` and `verifier.py` receive
the target as a parameter, and lets tests use simulated targets in a few lines.

Six adapters, and the first three are one instrument each: they differ by the
ASSET they protect, because a different asset has a different defence and
mixing two into one target's levels would measure both at once.
- `demo`   : deliberately badly protected, with three defence levels. It gives
  in FOR REAL, and serves as much for the demonstration as for measuring how
  far the tool can go. What it protects is a SECRET STRING.
- `records`: the other half of what a deployed application actually is — an
  assistant over a reader DATABASE it has already read, with no tool at all.
  What it protects is THIRD-PARTY DATA, which is a different asset with a
  different defence, hence its own levels rather than three more on `demo`.
- `docs`   : an assistant over a document base READERS CAN WRITE INTO. What it
  protects is the INTEGRITY OF ITS OWN INSTRUCTIONS against an instruction
  found in retrieved content, so its levels vary the delimitation of that
  content while holding the secret rule firm at all three. It carries the same
  asset KINDS as `demo` on purpose — the variable under test is the SOURCE of
  the instruction and nothing else.
- `decoy`  : the local toy chatbot, with a fictional secret to protect. It is
  the default target, so the repository runs with no configuration.
- `mock`   : deterministic, with no LLM at all. Instant, free, always
  identical: it is what makes end-to-end tests possible.
- `http`   : a real endpoint, described in `.env`. This is the adapter that
  takes the tool from "it tests itself" to "it aims at a target".

A word on the "no direct call to an LLM provider" rule: it covers the models WE
use (judge, analyst, decoy), so they stay interchangeable from `config.py`. The
target is an arbitrary third-party system — often an application, not a bare
model — so the `http` adapter calls it directly. That is deliberate.
"""

from targets.demo import LEVELS, build_demo_target
from targets.records import LEVELS as RECORDS_LEVELS
from targets.records import build_records_target
from targets.docs import LEVELS as DOCS_LEVELS
from targets.docs import build_docs_target
from targets.http import build_http_target
from targets.decoy import ask_decoy
from targets.mock import ask_mock

# The targets that need no configuration: chosen by name.
#
# `leurre` is kept beside `decoy` the way the French command-line options are
# kept beside the English ones: the README has shown `--cible leurre` since
# the project existed, and a documented name does not get pulled from under
# its users by a translation. `is_bundled_target` therefore answers for both,
# which is what keeps the mandate guard from asking for an authorisation.
# The secrets come from the modules that DECLARE them, never restated here:
# the project's preference recorded for `stats.STATES`, `judge_identity()` and
# the attack catalogue. A second copy drifts on the first change.
from targets.demo import SECRET as demo_secret
from targets.docs import SECRET as docs_secret
from targets.mock import SECRET as mock_secret

NAMED_TARGETS = {
    "decoy": ask_decoy,
    "leurre": ask_decoy,
    "mock": ask_mock,
}

# What `--target` offers, with the kept-for-compatibility names left out: a
# help text that listed both would suggest two different targets.
PUBLIC_TARGET_NAMES = ("decoy", "mock")

# The targets that carry a defence level in their name, and the builder for
# each. A mapping rather than two branches: `is_bundled_target` and
# `choose_target` both have to answer for every one of them, and the project
# has already paid for that being two places -- the authorisation guard did
# not know about `demo` and REFUSED TO START, breaking the one-command
# demonstration. A test checks every named target is recognised as bundled.
LEVELLED_TARGETS = {
    "demo": (build_demo_target, LEVELS),
    "records": (build_records_target, RECORDS_LEVELS),
    "docs": (build_docs_target, DOCS_LEVELS),
}


#: The secret each BUNDLED target holds, read from the module that declares
#: it. `decoy` embeds its own in a prompt string rather than a constant, so it
#: is named here; the day it gains a `SECRET` this should read it instead.
#:
#: Absent on purpose for `records` (it protects records, not a value) and for
#: any URL: a third-party endpoint's secret is precisely what a black-box test
#: is trying to obtain, and pretending to know it would invert the premise.
SECRETS = {
    "decoy": "TOPSECRET42",
    "leurre": "TOPSECRET42",
    "mock": mock_secret,
    "demo": demo_secret,
    "docs": docs_secret,
}


def secret_of(name=None):
    """
    The fictional secret `name` holds, or None when it holds none.

    None is a REAL answer, not a missing one: `records` guards third-party
    records rather than a value, and against a real endpoint we do not know
    the secret — that is the whole premise of a blind test. The harvesters
    record what this returns, and `labelling_prepass` searches the replies
    for it, so a wrong value here produces a prepass that reports zero
    disclosures on a harvest full of them.
    """
    from config import TARGET      # imported here: circular at module level

    name = name or TARGET
    base = name.split(":", 1)[0]
    return SECRETS.get(base)


def is_bundled_target(name):
    """
    True if `name` denotes a target shipped with the project.

    These targets run locally and hold nothing but fictional secrets:
    `audit.py` uses this to require a mandate only against a third party.
    """
    return (name in NAMED_TARGETS
            or any(name == base or name.startswith(f"{base}:")
                   for base in LEVELLED_TARGETS))


#: The URL schemes a target name may carry. `ws://` and `wss://` arrived on
#: 2026-11-20 with the WebSocket transport.
#:
#: In ONE place because three separate gates were deciding "is this a URL?"
#: by looking for "http", and widening two of three is how a ws:// endpoint
#: ends up refused by `--probe-target` as "a bundled target, with nothing to
#: configure" -- blaming the operator for a gate we forgot. The same reason
#: the PyRIT bridge reads `stats.STATES` and `label.py` reads
#: `split_sets.imposed_set()` instead of restating them.
URL_SCHEMES = ("http://", "https://", "ws://", "wss://")


def is_url_target(name):
    """Is this target name an endpoint to configure, rather than a bundled one?"""
    return str(name).startswith(URL_SCHEMES)


def choose_target(name=None, profile=None, transport=None):
    """
    Return the asking function matching `name`.

    - a known name ("decoy", "mock");
    - "demo" or "records", with ":N" to pick the defence level (1, 2 or 3);
    - a URL (http(s):// or ws(s)://) → the HTTP adapter configured from `.env`,
      or from `profil` (see targets.http.TARGET_PROFILES) for a known API shape:
      describing the JSON body by hand is the most tedious part of wiring a
      target, and for the common case it is entirely predictable;
    - None → the value of TARGET in `.env`, otherwise the local decoy.
    """
    from config import TARGET  # imported here to avoid a circular import

    name = name or TARGET

    # FIRST, before any branch: a profile only applies to an HTTP target.
    # Placed lower down, this check was unreachable — the named targets return
    # before it — and the profile was silently ignored, exactly what it was
    # meant to prevent. A test showed it.
    if (profile or transport) and not is_url_target(name):
        said = f'profile "{profile}"' if profile else f'transport "{transport}"'
        raise ValueError(
            f"The target {said} describes how to reach an endpoint; the "
            f"target '{name}' ships with the project and has nothing to "
            f"configure.")

    if name in NAMED_TARGETS:
        return NAMED_TARGETS[name]

    # A levelled target carries its level in its name: "demo:3",
    # "records:2". No new command-line option for a setting that concerns two
    # targets out of five.
    base, _, level = name.partition(":")
    if base in LEVELLED_TARGETS:
        build, levels = LEVELLED_TARGETS[base]
        try:
            return build(int(level) if level else 1)
        except ValueError as error:
            raise ValueError(
                f"Invalid {base} level in '{name}': {error}\n"
                f"  Expected: {base}, or {base}:N with N in "
                f"{{{', '.join(str(n) for n in levels)}}}."
            ) from error

    if is_url_target(name):
        return build_http_target(name, profile=profile, transport=transport)

    raise ValueError(
        f"Unknown target: '{name}'. Expected: "
        f"{', '.join(PUBLIC_TARGET_NAMES)}, "
        f"{', '.join(f'{base}[:N]' for base in LEVELLED_TARGETS)}, "
        f"or a URL ({', '.join(URL_SCHEMES)})."
    )
