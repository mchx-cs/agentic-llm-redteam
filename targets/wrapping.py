"""
targets/wrapping.py — carrying a target's DECLARED capabilities through a
wrapper.

WHY THIS EXISTS, and it is three failures and not a hypothesis. A target is a
function, and this project wraps it for several good reasons: to trace every
exchange (`AuditTrail.trace`), to count requests (`measure_modes.counting`),
to re-plant a note before each replay (`main._replanting`). Each wrapper is a
NEW function, so each one silently loses whatever the original DECLARED:

- 2026-11-17, `AuditTrail.trace`: it wrapped `ask(message)` and dropped the
  history, so an orchestrator believed it was holding a dialogue while the
  target saw isolated messages. The capability flag had to be copied too;
- 2026-11-25, the same wrapper again, with the indirect channel: `plant` was
  not copied, so a replay would have planted nothing — and the replay is the
  only path by which an indirect finding reaches `high`;
- 2026-11-25, `measure_modes.counting`: the measurement checked the channel
  on the RAW target, then wrapped it, and the campaign refused the wrapper.
  That one failed LOUDLY, because `require_indirect` runs inside
  `run_campaign` and the guard caught the wrapper rather than the original.

Three wrappers, three times the same omission, the third within hours of the
second. So the copying lives in ONE place, and the next wrapper is correct by
default instead of by memory — the preference already recorded for
`stats.STATES`, `judge_identity()` and `split_sets.imposed_set()`.

WHAT IT DOES NOT DO: invent a capability. A wrapper of a target that cannot
converse still cannot, and one around a target with no channel still has
none. Silence means refusal, never permission — the rule both capability
modules state, and the reason this function reads the ORIGINAL rather than
setting flags to True.
"""

from targets.conversation import supports_conversation
from targets.indirect import supports_indirect


def carry_capabilities(wrapper, target, plant=None):
    """
    Declare on `wrapper` what `target` declares, and return `wrapper`.

    `plant` lets a caller supply its own planting function — the audit trail
    needs to RECORD the plant, not merely forward it. Omitted, the original's
    is forwarded unchanged.

    Returns the wrapper so it can be used inline:

        return carry_capabilities(ask, ask_target)
    """
    wrapper.conversation = supports_conversation(target)

    if supports_indirect(target):
        wrapper.indirect = True
        wrapper.plant = plant if plant is not None else target.plant
        # Forwarded when the original has it: a reader-back is how a test and
        # a trail check WHAT is currently planted.
        if hasattr(target, "planted"):
            wrapper.planted = target.planted
    return wrapper
