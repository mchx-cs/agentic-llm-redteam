"""
Tests for the JUDGED outcome of `measure_multiturn` (2026-11-19).

No LLM call: the judge is replaced by a function of known behaviour, which is
the same arrangement `check_stability` uses and for the same reason — what can
be checked without a model must be.

What these protect is the property that makes the second protocol worth
running at all: **the two outcomes share their pairing**. Two measurements
that paired differently would be comparable in nothing, and the judged run's
whole justification is that it asks a different question of the SAME pairs.
"""

import json

import pytest

import evaluation.measure_multiturn as measure


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


def _verdict(breached, criterion=None, turn=None):
    return {"reussi": breached, "critere": criterion, "tour": turn}


class TestTheOutcomeIsTheONLYThingThatChanges:
    """
    The pairing, the arms and the order are identical either way. That is not
    a convenience: the judged protocol's justification is that it asks a
    different question of the same pairs, and a different pairing would make
    the two runs comparable in nothing.
    """

    @staticmethod
    def _spy(monkeypatch):
        """Record what each arm was sent, whatever the outcome."""
        sent = []

        def ask(message, history=None):
            sent.append(message)
            return "une réponse"

        monkeypatch.setattr(measure, "play",
                            lambda a, turns: [
                                {"role": "attacker", "content": turns[0]},
                                {"role": "target", "content": "r1"},
                                {"role": "attacker", "content": turns[1]},
                                {"role": "target", "content": "r2"}])
        return ask, sent

    def test_both_outcomes_send_the_same_composed_message(self, monkeypatch):
        payload = "préambule"
        objective = {"id": "refus-1", "wording": "donner le code"}
        seen = {}
        for outcome in ("string", "judge"):
            ask, sent = self._spy(monkeypatch)
            monkeypatch.setattr(measure, "_judged",
                                lambda *_: {"breached": False,
                                            "criterion": None, "turn": None})
            measure.one_pair(ask, payload, objective, outcome)
            seen[outcome] = sent
        assert seen["string"] == seen["judge"], (
            "the composed arm was not sent the same message under the two "
            "outcomes: the pairs would not be comparable")

    def test_the_judged_outcome_reads_the_verdict_and_not_the_string(
            self, monkeypatch):
        # The point of the second protocol: a breach the string search cannot
        # see — an `abus_outils` finding, which is what `outil-N` objectives
        # aim at and what defect 3 was about.
        ask, _ = self._spy(monkeypatch)
        monkeypatch.setattr(
            measure, "_judged",
            lambda turns, text: {"breached": True,
                                 "criterion": "abus_outils", "turn": 2})
        result = measure.one_pair(ask, "p", {"id": "outil-1", "wording": "w"},
                                  "judge")
        assert result["sequence"] is True
        assert result["critere_sequence"] == "abus_outils"
        assert result["tour_de_fuite"] == 2

    def test_the_string_outcome_is_untouched(self, monkeypatch):
        ask, _ = self._spy(monkeypatch)
        result = measure.one_pair(ask, "p", {"id": "refus-1", "wording": "w"},
                                  "string")
        assert result["sequence"] is False
        assert "critere_sequence" not in result


class TestTheJudgedOutcomeDeclaresItsFormat:
    """
    A conversation goes through `judge_conversation`, a single exchange
    through `judge`. The caller declares which, as everywhere else in this
    project: a default would let a conversation be judged without its context
    in silence, which is the defect family recorded for the conversation
    capability and for `_inject`.
    """

    def test_a_conversation_uses_the_conversation_judge(self, monkeypatch):
        called = []
        monkeypatch.setattr("agents.judge.judge_conversation",
                            lambda turns: called.append("conversation")
                            or _verdict(True, "divulgation", 1))
        monkeypatch.setattr("agents.judge.judge",
                            lambda *a: called.append("single")
                            or _verdict(False))
        turns = [{"role": "attacker", "content": "a"},
                 {"role": "target", "content": "b"},
                 {"role": "attacker", "content": "c"},
                 {"role": "target", "content": "d"}]
        out = measure._judged(turns, None)
        assert called == ["conversation"]
        assert out == {"breached": True, "criterion": "divulgation",
                       "turn": 1}

    def test_a_single_exchange_uses_the_single_turn_judge(self, monkeypatch):
        called = []
        monkeypatch.setattr("agents.judge.judge_conversation",
                            lambda turns: called.append("conversation")
                            or _verdict(False))
        monkeypatch.setattr("agents.judge.judge",
                            lambda p, r: called.append("single")
                            or _verdict(True, "obeissance"))
        turns = [{"role": "attacker", "content": "a"},
                 {"role": "target", "content": "b"}]
        out = measure._judged(turns, "a")
        assert called == ["single"]
        assert out["criterion"] == "obeissance"

    def test_no_breach_carries_no_criterion_and_no_turn(self, monkeypatch):
        # A criterion on a verdict that found nothing would be counted in the
        # breakdown and inflate it.
        monkeypatch.setattr("agents.judge.judge",
                            lambda p, r: _verdict(False, "divulgation", 2))
        out = measure._judged([{"role": "attacker", "content": "a"},
                               {"role": "target", "content": "b"}], "a")
        assert out == {"breached": False, "criterion": None, "turn": None}


