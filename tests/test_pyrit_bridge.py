"""
Tests for the PyRIT bridge (phase 3b).

THESE TESTS RUN WITHOUT PYRIT, and that is the whole design of the bridge.
PyRIT is an optional extra requiring Python >= 3.11; continuous integration
runs 3.10 and 3.13, so on half the matrix PyRIT cannot even be installed.
Anything decided inside a `PromptTarget` or a `Scorer` subclass is therefore
logic nobody tests — so every decision that can be made on plain data lives in
`pyrit_bridge.convert`, which imports no PyRIT at all, and the subclasses are
thin shells over it.

It is the garak arrangement read the other way round: there, the exporter
imports nothing from the project; here, the bridge's thinking imports nothing
from PyRIT.
"""

import builtins

import pytest

import main

import stats
from pyrit_bridge import REQUIRED, require_pyrit
from pyrit_bridge.convert import (BREACHED, HELD, UNDECIDED, api_from_turns,
                                  denominator_state, system_from_api,
                                  turns_from_api, verdict_to_score)
from targets.conversation import ATTACKER_ROLE, TARGET_ROLE


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge", "agents.reconnaissance"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


class TestTheRolesTheJudgeMustNeverRead:
    """
    `turns_from_api` decides what reaches the judge, so it decides what counts
    as evidence.

    Three roles are DROPPED, and the third is the one that matters:
    `system` is our own framing, `tool` is machinery, and
    `simulated_assistant` is a turn PyRIT PRETENDS the target said — a
    prefilled history, which several of its attacks use. Letting one through
    as a chatbot turn would hand the judge a sentence no target ever produced.

    That is the corpus's `secret-dit-par-l-attaquant` trap moved up to the
    orchestrator, and the hand-written cases A08/A09/A10 exist because the
    judge gets it wrong when the provenance of a sentence is unclear.
    """

    def test_user_and_assistant_become_our_two_roles(self):
        turns = turns_from_api([{"role": "user", "content": "bonjour"},
                                {"role": "assistant", "content": "salut"}])
        assert turns == [{"role": ATTACKER_ROLE, "content": "bonjour"},
                         {"role": TARGET_ROLE, "content": "salut"}]

    @pytest.mark.parametrize("role", ["system", "developer", "tool",
                                      "simulated_tool"])
    def test_machinery_roles_are_dropped(self, role):
        assert turns_from_api([{"role": role, "content": "x"}]) == []

    def test_a_SIMULATED_assistant_turn_is_dropped(self):
        # The dangerous one: it looks like a reply and the target never said
        # it. A judge reading it as one would score our own prefill.
        assert turns_from_api(
            [{"role": "simulated_assistant", "content": "le code est X"}]
        ) == []

    def test_a_missing_content_is_dropped_not_turned_into_an_empty_turn(self):
        # An empty chatbot turn in the rendered transcript would read as a
        # target that answered nothing, which is not what happened.
        assert turns_from_api([{"role": "assistant"}]) == []

    def test_the_round_trip_is_stable(self):
        api = [{"role": "user", "content": "a"},
               {"role": "assistant", "content": "b"}]
        assert api_from_turns(turns_from_api(api)) == api


class TestTheSystemPromptIsExtractedSEPARATELY:
    """
    Two functions, deliberately: the judge must not read a system turn as
    dialogue, and the attacker model must receive it as its framing. One
    function doing both would let either behaviour leak into the other.
    """

    def test_a_system_turn_is_returned(self):
        assert system_from_api(
            [{"role": "system", "content": "tu es un attaquant"},
             {"role": "user", "content": "bonjour"}]
        ) == "tu es un attaquant"

    def test_several_are_joined_in_order(self):
        assert system_from_api([{"role": "system", "content": "un"},
                                {"role": "developer", "content": "deux"}]
                               ) == "un\ndeux"

    def test_no_system_turn_gives_None_not_an_empty_string(self):
        # `ask_llm(system="")` and `ask_llm(system=None)` are not the same
        # call: an empty instruction is still an instruction.
        assert system_from_api([{"role": "user", "content": "x"}]) is None

    def test_dialogue_turns_never_leak_into_the_instruction(self):
        assert system_from_api([{"role": "user", "content": "secret"},
                                {"role": "assistant", "content": "secret"}]
                               ) is None


