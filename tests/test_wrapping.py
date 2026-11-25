"""
Tests for carrying a target's DECLARED capabilities through a wrapper.

Three wrappers in this project lost one, and the third within hours of the
second (see `targets/wrapping.py`). So the last class here is a SWEEP and not
a list: a wrapper that declares a capability BY HAND is exactly the shape
that failed, it is syntactically identifiable, and a list somebody must
remember to extend is the defect rather than the fix — the lesson the
entry-point sweep and the `py-modules` sweep already paid for.
"""

import ast
import pathlib

import pytest

from targets.conversation import supports_conversation
from targets.indirect import supports_indirect
from targets.wrapping import carry_capabilities

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _plantable():
    def ask(message, history=None):
        return "ok"
    ask.conversation = True
    ask.indirect = True
    ask.plant = lambda note: note
    ask.planted = lambda: None
    return ask


def _plain():
    def ask(message, history=None):
        return "ok"
    return ask


def _wrapper(target):
    def ask(message, history=None):
        return target(message, history=history) if history else target(message)
    return ask


class TestItCOPIESWhatTheTargetDeclares:
    def test_the_conversation_capability(self):
        wrapped = carry_capabilities(_wrapper(_plantable()), _plantable())
        assert supports_conversation(wrapped)

    def test_the_indirect_channel(self):
        target = _plantable()
        wrapped = carry_capabilities(_wrapper(target), target)
        assert supports_indirect(wrapped)

    def test_the_plant_FORWARDS_to_the_original(self):
        seen = []
        target = _plantable()
        target.plant = lambda note: seen.append(note) or note
        wrapped = carry_capabilities(_wrapper(target), target)
        wrapped.plant("une note")
        assert seen == ["une note"]

    def test_a_caller_may_supply_its_OWN_plant(self):
        # The audit trail needs to RECORD the plant, not merely forward it.
        recorded = []
        target = _plantable()
        wrapped = carry_capabilities(
            _wrapper(target), target,
            plant=lambda note: recorded.append(note) or note)
        wrapped.plant("une note")
        assert recorded == ["une note"]

    def test_the_wrapper_is_RETURNED_so_it_can_be_used_inline(self):
        target = _plantable()
        wrapper = _wrapper(target)
        assert carry_capabilities(wrapper, target) is wrapper


class TestItNeverINVENTSOne:
    """
    Silence means refusal, never permission — the rule both capability
    modules state. A wrapper that declared what its target does not would be
    the defect wearing the other face.
    """

    def test_a_plain_target_stays_single_turn(self):
        assert not supports_conversation(
            carry_capabilities(_wrapper(_plain()), _plain()))

    def test_a_plain_target_gets_no_channel(self):
        wrapped = carry_capabilities(_wrapper(_plain()), _plain())
        assert not supports_indirect(wrapped)
        assert not hasattr(wrapped, "plant")

    def test_a_supplied_plant_does_not_CREATE_a_channel(self):
        # Passing a plant for a target that has none must not conjure the
        # capability: there would be nothing to plant INTO.
        wrapped = carry_capabilities(_wrapper(_plain()), _plain(),
                                     plant=lambda note: note)
        assert not supports_indirect(wrapped)

    def test_a_target_declaring_the_flag_WITHOUT_a_plant_gets_neither(self):
        half = _plain()
        half.indirect = True
        assert not supports_indirect(carry_capabilities(_wrapper(half), half))


class TestTheTHREEWrappersCarryThem:
    """
    Driven, never read from source: two modules whose imports look right are
    the junction defect this project meets most often.
    """

    def test_the_audit_trail_wrapper(self, tmp_path):
        from audit import AuditTrail
        trail = AuditTrail(tmp_path / "t.jsonl", "docs")
        traced = trail.trace("attaque", _plantable())
        assert supports_conversation(traced)
        assert supports_indirect(traced)

    def test_the_request_counter(self):
        from evaluation.measure_modes import counting
        counted, _ = counting(_plantable())
        assert supports_conversation(counted)
        assert supports_indirect(counted), (
            "this is the omission that killed the delivery measurement at "
            "pair 1: the channel was checked on the RAW target, then the "
            "target was wrapped, and the campaign refused the wrapper")

    def test_the_replanting_wrapper(self):
        import main
        replanting = main._replanting(_plantable(), "une note")
        assert supports_conversation(replanting)
        assert supports_indirect(replanting)

    def test_and_a_PLAIN_target_survives_all_three_unchanged(self, tmp_path):
        # The contrast: without it the three above could pass on a helper
        # that set every flag to True.
        from audit import AuditTrail
        from evaluation.measure_modes import counting
        trail = AuditTrail(tmp_path / "t.jsonl", "mock")
        counted, _ = counting(_plain())
        for wrapped in (trail.trace("attaque", _plain()), counted):
            assert not supports_conversation(wrapped)
            assert not supports_indirect(wrapped)


class TestNoWrapperDeclaresACapabilityBYHAND:
    """
    THE SWEEP. A capability assigned by hand outside the modules that own one
    is a wrapper re-implementing `carry_capabilities` — which is how the same
    omission happened three times.

    Target adapters DECLARE their own, so they are the exception and it is
    derived from the package rather than listed: a sixth adapter is covered
    the day it lands.
    """

    #: Where declaring a capability by hand is the module's JOB.
    OWNERS = {"targets/wrapping.py"}

    def _assignments(self):
        found = []
        for path in sorted(ROOT.rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith((".venv", "tests/")):
                continue
            # Every target adapter declares its own capabilities; that is
            # what "declared, not guessed" means.
            if relative.startswith("targets/") or relative in self.OWNERS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for goal in node.targets:
                    if (isinstance(goal, ast.Attribute)
                            and goal.attr in ("conversation", "indirect",
                                              "plant")):
                        found.append(f"{relative}:{node.lineno} "
                                     f"sets .{goal.attr}")
        return found

    def test_nothing_outside_the_owners_sets_one(self):
        assert self._assignments() == [], (
            "a wrapper declares a capability by hand instead of calling "
            "`carry_capabilities`:\n  " + "\n  ".join(self._assignments())
            + "\nThat is the omission that happened three times — see "
              "targets/wrapping.py.")

    def test_the_sweep_would_SEE_one(self):
        # Without this the test above could be passing on an empty scan, the
        # tautology this project has met five times in its guards.
        probe = ROOT / "evaluation" / "_sweep_probe.py"
        probe.write_text("def f(ask):\n    ask.plant = None\n    return ask\n",
                         encoding="utf-8")
        try:
            assert any("_sweep_probe" in found for found in self._assignments())
        finally:
            probe.unlink()
