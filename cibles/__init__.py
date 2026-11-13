"""
cibles/ — The systems under test, and the choice between them.

The target used to be hard-coded: the tool could only test itself. Each target
is now an ADAPTER, and they all honour the same deliberately minimal contract:

    interroger(message: str) -> str

That contract is what lets `reconnaissance.py` and `verificateur.py` receive
the target as a parameter, and lets tests use simulated targets in a few lines.

Four adapters:
- `demo`   : deliberately badly protected, with three defence levels. It gives
  in FOR REAL, and serves as much for the demonstration as for measuring how
  far the tool can go.
- `leurre` : the local toy chatbot, with a fictional secret to protect. It is
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

from cibles.demo import LEVELS, build_demo_target
from cibles.http import build_http_target
from cibles.leurre import ask_decoy
from cibles.mock import ask_mock

# The targets that need no configuration: chosen by name.
NAMED_TARGETS = {
    "leurre": ask_decoy,
    "mock": ask_mock,
}


def is_bundled_target(name):
    """
    True if `name` denotes a target shipped with the project.

    These targets run locally and hold nothing but fictional secrets:
    `audit.py` uses this to require a mandate only against a third party.
    """
    return name in NAMED_TARGETS or name == "demo" or name.startswith("demo:")


def choose_target(name=None, profil=None):
    """
    Return the asking function matching `name`.

    - a known name ("leurre", "mock");
    - "demo", or "demo:N" to pick the defence level (1, 2 or 3);
    - a URL (http:// or https://) → the HTTP adapter configured from `.env`,
      or from `profil` (see cibles.http.PROFILS_CIBLE) for a known API shape:
      describing the JSON body by hand is the most tedious part of wiring a
      target, and for the common case it is entirely predictable;
    - None → the value of CIBLE in `.env`, otherwise the local decoy.
    """
    from config import CIBLE  # imported here to avoid a circular import

    name = name or CIBLE

    # FIRST, before any branch: a profile only applies to an HTTP target.
    # Placed lower down, this check was unreachable — the named targets return
    # before it — and the profile was silently ignored, exactly what it was
    # meant to prevent. A test showed it.
    if profil and not name.startswith(("http://", "https://")):
        raise ValueError(
            f"Le profil de cible « {profil} » décrit la forme d'une API "
            f"http(s) ; la cible '{name}' est livrée avec le projet et n'a "
            f"rien à configurer.")

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
                f"Niveau de démonstration invalide dans '{name}' : {error}\n"
                f"  Attendu : demo, ou demo:N avec N dans "
                f"{{{', '.join(str(n) for n in LEVELS)}}}."
            ) from error

    if name.startswith(("http://", "https://")):
        return build_http_target(name, profil=profil)

    raise ValueError(
        f"Cible inconnue : '{name}'. Attendu : "
        f"{', '.join(NAMED_TARGETS)}, demo[:N], ou une URL http(s)."
    )
