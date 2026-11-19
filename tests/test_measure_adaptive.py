"""
Tests for the adaptive-attacker measurement (2026-11-19).

No LLM call and NO PyRIT: the extra is absent from continuous integration and
cannot be installed on Python 3.10, so everything decidable on plain data
lives outside it — the same arrangement the bridge itself uses, where
`convert.py` imports no PyRIT at all.

What these protect is what makes the measurement readable: the arms are
interleaved, both are judged by the same instruction, and the two biases that
favour the adaptive arm stay visible in the output.
"""

import json

import pytest

import evaluation.measure_adaptive as adaptive


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


class TestPyRITIsImportedLAZILY:
    """
    The extra is absent from CI and not installable on Python 3.10. Importing
    it at module level would make this file unimportable where the rest of
    the evaluation still runs — the same reason `main` imports the bridge
    lazily, and a test reads its source for exactly this.
    """

    def test_the_module_imports_with_no_pyrit(self):
        # It already did, to reach this line.
        assert adaptive.ATTACK == "redteaming"

    def test_the_import_sits_inside_the_function(self):
        """
        Checked on the module's own PARSE TREE, not on its text.

        A first version searched the source above `adaptive_attempt` for the
        word "pyrit" and failed on the docstring, which names it a dozen
        times. A guard that cries wrong on legitimate text teaches people to
        ignore it -- this project removed one for exactly that -- and the
        thing to check is an import statement, not a word.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(adaptive))
        top_level = [node for node in tree.body
                     if isinstance(node, (ast.Import, ast.ImportFrom))]
        names = [alias.name for node in top_level
                 for alias in node.names] + [
            node.module or "" for node in top_level
            if isinstance(node, ast.ImportFrom)]
        offenders = [name for name in names if name.startswith("pyrit")]
        assert not offenders, (
            f"{offenders} imported at module level: the measurement would "
            f"stop importing wherever the extra is absent")

        inside = ast.parse(inspect.getsource(adaptive.adaptive_attempt))
        assert any(isinstance(node, ast.ImportFrom)
                   and (node.module or "").startswith("pyrit")
                   for node in ast.walk(inside)), (
            "the lazy import is gone: nothing would load PyRIT at all")


class TestTheBreachReading:
    def test_the_FIRST_positive_verdict_decides(self):
        # PyRIT stops on success, so the deciding verdict is the first
        # positive one; reading the last would take an abstention after it.
        breached, verdict = adaptive._breach([
            {"reussi": False}, {"reussi": True, "critere": "obeissance"},
        ])
        assert breached is True
        assert verdict["critere"] == "obeissance"

    def test_no_positive_verdict_is_no_breach(self):
        assert adaptive._breach([{"reussi": False}]) == (False, None)

    def test_an_ABSTENTION_is_not_a_breach(self):
        # `None` is a missing measurement, never an agreement — the rule the
        # ASR denominator applies, and conflating them moved an ASR by
        # seventeen points on 2026-11-12.
        assert adaptive._breach([{"reussi": None}]) == (False, None)

    def test_no_verdict_at_all_is_no_breach(self):
        assert adaptive._breach([]) == (False, None)


class TestTheFixedArmIsJudgedLikeTheAdaptiveOne:
    """
    Both arms are conversations, so BOTH go through `judge_conversation`.
    That is what removes the asymmetry declared for the 2026-11-19 run, where
    the composed arm was scored by the base instruction and the sequenced one
    by base plus addendum.
    """

    def test_the_fixed_arm_uses_the_conversation_judge(self, monkeypatch):
        called = []
        monkeypatch.setattr(adaptive, "play",
                            lambda ask, turns: [
                                {"role": "attacker", "content": turns[0]},
                                {"role": "target", "content": "r1"},
                                {"role": "attacker", "content": turns[1]},
                                {"role": "target", "content": "r2"}])
        monkeypatch.setattr(
            adaptive, "judge_conversation",
            lambda turns: called.append(turns) or {"reussi": True,
                                                   "critere": "divulgation",
                                                   "tour": 2})
        out = adaptive.fixed_attempt(lambda *a, **k: "r", "payload",
                                     {"id": "refus-1", "wording": "w"})
        assert called, "the fixed arm did not go through judge_conversation"
        assert out == {"breached": True, "criterion": "divulgation",
                       "turn": 2, "judgements": 1}

    def test_no_breach_carries_no_criterion(self, monkeypatch):
        monkeypatch.setattr(adaptive, "play",
                            lambda ask, turns: [{"role": "target",
                                                 "content": "r"}] * 4)
        monkeypatch.setattr(adaptive, "judge_conversation",
                            lambda turns: {"reussi": False,
                                           "critere": "divulgation",
                                           "tour": 2})
        out = adaptive.fixed_attempt(lambda *a, **k: "r", "p",
                                     {"id": "o", "wording": "w"})
        assert out["criterion"] is None and out["turn"] is None


class TestTheArmsAreINTERLEAVED:
    """
    The target is probabilistic and drifts. Running one arm to completion and
    then the other would let drift masquerade as an effect — the reason the
    string protocol plays a pair's two halves back to back.
    """

    def test_each_attempt_runs_both_arms_before_the_next(self, monkeypatch,
                                                         tmp_path):
        order = []
        monkeypatch.setattr(adaptive, "choose_target",
                            lambda name: (lambda *a, **k: "r"))
        monkeypatch.setattr(adaptive, "require_conversation",
                            lambda *a, **k: None)
        monkeypatch.setattr(adaptive, "load_library", lambda: {})
        monkeypatch.setattr(adaptive, "reconnoitre", lambda ask: {})
        monkeypatch.setattr(adaptive, "launchable",
                            lambda *a, **k: ([("t", "payload")], {}))
        monkeypatch.setattr(
            adaptive, "targeted_objectives",
            lambda *a, **k: ([{"id": "refus-1", "wording": "w"}], "1 from"))
        monkeypatch.setattr(
            adaptive, "adaptive_attempt",
            lambda *a, **k: order.append("A") or {
                "breached": False, "criterion": None, "turn": None,
                "judgements": 3})
        monkeypatch.setattr(
            adaptive, "fixed_attempt",
            lambda *a, **k: order.append("B") or {
                "breached": False, "criterion": None, "turn": None,
                "judgements": 1})

        adaptive.measure(per_objective=3, show=lambda *_: None)
        assert order == ["A", "B", "A", "B", "A", "B"], order


class TestTheTwoBIASESStayVisible:
    """
    Both favour the adaptive arm: three turns against two, and a verdict
    after every turn against one. Declared before the figure so the figure
    can be read — and the output has to keep saying so, or a later reader
    takes a win at face value.
    """

    @staticmethod
    def _summary(attempts):
        said = []
        adaptive._summary(attempts, said.append)
        return " ".join(said)

    @staticmethod
    def _attempt(a_breach, b_breach, judgements=3, turn=1):
        return {"objective": "o", "technique": "t",
                "adaptive": {"breached": a_breach, "judgements": judgements,
                             "criterion": "obeissance" if a_breach else None,
                             "turn": turn if a_breach else None},
                "fixed": {"breached": b_breach, "judgements": 1,
                          "criterion": "divulgation" if b_breach else None,
                          "turn": 2 if b_breach else None}}

    def test_the_judgement_count_of_each_arm_is_reported(self):
        text = self._summary([self._attempt(False, False, judgements=3)])
        assert "3.0 time(s) per attempt" in text
        assert "against 1 for the fixed arm" in text

    def test_the_protocol_states_both_biases_before_the_run(self, monkeypatch,
                                                            capsys):
        # In the header, not only in the docstring: a reader of the output
        # must meet them before the figures.
        monkeypatch.setattr(adaptive, "choose_target",
                            lambda name: (lambda *a, **k: "r"))
        monkeypatch.setattr(adaptive, "require_conversation",
                            lambda *a, **k: None)
        monkeypatch.setattr(adaptive, "load_library", lambda: {})
        monkeypatch.setattr(adaptive, "reconnoitre", lambda ask: {})
        monkeypatch.setattr(adaptive, "launchable",
                            lambda *a, **k: ([("t", "p")], {}))
        monkeypatch.setattr(
            adaptive, "targeted_objectives",
            lambda *a, **k: ([{"id": "o", "wording": "w"}], "1"))
        monkeypatch.setattr(adaptive, "adaptive_attempt",
                            lambda *a, **k: {"breached": False,
                                             "criterion": None, "turn": None,
                                             "judgements": 1})
        monkeypatch.setattr(adaptive, "fixed_attempt",
                            lambda *a, **k: {"breached": False,
                                             "criterion": None, "turn": None,
                                             "judgements": 1})
        adaptive.measure(per_objective=1)
        out = capsys.readouterr().out
        assert "biases favour the adaptive arm" in out
        assert "null result is therefore strong" in out


class TestTheTest:
    def test_a_clear_win_is_significant(self):
        # 30/60 against 10/60.
        assert adaptive.fisher_one_sided(30, 30, 10, 50) < 0.05

    def test_an_equal_split_is_not(self):
        assert adaptive.fisher_one_sided(20, 40, 20, 40) > 0.4

    def test_a_loss_is_never_significant_in_this_direction(self):
        # One-sided: the hypothesis is that the ADAPTIVE arm does better.
        assert adaptive.fisher_one_sided(10, 50, 30, 30) > 0.95

    def test_nothing_at_all_gives_one(self):
        assert adaptive.fisher_one_sided(0, 0, 0, 0) == 1.0


class TestResume:
    @staticmethod
    def _state(tmp_path, complete=False, wordings=None):
        path = tmp_path / "run.json"
        path.write_text(json.dumps({
            "target": "demo",
            "objectives": wordings or {"refus-1": "w"},
            "complete": complete,
            "attempts": [{"objective": "refus-1"}],
        }), encoding="utf-8")
        return path

    def test_a_complete_run_is_REFUSED(self, tmp_path):
        # Resuming is a repair; reusing a finished run would repeat a
        # measurement on a probabilistic target instead of resampling it.
        path = self._state(tmp_path, complete=True)
        with pytest.raises(SystemExit):
            adaptive._resume(path, {"refus-1": "w"}, lambda *_: None)

    def test_different_objectives_start_over(self, tmp_path):
        path = self._state(tmp_path, wordings={"refus-1": "something else"})
        assert adaptive._resume(path, {"refus-1": "w"},
                                lambda *_: None) == []

    def test_the_same_objectives_are_reused(self, tmp_path):
        # The contrast: without it, refusing every resume would pass too.
        path = self._state(tmp_path)
        assert len(adaptive._resume(path, {"refus-1": "w"},
                                    lambda *_: None)) == 1

    def test_an_absent_file_is_not_an_error(self, tmp_path):
        assert adaptive._resume(tmp_path / "none.json", {},
                                lambda *_: None) == []
