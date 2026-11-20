"""
The configuration the documents ADVISE must be the one the gate accepts
(2026-11-20).

Three places tell a reader how to obtain an independent bound: the report's
own no-finding block, `--attempts`'s help, and the README. On 2026-11-19 all
three advised `--only <technique> --no-adaptation` — and that configuration
was measured to span four objectives, so the gate refused it the bound. A
document advising a command that does not do what it says raises nothing and
breaks no test; this project has recorded that four times (the precedence
order documented backwards, the example report's stale claim, the six
passages the mode comparison falsified, and the report advising 30 attempts
when the CLI capped at 3).

So the advice is checked against the GATE, by driving a campaign with exactly
the flags the documents offer. No LLM call: the target and the judge are
replaced.
"""

import pathlib
import re

import pytest

import main

#: Every command the documents put in front of a reader as the way to get a
#: bound. Collected by reading them, so a fourth place added later is simply
#: not covered — which is honest, where hardcoding one string and calling it
#: "the advice" would not be.
DOCUMENTS = ("report.py", "main.py", "README.md")

PROFILE = {"role": "assistant", "language": "fr", "tools": ["consulter"],
           "refused_subjects": ["le code du fonds ancien", "les dossiers"],
           "mentions_instructions": True,
           "writes_code": None, "handles_documents": None, "context": [],
           "evidence": [], "exchanges": [], "warning": None}


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch, tmp_path):
    monkeypatch.setenv("GARAK_FILE", str(tmp_path / "absent.json"))
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("modèle appelé depuis tests/")),
                            raising=False)


def _offered():
    """
    The commands offered as the way to BOUND a zero — not every `--only`.

    A first version collected all of them and flagged `--only LLM07`, which is
    a scoping example and has nothing to do with a bound. A guard that cries
    wrong on legitimate text teaches people to ignore it, and this project
    removed one for exactly that. The discriminator is that bounding advice
    names a budget or the control arm; a scoping example names neither.
    """
    found = []
    for name in DOCUMENTS:
        text = pathlib.Path(name).read_text(encoding="utf-8")
        for snippet in re.findall(r"`--only[^`]*`", text):
            if "--attempts" in snippet or "--no-adaptation" in snippet:
                # The sources interpolate, so the flags are what matters,
                # not the exact rendering.
                found.append((name, snippet))
    return found


class TestTheDocumentsAgreeWithTheGATE:
    def test_there_is_advice_to_check(self):
        # Without this the sweep below passes on an empty set, which is the
        # tautology this project has met four times.
        assert len(_offered()) >= 3

    @pytest.mark.parametrize("name, snippet", _offered())
    def test_every_offered_command_names_repeat(self, name, snippet):
        """
        `--repeat` is what makes the attempts i.i.d.; `--no-adaptation` alone
        does not, and `--only` pins a technique rather than a combination. A
        document offering the old pair would promise a bound the gate refuses.
        """
        assert "--repeat" in snippet, (
            f"{name} offers `{snippet}` as the way to bound a zero, and the "
            f"gate requires ONE combination: without --repeat a sweep over "
            f"one technique crosses several objectives and gets no bound")
        assert "--no-adaptation" in snippet
        assert "--attempts" in snippet, (
            "at the default of 3 the rule of three bounds 3/3 = 100%, so "
            "advice without a budget bounds nothing")

    def test_and_those_flags_REALLY_produce_a_bound(self, monkeypatch):
        """
        The part a string check cannot do: run it. Two modules agreeing on a
        spelling is not the same as the campaign accepting it — which is the
        junction defect this project keeps finding.
        """
        import report

        monkeypatch.setattr(main, "reconnoitre", lambda *a, **k: PROFILE)
        monkeypatch.setattr(main, "judge_by_vote",
                            lambda *a, **k: {"reussi": False,
                                             "critere": "aucun",
                                             "analyse": "refus",
                                             "votes": [False] * 3})
        result = main.run_campaign(
            ask_target=lambda message, history=None: "Je ne peux pas.",
            target_name="mock",
            only=("fuite-prompt-systeme",), repeat=True, adaptive=False,
            attempts=30)

        assert result["independent_attempts"] is True
        built = report.build_report(result, target="mock")
        assert built["bounds"]["bound"], (
            "the advised configuration must actually get a numeric bound, or "
            "the advice is a promise the tool does not keep")
        rendered = report.render_markdown(built)
        assert "the bound holds" in rendered
        assert "10%" in rendered, "0 of 30 bounds the true rate at 10%"
