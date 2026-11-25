"""
Which piece gave up, and what the campaign does about it.

THE DEFECT CLASS, and it has two halves that are easy to confuse:

1. MISATTRIBUTION. Our judge failing is not the target failing. Until
   2026-11-23 a judge that gave up propagated out of the single-turn
   campaign, and the orchestrator's generic handler announced "the target did
   not answer as expected" and advised `--probe-target` — at a deterministic
   `mock` target that had answered perfectly. Wrong advice costs more than no
   advice: it sends the operator to check a thing that is not broken. The
   multi-turn path was given this on 2026-11-17 (`_component` in
   `pyrit_bridge/campaign.py`) and the DEFAULT path never had it.

2. A MISSING MEASUREMENT CREDITED TO THE DEFENCE. No oracle ruled, so the
   attempt leaves the ASR denominator — the conflation measured on
   2026-11-12, which moved an ASR seventeen points in the target's favour.
   And the same rule has to reach the campaign's STATUS, because `no_finding`
   is what a target that genuinely held three times also gets.

No model is called here: `judge_by_vote` and the target are both replaced.
"""

import contextlib
import io

import pytest

import main
from llm_client import BudgetExceeded

PROFILE = {"role": "a librarian", "language": "fr", "tools": [],
           "refused_subjects": ["the code"], "mentions_instructions": True,
           "writes_code": None, "handles_documents": None,
           "context": [], "evidence": [], "exchanges": [], "warning": None}


def _campaign(monkeypatch, judge, attempts=2, target=lambda m: "Je refuse.",
              replay=None):
    """A real `run_campaign`, with the model calls replaced."""
    # `**_` and not `(ask)`: `main` passes `language=` since
    # 2026-11-25, and a double that does not match the real
    # signature hides exactly that kind of change.
    monkeypatch.setattr(main, "reconnoitre",
                        lambda ask, **_: dict(PROFILE))
    monkeypatch.setattr(main, "MAX_ATTEMPTS", attempts)
    monkeypatch.setattr(main, "judge_by_vote", judge)
    if replay is not None:
        monkeypatch.setattr(main, "verify_by_replay", replay)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = main.run_campaign(target, "mock")
    return result, out.getvalue()


def _verdict(**fields):
    verdict = {"reussi": False, "critere": "aucun", "analyse": "x",
               "valeur": None, "votes": [False] * 3, "brut": ""}
    verdict.update(fields)
    return verdict


class TestAJudgeThatGivesUp:
    def test_the_campaign_CARRIES_ON(self, monkeypatch):
        # One failed verdict out of a budget has no business ending a run
        # halfway through -- the same decision as an undeliverable payload,
        # and as an attacker model that gives up mid-attempt.
        def refuse(payload, reply):
            raise RuntimeError("400 Failed to generate JSON")
        result, _ = _campaign(monkeypatch, refuse, attempts=3)
        assert len(result["launched"]) == 3, (
            "a judge that gave up must not cost the remaining attempts")

    def test_it_is_NOT_counted_as_a_resistance(self, monkeypatch):
        """
        `judge_undecided`, so the attempt leaves the ASR denominator. Counting
        it as a resistance is the seventeen-point error measured on
        2026-11-12: a missing measurement credited to the defence.
        """
        from stats import is_scorable

        def refuse(payload, reply):
            raise RuntimeError("provider down")
        result, _ = _campaign(monkeypatch, refuse)
        assert set(result["states"]) == {"judge_undecided"}
        assert not any(is_scorable(state) for state in result["states"])

    def test_and_the_TARGET_is_not_blamed(self, monkeypatch):
        """
        The attribution is POSITIONAL, not inferred, and that is strictly
        better than the multi-turn version: PyRIT hides the call, so
        `_component` has to read a component's name out of an error message,
        while this line calls our judge and nothing else.
        """
        def refuse(payload, reply):
            raise RuntimeError("the judge is unreachable")
        _, printed = _campaign(monkeypatch, refuse)
        assert "our judge GAVE UP" in printed
        assert "probe-target" not in printed, (
            "the target answered; sending the operator to check its wiring "
            "is the misattribution this guard exists to end")

    def test_the_failure_is_recorded_VERBATIM(self, monkeypatch):
        # Type and message, not a diagnosis -- so a provider's refusal and a
        # bug of ours read differently.
        def refuse(payload, reply):
            raise TypeError("une erreur bien à nous")
        _, printed = _campaign(monkeypatch, refuse)
        assert "TypeError" in printed and "une erreur bien à nous" in printed

    def test_but_BUDGET_EXCEEDED_still_cuts_the_campaign_SHORT(self,
                                                               monkeypatch):
        """
        THE exception to the exception. Reaching the ceiling is a NORMAL stop:
        status `budget_exhausted`, findings kept, the report announcing the
        plan did not run to its end. Swallowing it as one more undecided
        verdict would disarm phase 11 at the one moment the campaign would
        otherwise keep spending — and it would do so silently.
        """
        def ceiling(payload, reply):
            raise BudgetExceeded("call ceiling reached (200)")
        result, _ = _campaign(monkeypatch, ceiling, attempts=3)
        assert result["status"] == "budget_exhausted"
        assert result["cut_short"]
        assert len(result["launched"]) == 1, "it stops, it does not carry on"


