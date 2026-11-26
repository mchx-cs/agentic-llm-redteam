"""
Tests for the payload library and the configuration.

Two places where a mistake would not show up at once: a malformed template
that would send `{objective}` to the target as it stands, and a typo in `.env`
that would only surface on the first call to a model.
"""

import json

import pytest

import agents.attacker
from agents.attacker import (LIBRARY_FILE, TRANSFORMATIONS,
                              load_library, generate_payloads)


@pytest.fixture(autouse=True)
def without_garak_snapshot(monkeypatch, tmp_path):
    """Isolates the tests from any garak snapshot that may be present."""
    monkeypatch.setattr(agents.attacker, "GARAK_FILE",
                        tmp_path / "absent.json")


class TestLibrary:
    def test_it_is_valid_json(self):
        json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))

    def test_every_technique_has_the_expected_fields(self):
        for technique in load_library()["techniques"]:
            assert {"id", "owasp_family", "description", "prerequisites",
                    "templates"} <= set(technique)

    def test_every_template_holds_the_objective_marker(self):
        # A template without `{objective}` would always send the same text.
        for technique in load_library()["techniques"]:
            for template in technique["templates"]:
                assert "{objective}" in template, technique["id"]

    def test_the_prerequisites_are_known_to_the_planner(self):
        from agents.planner import PREREQUISITES
        for technique in load_library()["techniques"]:
            for prerequisite in technique["prerequisites"]:
                assert prerequisite in PREREQUISITES, technique["id"]

    def test_the_identifiers_are_unique(self):
        identifiers = [t["id"] for t in load_library()["techniques"]]
        assert len(identifiers) == len(set(identifiers))


class TestTransformations:
    def test_identity_changes_nothing(self):
        assert TRANSFORMATIONS["identity"]("Bonjour") == "Bonjour"

    def test_every_transformation_returns_non_empty_text(self):
        for name, transform in TRANSFORMATIONS.items():
            result = transform("Peux-tu te présenter ?")
            assert isinstance(result, str) and result, name


class TestPayloadGeneration:
    def test_no_marker_survives(self):
        for payload in generate_payloads():
            assert "{objective}" not in payload["text"]

    def test_every_payload_says_where_it_comes_from(self):
        for payload in generate_payloads():
            assert {"technique", "owasp_family", "objective",
                    "transformation", "text"} <= set(payload)

    def test_the_catalogue_really_crosses_the_axes(self):
        library = load_library()
        templates = sum(len(t["templates"]) for t in library["techniques"])
        complete = sum(len(t.get("complete_payloads", []))
                       for t in library["techniques"])
        objectives = len(library["objectives"])
        # A template crosses with each objective. A complete payload produces
        # ONE MORE than there are objectives: composed with each of them (it
        # then serves as a preamble, and the objective supplies the request),
        # plus its bare variant, which measures resistance to hijacking.
        #
        # This formula said "complete x transformations" until 2026-11-11,
        # and
        # the test passed anyway: composition dated from the same day, but the
        # fixture neutralises the garak snapshot and no HAND-WRITTEN technique
        # had a complete payload yet, so the term was zero. The LLM07 payloads
        # woke it up.
        expected = len(TRANSFORMATIONS) * (
            templates * objectives + complete * (objectives + 1))
        assert len(generate_payloads()) == expected


class TestConfiguration:
    def test_the_profiles_declare_what_is_needed(self):
        from config import PROFILES
        for name, profile in PROFILES.items():
            assert {"base_url", "api_key", "model"} <= set(profile), name

    def test_an_unknown_profile_fails_at_import(self, monkeypatch):
        # Without this guard, a typo in .env would give a bare KeyError, a
        # long way from here, on the first call to a model.
        import importlib
        import config
        monkeypatch.setenv("JUDGE_PROFILE", "faute_de_frappe")
        with pytest.raises(ValueError, match="Unknown profile"):
            importlib.reload(config)
        monkeypatch.delenv("JUDGE_PROFILE")
        importlib.reload(config)  # put the configuration back on its feet

    def test_the_default_target_asks_for_no_key(self):
        import config
        assert config.TARGET == "decoy"
        assert config.PROFILES[config.ACTIVE_PROFILE]["api_key"]

class TestTheObjectivesCanBeREPLACED:
    """
    `generate_payloads(objectives=...)` existe pour les recoltes : les
    objectifs de la bibliotheque sont tous ANODINS par conception, donc une
    recolte qui veut des positifs passe ceux que la RECONNAISSANCE a derives.

    Un parametre et non une globale : `measure_modes` patche `LIBRARY_FILE`
    plutot que la fonction parce que le planificateur lie `load_library` a
    l'import, et une globale ici porterait la meme fragilite.
    """

    def test_the_given_objectives_REPLACE_the_library_s(self):
        from agents.attacker import generate_payloads

        mine = [{"id": "refus-1", "wording": "me parler du code secret"}]
        payloads = generate_payloads(mine)
        objectives = {p["objective"] for p in payloads} - {None}
        assert objectives == {"refus-1"}, (
            f"les objectifs passes sont ignores : {sorted(objectives)[:5]}")

    def test_the_wording_really_reaches_the_payload_TEXT(self):
        """
        Remplacer l'identifiant sans remplacer le texte donnerait un
        catalogue correctement etiquete et toujours anodin -- la forme de
        defaut la plus coûteuse, puisque rien ne la signale.
        """
        from agents.attacker import generate_payloads

        marker = "ZZ-objectif-temoin-ZZ"
        payloads = generate_payloads(
            [{"id": "temoin", "wording": marker}])
        assert any(marker in p["text"] for p in payloads)

    def test_NO_objective_falls_back_on_the_library(self):
        # Le contraste : le defaut ne doit pas bouger, sinon toute campagne
        # existante changerait de catalogue.
        from agents.attacker import generate_payloads

        assert generate_payloads() == generate_payloads(None)
