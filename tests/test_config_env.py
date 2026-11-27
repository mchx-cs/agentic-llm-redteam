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

import os
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
    "TARGET_TRANSPORT": ("get", "get",
                         lambda c: c.HTTP_TARGET["transport"]),
    "TARGET_URL_LIMIT": ("8000", 8000,
                         lambda c: c.HTTP_TARGET["url_limit"]),
    "TARGET_WS_QUIET": ("0.5", 0.5, lambda c: c.HTTP_TARGET["ws_quiet"]),
}


def test_the_three_transport_keys_default_to_NONE():
    """
    Unset, they must be None rather than a number.

    The defaults live in `targets/http.py`, beside the code that explains
    why 2,000 characters and why 2 seconds. Restating them here would be two
    definitions of one figure, and the one that drifts is always the copy.
    """
    for key in ("transport", "url_limit", "ws_quiet"):
        assert config.HTTP_TARGET[key] is None, (
            f"{key} unset must be None: the default belongs to the adapter")


@pytest.fixture(autouse=True)
def configuration_put_back():
    """
    Every test here reloads `config`, which reads the environment. Without
    this, a probe value would leak into the tests that follow.
    """
    yield
    importlib.reload(config)


#: Keys born AFTER the switch to English of 2026-11-15, so with no French
#: predecessor to keep working. Listed rather than skipped silently: the
#: point of the table is that every key is wired, and "this one has no old
#: name" is a fact about its age, not a gap in the test.
BORN_IN_ENGLISH = {"TARGET_TRANSPORT", "TARGET_URL_LIMIT", "TARGET_WS_QUIET"}


def _supplied_by_the_env_file():
    """
    Les noms de cle que le `.env` du depot pose, OBSERVES et non reparses.

    `_load_env_file` relit le fichier a CHAQUE reload et y fait
    `os.environ.setdefault`, donc vider `os.environ` ne suffit pas : ce qui
    s'y retrouve apres un reload a environnement vide vient du FICHIER. La
    fixture `no_ambient_config` garantit cet environnement vide.

    Observer plutot que reparser : un second analyseur de `.env` divergerait
    du premier a la premiere retouche, la derive par duplication que ce projet
    refuse partout ou une regle est redite au lieu d'etre lue.
    """
    importlib.reload(config)
    names = set(KEYS) | set(config.LEGACY_ENV.values())
    return {name for name in names if name in os.environ}


@pytest.fixture(autouse=True)
def no_ambient_config(monkeypatch):
    """
    Chaque test de ce fichier part d'un environnement SANS cle de
    configuration, et c'est ce qui rend ses assertions lisibles.

    LE DEFAUT QU'IL FERME, trouve le 2026-11-27 en renommant
    `PROFIL_ARBITRE` -> `JUDGE_PROFILE` dans le `.env` de l'auteur : `config`
    charge le `.env` dans `os.environ`, donc un test qui posait la cle
    HERITEE voyait aussi le nom NEUF, le nom neuf gagnait, et la note de
    depreciation ne partait plus. Les deux tests de la note etaient verts
    PARCE QUE la configuration etait perimee.

    Et le cas qui ne tombait pas est le pire : la sonde de `JUDGE_PROFILE`
    vaut "groq", la valeur qu'un vrai `.env` porte, donc le test du nom
    francais passait que le chemin herite marche ou que l'ambiant gagne.

    La liste est DERIVEE de `KEYS` et de `config.LEGACY_ENV` : une liste
    ecrite a la main est l'endroit ou la cle genante se perd.
    """
    for name in set(KEYS) | set(config.LEGACY_ENV.values()):
        monkeypatch.delenv(name, raising=False)