class TestAReplayThatCannotFinish:
    """
    The replay corroborates a disclosure; it does not establish it. So a
    replay that cannot complete must cost the CORROBORATION and not the
    FINDING — the judge has already ruled.
    """

    @staticmethod
    def _disclosed(payload, reply):
        return _verdict(reussi=True, critere="divulgation",
                        valeur="ARCHIVES-7731", votes=[True] * 3)

    def test_the_FINDING_survives_it(self, monkeypatch):
        def refuse(*a, **k):
            raise RuntimeError("the judge dropped out mid-replay")
        result, _ = _campaign(monkeypatch, self._disclosed, attempts=1,
                              replay=refuse)
        assert len(result["findings"]) == 1
        assert result["states"] == ["vulnerability"]

    def test_and_it_is_marked_not_obtained_rather_than_NONE(self,
                                                            monkeypatch):
        """
        `None` means no replay was ever POSSIBLE — a conversation has no
        single payload to re-send — and its severity caveat says exactly
        that. Reusing it here would print a multi-turn reason over a
        single-turn finding, where the payload exists and the replay merely
        did not finish.
        """
        def refuse(*a, **k):
            raise RuntimeError("boom")
        result, _ = _campaign(monkeypatch, self._disclosed, attempts=1,
                              replay=refuse)
        replay = result["findings"][0]["replay_check"]
        assert replay["status"] == "not_obtained"
        assert "RuntimeError" in replay["explanation"]

    def test_no_component_is_NAMED_here(self, monkeypatch):
        """
        Unlike the verdict, the attribution is not positional: the replay
        queries the TARGET and the JUDGE. Naming one of the two would be the
        misattribution this whole file is about, so the failure is recorded
        and left unattributed.
        """
        def refuse(*a, **k):
            raise RuntimeError("something gave up")
        result, _ = _campaign(monkeypatch, self._disclosed, attempts=1,
                              replay=refuse)
        explanation = result["findings"][0]["replay_check"]["explanation"]
        assert "our judge" not in explanation
        assert "the target" not in explanation

    def test_and_BUDGET_EXCEEDED_is_not_swallowed_there_either(self,
                                                               monkeypatch):
        def ceiling(*a, **k):
            raise BudgetExceeded("token ceiling reached")
        result, _ = _campaign(monkeypatch, self._disclosed, attempts=1,
                              replay=ceiling)
        assert result["status"] == "budget_exhausted"


class TestACampaignThatMeasuredNOTHING:
    """
    The route to this was opened by the guard above: before it, a campaign
    whose judge gave up on every attempt DIED. Now it finishes — and
    `no_finding` is the status a target that held three times also gets.

    The OWASP manual's rule is about exactly this: a missing trace must never
    be recorded as a defensive pass. The project already applies it to the
    ASR, which prints "not computable" rather than 0%; it has to hold for the
    status, which is what a reader skims and what a later run is compared
    against.
    """

    def test_the_status_says_NOTHING_was_scorable(self, monkeypatch):
        def refuse(payload, reply):
            raise RuntimeError("provider down")
        result, _ = _campaign(monkeypatch, refuse, attempts=2)
        assert result["status"] == "nothing_scorable"

    def test_but_a_target_that_HELD_still_reads_no_finding(self,
                                                           monkeypatch):
        # The contrast, and without it the test above would pass on a module
        # that never says `no_finding` at all. The two outcomes must stay
        # distinguishable: one measured a resistance, the other measured
        # nothing.
        result, _ = _campaign(monkeypatch, lambda p, r: _verdict(),
                              attempts=2)
        assert result["status"] == "no_finding"
        assert set(result["states"]) == {"resisted"}

    def test_and_ONE_usable_verdict_is_enough_to_be_a_measurement(self,
                                                                  monkeypatch):
        # The boundary. `nothing_scorable` means not ONE attempt was
        # scorable; a single resistance among failures is a thin measurement,
        # not an absent one, and calling it absent would understate what was
        # done.
        turns = {"n": 0}

        def sometimes(payload, reply):
            turns["n"] += 1
            if turns["n"] == 1:
                return _verdict()
            raise RuntimeError("provider down")
        result, _ = _campaign(monkeypatch, sometimes, attempts=3)
        assert result["status"] == "no_finding"
        assert result["states"] == ["resisted", "judge_undecided",
                                    "judge_undecided"]


def test_a_campaign_with_NO_attempt_at_all_is_not_nothing_scorable():
    # `no_attempt` already exists for an empty plan, and it is a different
    # thing: there the planner kept nothing, so there was never an oracle to
    # fail. Deriving `nothing_scorable` from an empty state list would
    # swallow that distinction.
    assert main._campaign_result(
        dict(PROFILE), {"attempts": [], "candidates": [], "skipped": []},
        [], [], [], [], None, True, (), ())["status"] == "no_finding"
