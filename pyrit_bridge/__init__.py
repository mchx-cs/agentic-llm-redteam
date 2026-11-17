"""
pyrit_bridge — PyRIT's multi-turn attacks, driven through this project's own
points of passage (phase 3b).

WHY A BRIDGE AND NOT A DEPENDENCY
---------------------------------
PyRIT calls models through ITS targets, so outside `ask_llm()` — the one place
this project counts calls and tokens, and therefore the one place the budget
circuit breaker lives. Letting PyRIT reach a model directly would disarm phase
11 at the precise moment it becomes necessary, because multi-turn is the case
where cost grows QUADRATICALLY: every turn carries the whole history forward.

So the bridge is not a convenience layer. It exists to keep three rules that
the project would otherwise lose:

  1. `ask_llm()` stays the only road to a model, so `CALL_BUDGET` and
     `TOKEN_BUDGET` still bite and `BudgetExceeded` still stops a runaway;
  2. the JUDGE stays the oracle, judged on the format it was MEASURED on —
     `targets/conversation.render`, not PyRIT's transcript rendering;
  3. a verdict the judge could not reach stays a MISSING MEASUREMENT and
     never becomes "the target resisted".

WHAT IS OPTIONAL AND WHAT IS NOT
--------------------------------
PyRIT is an extra (`requirements-pyrit.txt`). It requires Python >= 3.11 since
its 1.2.0, while this project supports 3.10 and tests it in continuous
integration — so on 3.10 none of this is importable, and that is accepted
rather than worked around. Importing this package without PyRIT installed
raises with the command to run, never a bare `ModuleNotFoundError`.

`pyrit_bridge.convert` is the exception and imports nothing from PyRIT: every
decision that can be made on plain data lives there, so that the parts worth
testing ARE tested, in an environment that has no PyRIT at all.

VERIFIED AGAINST THE INSTALLED PACKAGE, 1.2.1, on 2026-11-17 — not against
the documentation, which described 1.1.0 and was already stale. Two facts had
moved in four days: `TargetConfiguration` now takes a `TargetCapabilities`
object instead of keyword flags, and `PAIRAttack` exists as its own export
rather than being TAP's single-branch case. One fact recorded as a risk turned
out not to be one: a user-written scorer DOES have a documented-by-code
contract, `TrueFalseScorer` needing `_build_identifier` and
`_score_scorable_async`.

That is the integration's standing cost, and it is why it is pinned to
`>=1.2.1,<1.3`: these three facts must be re-checked on every minor release.
"""

# The floor this bridge was written against. Pinned in requirements-pyrit.txt
# too; named here so the error message can say it.
REQUIRED = "1.2.1"

_INSTALL = (
    "PyRIT is not installed, and it is an optional extra.\n"
    "\n"
    "  py -3.11 -m venv .venv-pyrit\n"
    "  .venv-pyrit/Scripts/python -m pip install -r requirements-pyrit.txt\n"
    "\n"
    "It needs Python >= 3.11 (since PyRIT 1.2.0), where this project supports "
    "3.10. Multi-turn via PyRIT is simply unavailable on 3.10 — a single-turn "
    "campaign still works everywhere: python main.py --target demo")


def require_pyrit():
    """
    Import PyRIT, or raise with the command to run.

    A bare `ModuleNotFoundError: No module named 'pyrit'` tells a reader
    nothing about an extra they were never told existed. The same choice as
    the authorisation guard, which exits with "copy
    authorisation.example.json…" rather than a traceback.
    """
    try:
        import pyrit
    except ModuleNotFoundError as absent:
        raise RuntimeError(_INSTALL) from absent

    version = getattr(pyrit, "__version__", None)
    if version and version < REQUIRED:
        # A warning, not a refusal: a version comparison on strings is crude,
        # and refusing to run on a package that might work would be worse
        # than saying so. The same principle as the garak snapshot's age —
        # flagged, never blocking.
        print(f"/!\\ PyRIT {version} installed, bridge written against "
              f"{REQUIRED}. Three API facts must be re-checked: "
              f"TargetConfiguration, the PromptTarget hook, and the "
              f"TrueFalseScorer contract. See pyrit_bridge/__init__.py.")
    return pyrit