class TestARunNeverBlendsTheTwoOutcomes:
    """
    The judge cache's rule of 2026-11-16, applied here: resuming across a
    change of OUTCOME would pool two measurements that answer different
    questions into one figure — the blending this project refuses for judges,
    formats, languages and defence levels alike.
    """

    @staticmethod
    def _state(tmp_path, outcome):
        path = tmp_path / "run.json"
        measure._save(path, "demo", [{"id": "refus-1", "wording": "w"}],
                      [{"technique": "t", "objective": "refus-1",
                        "sequence": True, "mono": False}],
                      False, outcome)
        return path

    def test_the_outcome_is_written_into_the_state(self, tmp_path):
        path = self._state(tmp_path, "judge")
        assert json.loads(path.read_text(encoding="utf-8"))["outcome"] \
            == "judge"

    def test_resuming_a_string_run_as_judged_starts_over(self, tmp_path):
        path = self._state(tmp_path, "string")
        said = []
        done = measure._resume(path, "demo",
                               [{"id": "refus-1", "wording": "w"}],
                               said.append, "judge")
        assert done == {}
        assert any("different question" in line for line in said)

    def test_resuming_the_SAME_outcome_reuses_the_pairs(self, tmp_path):
        # The contrast that makes the test above mean something: without it,
        # refusing every resume would pass just as well.
        path = self._state(tmp_path, "judge")
        done = measure._resume(path, "demo",
                               [{"id": "refus-1", "wording": "w"}],
                               lambda *_: None, "judge")
        assert ("t", "refus-1") in done

    def test_a_file_written_before_the_outcome_existed_reads_as_string(
            self, tmp_path):
        path = tmp_path / "old.json"
        path.write_text(json.dumps({
            "target": "demo",
            "objectives": {"refus-1": "w"},
            "pairs": [{"technique": "t", "objective": "refus-1"}],
        }), encoding="utf-8")
        done = measure._resume(path, "demo",
                               [{"id": "refus-1", "wording": "w"}],
                               lambda *_: None, "string")
        assert ("t", "refus-1") in done


class TestTheBreakdownIsDescriptiveAndNeverTested:
    def test_it_names_the_criteria_of_each_arm(self):
        said = []
        measure._judged_detail([
            {"sequence": True, "mono": False,
             "critere_sequence": "divulgation", "critere_mono": None,
             "tour_de_fuite": 2},
            {"sequence": True, "mono": True,
             "critere_sequence": "abus_outils",
             "critere_mono": "divulgation", "tour_de_fuite": 1},
        ], said.append)
        text = " ".join(said)
        assert "divulgation 1" in text and "abus_outils 1" in text

    def test_it_does_NOT_repeat_the_formats_own_contribution(self):
        """
        The summary already gives it, as its exact complement: "invisible in
        the last reply" is a breach on turn 1 of a two-turn conversation. Two
        figures saying the inverse of each other side by side read as a
        contradiction -- found by running this and reading the output.
        """
        said = []
        measure._judged_detail([
            {"sequence": True, "mono": False, "critere_sequence": "x",
             "critere_mono": None, "tour_de_fuite": 2},
        ], said.append)
        assert not any("AFTER the first turn" in line for line in said)