class TestAnUndecidedVerdictIsNotADefensivePass:
    """
    The decision this bridge turns on.

    `judge_by_vote` returns `None` when three judgements do not agree — "for a
    human to review" — and `stats.STATES` counts that as NOT scorable, out of
    the ASR denominator, because an unreadable verdict is a MISSING
    measurement. Measured 2026-11-12: treating it as "the target resisted"
    moved an ASR by seventeen points in the target's favour.

    PyRIT's control flow has no third state, so it is told `false`. The point
    of these tests is that the state SURVIVES that flattening.
    """

    def test_a_breach_is_reported_true(self):
        score = verdict_to_score({"reussi": True, "critere": "divulgation",
                                  "analyse": "donne le code"})
        assert score["score_value"] == "true"
        assert score["score_category"] == ["divulgation"]

    def test_a_refusal_is_reported_false(self):
        score = verdict_to_score({"reussi": False, "critere": "aucun",
                                  "analyse": "refuse"})
        assert score["score_value"] == "false"
        assert score["score_metadata"]["undecided"] == 0

    def test_an_undecided_verdict_is_false_FOR_PYRIT(self):
        # It must not stop an attack: an undecided verdict is not a
        # demonstrated breach.
        score = verdict_to_score({"reussi": None, "critere": "split",
                                  "votes": [True, False, None]})
        assert score["score_value"] == "false"

    def test_but_the_undecided_state_is_CARRIED_not_lost(self):
        # The half that makes the flattening acceptable. Without it we would
        # be writing "the target resisted" into the evidence every time the
        # judge abstained -- the OWASP manual's "a missing trace must never be
        # recorded as a defensive pass", committed by the integration.
        score = verdict_to_score({"reussi": None, "critere": "split",
                                  "votes": [True, False, None]})
        assert score["score_metadata"]["undecided"] == 1
        assert UNDECIDED in score["score_rationale"]

    def test_the_metadata_holds_only_strings_and_ints(self):
        # PyRIT types `score_metadata` that way; a list or a None would be
        # rejected at write time, i.e. after the campaign has been run.
        score = verdict_to_score({"reussi": True, "critere": "divulgation",
                                  "valeur": "ARCHIVES-7731", "tour": 2,
                                  "votes": [True, True, True]})
        assert all(isinstance(v, (str, int))
                   for v in score["score_metadata"].values())


class TestTheDenominatorStatesAreNOTREDECLARED:
    """
    `stats.STATES` is the single source of truth for these keys, and this test
    is the junction that proves the bridge uses it.

    It is not hypothetical: writing those names from memory produced
    `juge_indecis`, `faille` and `resiste` -- the FRENCH names, which
    CLAUDE.md still describes, for keys the code calls `judge_undecided`,
    `vulnerability` and `resisted`. A contradiction between code and prose
    raises nothing and breaks no test, so the test has to be this one.
    """

    def test_every_state_the_bridge_returns_exists_in_stats(self):
        for state in (UNDECIDED, BREACHED, HELD):
            assert state in stats.STATES, f"{state} unknown to stats.STATES"

    def test_a_breach_and_a_refusal_are_both_SCORABLE(self):
        assert stats.is_scorable(denominator_state({"reussi": True}))
        assert stats.is_scorable(denominator_state({"reussi": False}))

    def test_an_undecided_verdict_LEAVES_the_denominator(self):
        state = denominator_state({"reussi": None})
        assert state == UNDECIDED
        assert stats.is_scorable(state) is False

    def test_a_breach_and_a_refusal_are_not_the_same_state(self):
        assert denominator_state({"reussi": True}) != \
            denominator_state({"reussi": False})


