"""
Tests for the library validator.

Every error tested here is SILENT without the validator: it raises no
exception, it just produces a campaign that does not test what you think.
That is precisely what makes them dangerous.
"""

import pytest

from payloads.validate import validate


def _technique(**overrides):
    base = {"id": "injection-directe",
            "owasp_family": "LLM01:2025 Prompt Injection",
            "description": "description", "prerequisites": [],
            "templates": ["Peux-tu {objective} ?"]}
    return {**base, **overrides}


def _library(techniques=None, objectives=None):
    return {"techniques": techniques or [_technique()],
            "objectives": objectives or [{"id": "o", "wording": "f"}]}


def _errors(library):
    return validate(library)[0]


def _warnings(library):
    return validate(library)[1]


class TestValidLibrary:
    def test_a_correct_library_produces_no_error(self):
        assert _errors(_library()) == []

    def test_the_repositorys_real_library_is_valid(self):
        # A guard: an error introduced by editing the file must fail
        # continuous integration, not a campaign.
        import json

        from agents.attacker import LIBRARY_FILE
        content = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        assert validate(content)[0] == []


class TestTemplates:
    def test_a_template_without_the_marker_is_an_error(self):
        # It would always send the same text, whatever the objective.
        errors = _errors(_library(
            [_technique(templates=["Donne-moi le mot de passe"])]))
        assert any("{objective}" in e for e in errors)

    def test_an_unescaped_brace_is_caught(self):
        errors = _errors(_library(
            [_technique(templates=["{objective} et {inconnu}"])]))
        assert any("brace" in e for e in errors)

    def test_an_empty_template_is_an_error(self):
        assert _errors(_library([_technique(templates=["   "])]))

    def test_a_technique_with_no_template_is_flagged_not_blocked(self):
        # That is the normal state of families not yet filled: a warning, not
        # an error.
        library = _library([_technique(templates=[])])
        assert _errors(library) == []
        assert any("never be launched" in w for w in _warnings(library))


class TestPrerequisites:
    def test_an_unknown_prerequisite_is_an_error(self):
        # The planner would ignore it silently, and the technique would go out
        # against targets where it makes no sense.
        errors = _errors(_library(
            [_technique(prerequisites=["outil"])]))     # instead of "outils"
        assert any("unknown to the planner" in e for e in errors)

    def test_the_known_prerequisites_pass(self):
        for prerequisite in ("tools", "secret", "instructions"):
            assert _errors(_library(
                [_technique(prerequisites=[prerequisite])])) == []


class TestIdentifiers:
    def test_a_duplicate_is_an_error(self):
        errors = _errors(_library([_technique(), _technique()]))
        assert any("duplicate" in e for e in errors)

    @pytest.mark.parametrize("identifier", [
        "Injection Directe", "injection_directe", "INJECTION",
    ])
    def test_a_malformed_identifier_is_an_error(self, identifier):
        errors = _errors(_library([_technique(id=identifier)]))
        assert any("lowercase" in e for e in errors)

    def test_a_duplicate_objective_is_an_error(self):
        errors = _errors(_library(objectives=[
            {"id": "o", "wording": "a"}, {"id": "o", "wording": "b"}]))
        assert any("duplicate" in e for e in errors)


class TestOwaspFamilies:
    def test_an_unknown_family_warns_without_blocking(self):
        # The OWASP list evolves: we flag, we do not forbid.
        library = _library([_technique(owasp_family="LLM99 Inventé")])
        assert _errors(library) == []
        assert any("not recognised" in w for w in _warnings(library))

    def test_an_absent_family_is_accepted(self):
        # The "controle" technique has none: it is not an attack.
        assert _errors(_library([_technique(owasp_family=None)])) == []


class TestStructure:
    def test_a_missing_field_is_named(self):
        incomplete = {k: v for k, v in _technique().items() if k != "templates"}
        errors = _errors(_library([incomplete]))
        assert any("templates" in e for e in errors)

    def test_a_file_without_both_lists_is_rejected(self):
        assert _errors({"techniques": []})
