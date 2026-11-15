"""
targets/ — The systems under test, and the choice between them.

The target used to be hard-coded: the tool could only test itself. Each target
is now an ADAPTER, and they all honour the same deliberately minimal contract:

    interroger(message: str) -> str

That contract is what lets `reconnaissance.py` and `verifier.py` receive
the target as a parameter, and lets tests use simulated targets in a few lines.

Four adapters:
- `demo`   : deliberately badly protected, with three defence levels. It gives
  in FOR REAL, and serves as much for the demonstration as for measuring how
  far the tool can go.
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
NAMED_TARGETS = {
    "decoy": ask_decoy,
    "leurre": ask_decoy,
    "mock": ask_mock,
}

# What `--target` offers, with the kept-for-compatibility names left out: a
# help text that listed both would suggest two different targets.
PUBLIC_TARGET_NAMES = ("decoy", "mock")


def is_bundled_target(name):
    """
    True if `name` denotes a target shipped with the project.

    These targets run locally and hold nothing but fictional secrets:
    `audit.py` uses this to require a mandate only against a third party.
    """
    return name in NAMED_TARGETS or name == "demo" or name.startswith("demo:")


def choose_target(name=None, profile=None):
    """
    Return the asking function matching `name`.

    - a known name ("decoy", "mock");
    - "demo", or "demo:N" to pick the defence level (1, 2 or 3);
    - a URL (http:// or https://) → the HTTP adapter configured from `.env`,
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
    if profile and not name.startswith(("http://", "https://")):
        raise ValueError(
            f'The target profile "{profile}" describes the shape of an '
            f"http(s) API; the target '{name}' ships with the project and "
            f"has nothing to configure.")

    if name in NAMED_TARGETS:
        return NAMED_TARGETS[name]

    # The demo target carries its level in its name: "demo:3". No new
    # command-line option for a setting that concerns one target out of four.
    if name == "demo" or name.startswith("demo:"):
        _, _, level = name.partition(":")
        try:
            return build_demo_target(int(level) if level else 1)
        except ValueError as error:
            raise ValueError(
                f"Invalid demo level in '{name}': {error}\n"
                f"  Expected: demo, or demo:N with N in "
                f"{{{', '.join(str(n) for n in LEVELS)}}}."
            ) from error

    if name.startswith(("http://", "https://")):
        return build_http_target(name, profile=profile)

    raise ValueError(
        f"Unknown target: '{name}'. Expected: "
        f"{', '.join(PUBLIC_TARGET_NAMES)}, demo[:N], or an http(s) URL."
    )