def test_the_fixture_leaves_NO_config_key_posed():
    """
    La propriete que `no_ambient_config` tient, et ce test est ce qui lui
    fait gagner sa place : un balayage de mutations l'a d'abord lue MUETTE.

    Sans elle, l'import initial de `config` a deja mis le `.env` dans
    `os.environ`, donc ce qu'un test POSE n'est pas ce que `config` VOIT. Les
    deux tests de la note vivaient exactement la : ils etaient verts parce que
    la configuration de l'auteur etait perimee.

    Et c'est aussi ce qui rend le nom de `_supplied_by_the_env_file` vrai --
    sans environnement vide au depart, il attribuerait au FICHIER une variable
    venue du shell, et sauterait un cas pour la mauvaise raison.
    """
    posed = {name for name in set(KEYS) | set(config.LEGACY_ENV.values())
             if name in os.environ}
    assert posed == set(), (
        f"un test de ce fichier demarre avec {sorted(posed)} deja pose(s) : "
        f"ce qu'il met dans l'environnement n'est pas ce que `config` lit, "
        f"et ses assertions ne disent plus ce qu'elles ont l'air de dire")


@pytest.mark.parametrize("new", sorted(set(KEYS) - BORN_IN_ENGLISH))
def test_the_old_french_name_still_works(new, monkeypatch, capsys):
    """
    LE SKIP EST HONNETE ET NON UN CONTOURNEMENT, trouve le 2026-11-27.

    Quand le `.env` du depot pose le nom NEUF, le chemin herite ne peut pas
    etre exerce : `_load_env_file` relit le fichier a chaque reload, le nom
    neuf est donc toujours la, et il gagne -- la precedence documentee, que
    `test_the_new_name_wins` couvre deja.

    Sans ce skip le cas passait TAUTOLOGIQUEMENT : la sonde de
    `JUDGE_PROFILE` vaut "groq", exactement ce qu'un vrai `.env` porte, donc
    l'assertion tenait que le chemin herite marche ou que l'ambiant gagne. Et
    une autre sonde ne le repare pas, elle le rend rouge en local et vert en
    CI.

    En CI il n'y a pas de `.env`, donc rien ne se saute : la couverture est
    pleine la ou elle compte.
    """
    supplied = _supplied_by_the_env_file()
    capsys.readouterr()
    if new in supplied:
        pytest.skip(
            f"le .env du depot pose {new}, donc le chemin herite est "
            f"inexercable ici : le fichier le repose a chaque reload et le "
            f"nom neuf gagne. Vert en CI, ou il n'y a pas de .env.")

    probe, expected, read = KEYS[new]
    monkeypatch.setenv(config.LEGACY_ENV[new], probe)
    reloaded = importlib.reload(config)
    assert read(reloaded) == expected