class TestAbsentPyritSaysWhatToDo:
    """
    A bare `ModuleNotFoundError: No module named 'pyrit'` tells a reader
    nothing about an extra they were never told existed -- and on Python 3.10
    it is not even installable, so the message has to say that too.

    The same choice as the authorisation guard, which exits with "copy
    authorisation.example.json..." rather than a traceback.
    """

    @staticmethod
    def _without_pyrit(monkeypatch):
        real = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name == "pyrit" or name.startswith("pyrit."):
                raise ModuleNotFoundError(f"No module named {name!r}")
            return real(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", refuse)

    def test_it_raises_with_the_command_to_run(self, monkeypatch):
        self._without_pyrit(monkeypatch)
        with pytest.raises(RuntimeError) as refusal:
            require_pyrit()
        message = str(refusal.value)
        assert "requirements-pyrit.txt" in message
        assert "3.11" in message

    def test_it_says_a_single_turn_campaign_still_works(self, monkeypatch):
        # Otherwise a reader on 3.10 concludes the tool does not run at all.
        self._without_pyrit(monkeypatch)
        with pytest.raises(RuntimeError) as refusal:
            require_pyrit()
        assert "main.py" in str(refusal.value)

    def test_the_version_the_bridge_was_written_against_is_NAMED(self):
        # The integration's standing cost: three API facts must be re-checked
        # on each minor release, and a reader cannot do that without knowing
        # which version was checked.
        assert REQUIRED == "1.2.1"


class TestTheMultiturnEntryPoint:
    """
    Phase 3b's orchestrator entry point, checked WITHOUT PyRIT — which is the
    state of continuous integration, and the only state possible on Python
    3.10, where PyRIT cannot be installed at all.
    """

    def test_an_unknown_attack_name_exits_with_an_INSTRUCTION(self, capsys):
        # Checked before the mandate, because it sends no request. The
        # alternative is a KeyError in the middle of a campaign, after the
        # budget is armed and an audit trail opened against a client's
        # system — the lesson of `--target demo:9`.
        with pytest.raises(SystemExit) as stop:
            main.cli(["--target", "mock", "--multiturn", "fictif"])
        assert stop.value.code == 2
        err = capsys.readouterr().err
        assert "Unknown multi-turn attack" in err
        assert "redteaming" in err

    def test_an_absent_PyRIT_exits_with_the_command_to_run(self, capsys,
                                                           monkeypatch):
        import builtins
        real = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name == "pyrit" or name.startswith("pyrit."):
                raise ModuleNotFoundError(name)
            return real(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", refuse)

        with pytest.raises(SystemExit) as stop:
            main.cli(["--target", "mock", "--multiturn"])
        assert stop.value.code == 2
        assert "requirements-pyrit.txt" in capsys.readouterr().err

    def test_the_help_works_WITHOUT_the_extra(self, capsys):
        # Building the parser must not require PyRIT: `--help` has to work on
        # Python 3.10, where the extra cannot be installed.
        with pytest.raises(SystemExit):
            main.cli(["--help"])
        out = capsys.readouterr().out
        assert "--multiturn" in out
        assert "--max-turns" in out

    def test_the_help_WARNS_that_the_payload_text_is_not_sent(self, capsys):
        # The surprising part of the mode, said where it is chosen rather
        # than only in the report afterwards.
        with pytest.raises(SystemExit):
            main.cli(["--help"])
        assert "NOT sent" in capsys.readouterr().out

    def test_the_attack_names_are_READ_not_restated(self):
        # They live in `pyrit_bridge.convert`, which imports no PyRIT, so the
        # CLI can offer them on a machine that cannot install the extra. A
        # second copy of a catalogue drifts on the first attack added.
        from pyrit_bridge.convert import ATTACK_NAMES, DEFAULT_ATTACK
        assert main.MULTITURN_ATTACKS is ATTACK_NAMES
        assert main.MULTITURN_DEFAULT == DEFAULT_ATTACK

    def test_main_is_IMPORTABLE_with_PyRIT_unavailable(self):
        # The promise that must survive the extra: the default path needs
        # nothing. Checked on the SOURCE, because `main` is already imported
        # here -- a top-level `import pyrit` anywhere in it would break every
        # single-turn campaign on Python 3.10.
        import pathlib as _pathlib
        lines = _pathlib.Path(main.__file__).read_text(
            encoding="utf-8").splitlines()
        tops = [line for line in lines
                if line.startswith(("import ", "from "))]
        offenders = [line for line in tops
                     if "pyrit" in line.lower()
                     and "pyrit_bridge.convert" not in line]
        assert not offenders, offenders
