"""
Tests for the payload library and the configuration.

Two places where a mistake would not show up at once: a malformed template
that would send `{objectif}` to the target as it stands, and a typo in `.env`
that would only surface on the first call to a model.
"""

import json

import pytest

import agents.attaquant
from agents.attaquant import (LIBRARY_FILE, TRANSFORMATIONS,
                              load_library, generate_payloads)


@pytest.fixture(autouse=True)
def without_garak_snapshot(monkeypatch, tmp_path):
    """Isolates the tests from any garak snapshot that may be present."""
    monkeypatch.setattr(agents.attaquant, "GARAK_FILE",
                        tmp_path / "absent.json")


class TestLibrary:
    def test_it_is_valid_json(self):
        json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))

    def test_every_technique_has_the_expected_fields(self):
        for technique in load_library()["techniques"]:
            assert {"id", "famille_owasp", "description", "prerequis",
                    "modeles"} <= set(technique)

    def test_every_template_holds_the_objective_marker(self):
        # A template without `{objectif}` would always send the same text.
        for technique in load_library()["techniques"]:
            for template in technique["modeles"]:
                assert "{objectif}" in template, technique["id"]

    def test_the_prerequisites_are_known_to_the_planner(self):
        from agents.planificateur import PREREQUISITES
        for technique in load_library()["techniques"]:
            for prerequisite in technique["prerequis"]:
                assert prerequisite in PREREQUISITES, technique["id"]

    def test_the_identifiers_are_unique(self):
        identifiers = [t["id"] for t in load_library()["techniques"]]
        assert len(identifiers) == len(set(identifiers))


class TestTransformations:
    def test_identity_changes_nothing(self):
        assert TRANSFORMATIONS["identite"]("Bonjour") == "Bonjour"

    def test_every_transformation_returns_non_empty_text(self):
        for name, transform in TRANSFORMATIONS.items():
            result = transform("Peux-tu te présenter ?")
            assert isinstance(result, str) and result, name


class TestPayloadGeneration:
    def test_no_marker_survives(self):
        for payload in generate_payloads():
            assert "{objectif}" not in payload["texte"]

    def test_every_payload_says_where_it_comes_from(self):
        for payload in generate_payloads():
            assert {"technique", "famille_owasp", "objectif",
                    "transformation", "texte"} <= set(payload)

    def test_the_catalogue_really_crosses_the_axes(self):
        library = load_library()
        templates = sum(len(t["modeles"]) for t in library["techniques"])
        complete = sum(len(t.get("payloads_complets", []))
                       for t in library["techniques"])
        objectives = len(library["objectifs"])
        # A template crosses with each objective. A complete payload produces
        # ONE MORE than there are objectives: composed with each of them (it
        # then serves as a preamble, and the objective supplies the request),
        # plus its bare variant, which measures resistance to hijacking.
        #
        # This formula said "complete × transformations" until 2026-11-11, and
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
            assert {"base_url", "api_key", "modele"} <= set(profile), name

    def test_an_unknown_profile_fails_at_import(self, monkeypatch):
        # Without this guard, a typo in .env would give a bare KeyError, a
        # long way from here, on the first call to a model.
        import importlib
        import config
        monkeypatch.setenv("PROFIL_ARBITRE", "faute_de_frappe")
        with pytest.raises(ValueError, match="Profil inconnu"):
            importlib.reload(config)
        monkeypatch.delenv("PROFIL_ARBITRE")
        importlib.reload(config)  # put the configuration back on its feet

    def test_the_default_target_asks_for_no_key(self):
        import config
        assert config.TARGET == "leurre"
        assert config.PROFILES[config.ACTIVE_PROFILE]["api_key"]
