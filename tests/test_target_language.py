"""
Tests for the probe LANGUAGE (2026-11-25).

French only until then, so every profile of an English-speaking target was
built on an exchange opened in French — and probing is the first thing this
tool does.

Its own file because the feature spans `reconnaissance` and the orchestrator:
`test_cli_wiring.py` parses source without executing it, and driving
`main.cli` there would break its premise.

No model is involved: reconnaissance and the judge are replaced.
"""

import pytest

PROFILE = {"role": "assistant", "language": "fr", "tools": [],
           "refused_subjects": ["le code du fonds ancien"],
           "mentions_instructions": True,
           "writes_code": None, "handles_documents": None, "context": [],
           "evidence": [], "exchanges": [], "warning": None}


def _no_breach(*_, **__):
    return {"reussi": False, "critere": "aucun", "analyse": "refus",
            "votes": [False, False, False]}


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge", "agents.reconnaissance"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


@pytest.fixture(autouse=True)
def no_garak(monkeypatch, tmp_path):
    monkeypatch.setenv("GARAK_FILE", str(tmp_path / "absent.json"))


class TestTheLANGUAGEReachesTheProbes:
    """
    The CLI-to-campaign junction for `--target-language`, DRIVEN and never
    read from source.

    This project has met that defect nine times — a flag parsed correctly and
    never reaching the call — and a mutation cutting the argument out of
    `run_campaign`'s invocation broke nothing at all until this class existed.
    """

    def test_the_flag_reaches_reconnaissance(self, monkeypatch, tmp_path):
        import main
        seen = {}

        def spy(ask, language="fr"):
            seen["language"] = language
            return dict(PROFILE)

        monkeypatch.setattr(main, "reconnoitre", spy)
        monkeypatch.setattr(main, "judge_by_vote", _no_breach)
        main.cli(["--target", "mock", "--target-language", "en",
                  "--attempts", "1", "--only", "fuite-prompt-systeme"])
        assert seen["language"] == "en"

    def test_and_FRENCH_is_what_an_unflagged_run_sends(self, monkeypatch):
        # The contrast: without it the test above would pass on a campaign
        # that always probed in English.
        import main
        seen = {}

        def spy(ask, language="fr"):
            seen["language"] = language
            return dict(PROFILE)

        monkeypatch.setattr(main, "reconnoitre", spy)
        monkeypatch.setattr(main, "judge_by_vote", _no_breach)
        main.cli(["--target", "mock", "--attempts", "1",
                  "--only", "fuite-prompt-systeme"])
        assert seen["language"] == "fr"

    def test_an_unknown_code_is_refused_by_the_PARSER(self, capsys):
        # Before anything is spent: argparse's `choices`, so the message
        # names the valid codes.
        import main
        with pytest.raises(SystemExit):
            main.cli(["--target", "mock", "--target-language", "de"])
        assert "de" in capsys.readouterr().err

