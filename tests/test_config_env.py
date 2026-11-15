"""
Tests for the `.env` key names and their deprecation path.

A `.env` key is a configuration CONTRACT: the file is gitignored, so it lives
on machines this repository never sees and nothing here can migrate it. The
English names are what the documentation now shows; the French names keep
working, and say so.

The test that matters most is the parametrized one: it reads every key under
its OLD name and checks the value actually arrives where the code uses it.
Dropping a key from `LEGACY_ENV`, or forgetting to route one read through
`_from_env`, fails it — a map that merely lists names would prove nothing.
"""

import importlib

import pytest

import config

# new name -> (what to put in the environment, what the module must end up
# holding, where to read it). The reader is what makes this a wiring test and
# not a map test.
KEYS = {
    "TARGET": ("demo", "demo", lambda c: c.TARGET),
    "ACTIVE_PROFILE": ("groq", "groq", lambda c: c.ACTIVE_PROFILE),
    "JUDGE_PROFILE": ("groq", "groq", lambda c: c.JUDGE_PROFILE),
    "CALL_BUDGET": ("7", 7, lambda c: c.CALL_BUDGET),
    "TOKEN_BUDGET": ("9", 9, lambda c: c.TOKEN_BUDGET),
    "TARGET_HEADERS": ('{"X": "y"}', {"X": "y"},
                       lambda c: c.HTTP_TARGET["headers"]),
    "TARGET_BODY": ('{"q": "{message}"}', {"q": "{message}"},
                    lambda c: c.HTTP_TARGET["body"]),
    "TARGET_RESPONSE_PATH": ("a.b", "a.b",
                             lambda c: c.HTTP_TARGET["response_path"]),
    "TARGET_TIMEOUT": ("3", 3.0, lambda c: c.HTTP_TARGET["timeout"]),
}


@pytest.fixture(autouse=True)
def configuration_put_back():
    """
    Every test here reloads `config`, which reads the environment. Without
    this, a probe value would leak into the tests that follow.
    """
    yield
    importlib.reload(config)


@pytest.mark.parametrize("new", sorted(KEYS))
def test_the_old_french_name_still_works(new, monkeypatch):
    probe, expected, read = KEYS[new]
    monkeypatch.setenv(config.LEGACY_ENV[new], probe)
    reloaded = importlib.reload(config)
    assert read(reloaded) == expected


@pytest.mark.parametrize("new", sorted(KEYS))
def test_the_english_name_works(new, monkeypatch):
    probe, expected, read = KEYS[new]
    monkeypatch.setenv(new, probe)
    reloaded = importlib.reload(config)
    assert read(reloaded) == expected


class TestWhenBothAreSet:
    def test_the_new_name_wins(self, monkeypatch):
        # Someone adding the new line to an old .env means it to take effect:
        # the stale line is the one they are in the middle of replacing.
        monkeypatch.setenv("CIBLE", "leurre")
        monkeypatch.setenv("TARGET", "demo")
        assert importlib.reload(config).TARGET == "demo"

    def test_and_nothing_is_reported_as_stale(self, monkeypatch, capsys):
        monkeypatch.setenv("CIBLE", "leurre")
        monkeypatch.setenv("TARGET", "demo")
        importlib.reload(config)
        assert "CIBLE" not in capsys.readouterr().err


class TestTheNoteToTheOperator:
    def test_an_old_key_is_named_with_its_replacement(self, monkeypatch,
                                                      capsys):
        monkeypatch.setenv("PROFIL_ARBITRE", "groq")
        importlib.reload(config)
        assert "PROFIL_ARBITRE -> JUDGE_PROFILE" in capsys.readouterr().err

    def test_it_goes_to_stderr_and_not_to_stdout(self, monkeypatch, capsys):
        # A report is piped to a file; a note about the configuration has no
        # business inside it.
        monkeypatch.setenv("PROFIL_ARBITRE", "groq")
        importlib.reload(config)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err != ""

    def test_a_current_env_says_nothing_at_all(self, monkeypatch, capsys):
        monkeypatch.setenv("JUDGE_PROFILE", "groq")
        importlib.reload(config)
        assert capsys.readouterr().err == ""


class TestWhatTheMapMustNotContain:
    def test_no_provider_key_was_renamed(self):
        """
        OPENAI_API_KEY and friends were never French, and two of them follow
        the provider's own convention. Renaming one would break a key that
        users set from a provider's console, for no gain at all.
        """
        for name in ("OPENAI_API_KEY", "OPENAI_MODEL",
                     "GROQ_API_KEY", "GROQ_MODEL"):
            assert name not in config.LEGACY_ENV
            assert name not in config.LEGACY_ENV.values()

    def test_the_two_sides_do_not_overlap(self):
        # A name that was both an old and a new key would resolve to itself
        # and hide a real rename.
        assert not set(config.LEGACY_ENV) & set(config.LEGACY_ENV.values())