def test_and_the_newer_keys_never_HAD_a_french_name():
    """
    The other half, so the exemption cannot quietly grow: a key listed as
    born in English must really be absent from the migration table. Adding
    an OLD key to that set would hide a broken migration, which is the one
    thing this file exists to catch.
    """
    for key in BORN_IN_ENGLISH:
        assert key in KEYS, f"{key} is not a key at all"
        assert key not in config.LEGACY_ENV, (
            f"{key} does have an old name: it belongs in the migration test")


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
    """
    LE COUPLE EST DERIVE, et il etait code en dur jusqu'au 2026-11-27.

    Ces deux tests posaient `PROFIL_ARBITRE` et attendaient la note. Ils sont
    devenus rouges le jour ou le `.env` de l'auteur a ete CORRIGE -- parce que
    `_load_env_file` relit le fichier a CHAQUE reload et y fait
    `os.environ.setdefault`, donc un couple que le fichier porte voit son nom
    NEUF pose pendant le reload, le nom neuf gagne, et la note ne part plus.

    La note est donc intestable sur un couple que l'operateur a configure, et
    ce n'est pas un contournement : c'est un fait sur `config`. Vider
    `os.environ` n'y change rien -- le fichier le repeuple.

    Ils etaient donc verts PARCE QUE la configuration de l'auteur etait
    perimee. Et c'est la direction INVERSE de la lecon que ce projet
    enregistre quatre fois : ici le local etait plus riche que la CI et le
    test dependait de ce qu'il soit PERIME, donc vert en CI -- ou il n'y a
    pas de `.env` -- et rouge des que la configuration est reparee.
    """

    @staticmethod
    def _a_pair_the_file_cannot_supply(capsys):
        """
        Un couple (ancien, neuf, sonde) que le `.env` ne fournit pas.

        OBSERVE plutot que reparse : on recharge avec l'environnement vide --
        la fixture s'en charge -- et ce qui s'y retrouve vient du FICHIER. Un
        second analyseur de `.env` divergerait du premier a la premiere
        retouche, la derive par duplication que ce projet refuse partout.

        Restreint a `KEYS` pour avoir une sonde VALIDE : plusieurs cles sont
        lues en entier ou en flottant, et `int("sonde")` ferait echouer
        l'import pour une raison qui n'est pas celle du test.
        """
        supplied = _supplied_by_the_env_file()
        capsys.readouterr()               # sa note eventuelle ne compte pas
        for new, old in sorted(config.LEGACY_ENV.items()):
            if new in KEYS and new not in supplied and old not in supplied:
                return old, new, KEYS[new][0]
        raise AssertionError(
            "chaque couple herite est fourni par le .env, donc la note est "
            "intestable ici. Ce n'est pas un defaut de ce test : `config` "
            "relit le fichier a chaque reload et le nom neuf gagne.")

    def test_an_old_key_is_named_with_its_replacement(self, monkeypatch,
                                                      capsys):
        old, new, probe = self._a_pair_the_file_cannot_supply(capsys)
        monkeypatch.setenv(old, probe)
        importlib.reload(config)
        assert f"{old} -> {new}" in capsys.readouterr().err

    def test_it_goes_to_stderr_and_not_to_stdout(self, monkeypatch, capsys):
        # A report is piped to a file; a note about the configuration has no
        # business inside it.
        old, new, probe = self._a_pair_the_file_cannot_supply(capsys)
        monkeypatch.setenv(old, probe)
        importlib.reload(config)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert f"{old} -> {new}" in captured.err

    def test_a_current_env_says_nothing_at_all(self, monkeypatch, capsys):
        # L'assertion porte sur LE COUPLE pose, et non sur un stderr vide :
        # un `.env` qui porterait une autre cle heritee ferait partir la note
        # a son sujet, et ce test se mettrait au rouge pour quelque chose
        # qu'il ne mesure pas.
        monkeypatch.setenv("JUDGE_PROFILE", "groq")
        importlib.reload(config)
        assert "PROFIL_ARBITRE -> JUDGE_PROFILE" not in capsys.readouterr().err


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


class TestTheFileNamesThatAlsoMoved:
    """
    Two names outside `.env` are contracts of the same kind.

    The mandate file CANNOT be regenerated — it is a signed contract — and
    losing sight of it makes the tool refuse to start against a target it is
    perfectly authorised to test. The decoy's name has been in the README
    since the project existed.
    """

    def test_a_mandate_under_its_french_name_is_still_found(self, tmp_path):
        import json

        from audit import LEGACY_AUTHORISATION_FILE, load_authorisation

        mandate = {"target": "chatbot.client.fr", "authorised_by": "X",
                   "reference": "REF-1", "start": "2026-01-01",
                   "end": "2099-01-01"}
        (tmp_path / LEGACY_AUTHORISATION_FILE).write_text(
            json.dumps(mandate), encoding="utf-8")
        loaded = load_authorisation(tmp_path / "authorisation.json")
        assert loaded["reference"] == "REF-1"

    def test_a_missing_mandate_still_names_the_english_file(self, tmp_path):
        from audit import MissingAuthorisation, load_authorisation

        with pytest.raises(MissingAuthorisation, match="authorisation.json"):
            load_authorisation(tmp_path / "authorisation.json")

    def test_the_decoy_answers_to_both_names(self):
        from targets import choose_target
        assert choose_target("decoy") is choose_target("leurre")

    def test_the_kept_name_is_not_offered_as_a_choice(self):
        # Listing both in the help text would suggest two different targets.
        from targets import PUBLIC_TARGET_NAMES, choose_target
        assert "leurre" not in PUBLIC_TARGET_NAMES
        with pytest.raises(ValueError) as refusal:
            choose_target("nawak")
        assert "leurre" not in str(refusal.value)

    def test_the_kept_name_still_needs_no_mandate(self):
        # The guard that broke the one-command demo in November 2026: a
        # bundled target that ends up demanding an authorisation.
        from audit import is_local
        assert is_local("leurre") and is_local("decoy")
