"""
Tests for the per-case stability check (2026-11-18).

No LLM call: the judge is a parameter, so the logic is exercised with a
simulated one of known behaviour — the same reason `verify_by_replay` takes
its target and its judge.

What is checked here is the READING, because a wrong reading is worse than no
check: it would credit an edit for a lucky draw, which is exactly the mistake
this module was written after making. Three conclusions drawn from single runs
on 2026-11-18 turned out to be wrong in precisely that way.
"""

import pytest

from evaluation.check_stability import check, is_conversation, reading


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


class TestTheReading:
    """
    Three outcomes and not two. "Unstable" is the one the project was
    missing, and it is the only honest label for a case that answers
    differently to the same question.
    """

    def test_every_vote_right_is_stable_and_correct(self):
        verdict, wrong = reading([False] * 5, False, 5)
        assert verdict == "stable, correct"
        assert wrong == 0

    def test_every_vote_wrong_is_stable_and_WRONG(self):
        # The case that matters most: a fix that did nothing. A08 answered
        # wrongly five times out of five while a single run had shown it
        # passing.
        verdict, wrong = reading([True] * 5, False, 5)
        assert verdict == "stable, WRONG"
        assert wrong == 5

    def test_a_MIX_is_unstable_and_says_how_often(self):
        verdict, wrong = reading([True, False, True, True, False], False, 5)
        assert "UNSTABLE" in verdict
        assert "3/5" in verdict

    def test_one_flip_in_five_is_already_UNSTABLE(self):
        # Not rounded away: one flip means the verdict is not a property of
        # the case, and a run showing it either way proves nothing.
        verdict, _ = reading([True, True, True, False, True], True, 5)
        assert "UNSTABLE" in verdict

    def test_None_counts_as_WRONG_whatever_the_label(self):
        # A verdict without a majority is a missing measurement, not an
        # agreement — the same rule the ASR denominator applies.
        verdict, wrong = reading([None] * 5, False, 5)
        assert verdict == "stable, WRONG"
        assert wrong == 5


class TestTheFormatIsDECLAREDNotGuessed:
    def test_several_exchanges_are_a_conversation(self):
        assert is_conversation({"turns": [{}, {}, {}, {}]})

    def test_a_SINGLE_exchange_stored_as_turns_is_not(self):
        # A03 and A04 are stored as `turns` and hold one exchange. Judging
        # them with the multi-turn addendum would judge them with rules
        # written for several turns.
        assert not is_conversation({"turns": [{}, {}]})

    def test_a_payload_and_reply_entry_is_not(self):
        assert not is_conversation({"payload": "u", "reply": "c"})


class TestCheck:
    CORPUS = {
        "STABLE-OK": {"id": "STABLE-OK", "expected": False,
                      "payload": "u", "reply": "c"},
        "STABLE-BAD": {"id": "STABLE-BAD", "expected": False,
                       "payload": "u", "reply": "c"},
        "FLAKY": {"id": "FLAKY", "expected": False,
                  "payload": "u", "reply": "c"},
    }

    @staticmethod
    def _judge(behaviour):
        """A judge whose answers we decide, per entry."""
        counters = {}

        def judge_one(entry):
            n = counters.get(entry["id"], 0)
            counters[entry["id"]] = n + 1
            return {"reussi": behaviour[entry["id"]][n]}
        return judge_one

    def _run(self, capsys, behaviour, ids=None, rounds=5):
        results = check(ids or sorted(self.CORPUS), rounds=rounds,
                        corpus=self.CORPUS, judge_one=self._judge(behaviour))
        return results, capsys.readouterr().out

    def test_each_case_gets_its_reading(self, capsys):
        results, out = self._run(capsys, {
            "STABLE-OK": [False] * 5,
            "STABLE-BAD": [True] * 5,
            "FLAKY": [True, False, True, True, False],
        })
        assert results["STABLE-OK"]["reading"] == "stable, correct"
        assert results["STABLE-BAD"]["reading"] == "stable, WRONG"
        assert "UNSTABLE" in results["FLAKY"]["reading"]

    def test_the_unstable_ones_are_NAMED_at_the_end(self, capsys):
        # So a reader cannot miss them: attributing an unstable case to an
        # edit is the mistake this module exists to prevent.
        _, out = self._run(capsys, {
            "STABLE-OK": [False] * 5,
            "STABLE-BAD": [True] * 5,
            "FLAKY": [True, False, True, True, False],
        })
        assert "1 unstable case(s): FLAKY" in out
        assert "Attribute neither to an" in out

    def test_nothing_is_flagged_when_everything_is_stable(self, capsys):
        _, out = self._run(capsys, {
            "STABLE-OK": [False] * 5,
            "STABLE-BAD": [True] * 5,
            "FLAKY": [False] * 5,
        })
        assert "unstable case(s)" not in out

    def test_the_WILSON_bound_is_printed_beside_each_line(self, capsys):
        # "Stable" means "did not flip in five", never "never flips", and the
        # bound is what says so: 5/5 correct still allows a real rate of 57%.
        _, out = self._run(capsys, {"STABLE-OK": [False] * 5},
                           ids=["STABLE-OK"])
        assert "Wilson" in out
        assert "57%" in out

    def test_an_absent_id_is_said_not_crashed(self, capsys):
        results, out = self._run(capsys, {}, ids=["NOPE"])
        assert "ABSENT" in out
        assert results == {}

    def test_the_rounds_are_honoured(self, capsys):
        results, _ = self._run(capsys, {"FLAKY": [True, False, True]},
                               ids=["FLAKY"], rounds=3)
        assert len(results["FLAKY"]["votes"]) == 3
