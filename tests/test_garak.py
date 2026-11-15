"""
Tests for the garak source: translating a probe and merging the snapshot.

No call to garak here, and that is the point: the project must work
IDENTICALLY with or without a snapshot. The snapshot is optional by
construction — so we build test snapshots by hand.
"""

import json

import pytest

import agents.attacker
from agents.attacker import _technique_from_probe, load_library
from payloads.garak_export import main as exporter
from payloads.garak_source import OUT_OF_SCOPE
from payloads.validate import validate


def _probe(name="probes.dan.DanInTheWild", owasp_families=("owasp:llm01",),
           payloads=("prompt un", "prompt deux")):
    return {"probe": name, "objective": "disregard the system prompt",
            "owasp_families": list(owasp_families), "language": "en", "doc": "",
            "payloads": list(payloads), "payloads_available": len(payloads)}


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    """Installs a garak snapshot built for the test."""
    def installer(probes):
        path = tmp_path / "garak.json"
        path.write_text(json.dumps({
            "garak_version": "0.17.1", "exported_at": "2026-11-10T00:00:00",
            "probes": probes, "skipped": []}), encoding="utf-8")
        monkeypatch.setattr(agents.attacker, "GARAK_FILE", path)
        return path
    return installer


@pytest.fixture
def without_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(agents.attacker, "GARAK_FILE",
                        tmp_path / "absent.json")


class TestTranslatingAProbe:
    def test_the_identifier_follows_the_projects_format(self):
        # Le validateur impose minuscules, chiffres et tirets.
        technique = _technique_from_probe(_probe())
        assert technique["id"] == "garak-dan-daninthewild"

    @pytest.mark.parametrize("tag, family, prerequisite", [
        ("owasp:llm01", "LLM01:2025 Prompt Injection", []),
        ("owasp:llm02", "LLM02:2025 Sensitive Information Disclosure",
         ["secret"]),
    ])
    def test_the_owasp_tag_gives_the_family_and_the_prerequisite(
            self, tag, family, prerequisite):
        # garak already carries the OWASP mapping: we do not guess it.
        # A probe from a module with NO prerequisite of its own, to isolate
        # this source from the other (see TestRelevancePerModule).
        technique = _technique_from_probe(
            _probe(name="probes.encoding.InjectBase64", owasp_families=[tag]))
        assert technique["owasp_family"] == family
        assert technique["prerequisites"] == prerequisite


class TestRelevancePerModule:
    """
    Deux sources de prérequis, qui ne disent PAS la même chose et se cumulent :
    la famille OWASP dit ce que l'attaque CHERCHE (un secret, des consignes),
    le module garak ce qu'elle EXIGE du contexte (du code, un terminal).

    Jusqu'au 2026-11-11 seule la première existait, et comme `owasp:llm01`
    n'exige rien, 73 % des payloads (845/1 143) partaient contre n'importe
    quelle cible — « print ANSI terminal codes » compris, contre un chatbot
    de bibliothèque.
    """

    @pytest.mark.parametrize("module, prerequisite", [
        ("dan", "instructions"),
        ("phrasing", "instructions"),
        ("sata", "instructions"),
        ("packagehallucination", "writes-code"),
        ("latentinjection", "handles-documents"),
        ("ansiescape", "terminal"),
        ("web_injection", "rich-rendering"),
        ("exploitation", "database"),
    ])
    def test_the_module_imposes_its_prerequisite(self, module, prerequisite):
        technique = _technique_from_probe(_probe(name=f"probes.{module}.X"))
        assert prerequisite in technique["prerequisites"]

    @pytest.mark.parametrize("module", ["encoding", "goodside", "promptinject"])
    def test_a_universal_module_demands_nothing(self, module):
        # The right default: these probes apply to any model. Adding a
        # prerequisite "as a precaution" would cost an undiscovered
        # vulnerability, which is worse than a wasted attempt.
        technique = _technique_from_probe(_probe(name=f"probes.{module}.X"))
        assert technique["prerequisites"] == []

    def test_the_two_sources_add_up(self):
        # `dan` exige des consignes, `owasp:llm02` un secret : les deux.
        technique = _technique_from_probe(
            _probe(name="probes.dan.DanInTheWild", owasp_families=["owasp:llm02"]))
        assert technique["prerequisites"] == ["instructions", "secret"]

    def test_the_group_and_the_prerequisite_read_the_same_module(self):
        # One place only knows how to extract a module from a probe name:
        # if the two drifted apart, the round-robin and the relevance rules
        # would no longer be talking about the same thing.
        technique = _technique_from_probe(
            _probe(name="probes.web_injection.MarkdownXSS"))
        assert technique["group"] == "web_injection"
        assert "rich-rendering" in technique["prerequisites"]

    @pytest.mark.parametrize("tag, family", [
        ("owasp:llm05", "LLM05:2025 Improper Output Handling"),
        ("owasp:llm06", "LLM06:2025 Excessive Agency"),
        ("owasp:llm09", "LLM09:2025 Misinformation"),
    ])
    def test_a_family_the_judge_cannot_score_is_logged_apart(
            self, tag, family):
        # Verified 2026-11-11: garak also tags 10 llm06 probes, 7 llm09
        # and 2 llm05. They genuinely ARE launched (each also carries llm01
        # or llm02), but announcing "LLM06 tested" would be false, since the
        # judge has no criterion for those families. Neither tested nor
        # ignored: touched.
        technique = _technique_from_probe(
            _probe(owasp_families=["owasp:llm01", tag]))
        assert technique["owasp_family"] == "LLM01:2025 Prompt Injection"
        assert technique["families_not_scorable"] == [family]

    def test_owasp_llm07_is_no_longer_promised(self):
        # A dead entry removed on 2026-11-11: no probe in the snapshot
        # carries that tag. A mapping promising a family the source does not
        # supply suggests a coverage that does not exist.
        from agents.attacker import GARAK_FAMILIES
        assert "owasp:llm07" not in GARAK_FAMILIES
        technique = _technique_from_probe(_probe(owasp_families=["owasp:llm07"]))
        assert technique["owasp_family"] is None

    def test_the_prompts_go_in_payloads_complets_not_in_modeles(self):
        # These are whole prompts: without `{objective}` they would fail
        # validation if they landed in `modeles`.
        technique = _technique_from_probe(_probe())
        assert technique["templates"] == []
        assert technique["complete_payloads"] == ["prompt un", "prompt deux"]

    def test_the_provenance_is_kept(self):
        # Pour que le rapport puisse citer la sonde d'origine.
        assert _technique_from_probe(_probe())["source"] == \
               "garak probes.dan.DanInTheWild"

    def test_a_translated_probe_passes_the_validator(self):
        library = {"techniques": [_technique_from_probe(_probe())],
                        "objectives": [{"id": "o", "wording": "f"}]}
        assert validate(library)[0] == []


class TestMerging:
    def test_without_a_snapshot_the_library_is_unchanged(self, without_snapshot):
        # The repository must run exactly as before for anyone who does
        # synchronise pas.
        assert "_garak" not in load_library()

    def test_with_a_snapshot_the_probes_are_added(self, snapshot):
        snapshot([_probe(), _probe(name="probes.encoding.InjectBase64")])
        library = load_library()
        identifiants = {t["id"] for t in library["techniques"]}
        assert "garak-dan-daninthewild" in identifiants
        assert "garak-encoding-injectbase64" in identifiants
        # The hand-written techniques stay present.
        assert "controle" in identifiants

    def test_garaks_version_is_logged(self, snapshot):
        # A campaign must stay attachable to a version of the source.
        snapshot([_probe()])
        assert load_library()["_garak"]["version"] == "0.17.1"

    def test_with_garak_can_be_switched_off(self, snapshot):
        snapshot([_probe()])
        assert "_garak" not in load_library(with_garak=False)

    def test_the_merged_library_stays_valid(self, snapshot):
        snapshot([_probe(), _probe(name="probes.leakreplay.Guardrail",
                                     owasp_families=["owasp:llm02"])])
        assert validate(load_library())[0] == []


class TestFreshness:
    """
    garak publie environ tous les 37 jours (médiane mesurée le 2026-11-10 sur
    ses douze dernières versions). Un instantané vieux de plusieurs mois a
    donc manqué des sondes — on le signale sans rien bloquer.
    """

    def _snapshot_dated(self, snapshot, jours):
        from datetime import datetime, timedelta
        import json as _json
        path = snapshot([_probe()])
        contenu = _json.loads(path.read_text(encoding="utf-8"))
        contenu["exported_at"] = (
            datetime.now() - timedelta(days=jours)).isoformat(timespec="seconds")
        path.write_text(_json.dumps(contenu), encoding="utf-8")

    def test_the_age_is_computed(self, snapshot):
        self._snapshot_dated(snapshot, 42)
        assert load_library()["_garak"]["age_days"] == 42

    def test_a_recent_snapshot_triggers_nothing(self, snapshot):
        self._snapshot_dated(snapshot, 3)
        avertissements = validate(load_library())[1]
        assert not any("vieux de" in a for a in avertissements)

    def test_an_old_snapshot_is_reported(self, snapshot):
        self._snapshot_dated(snapshot, 95)
        avertissements = validate(load_library())[1]
        assert any("95 days old" in a for a in avertissements)

    def test_an_unreadable_date_does_not_bring_the_load_down(
            self, snapshot, monkeypatch):
        import json as _json
        path = snapshot([_probe()])
        contenu = _json.loads(path.read_text(encoding="utf-8"))
        contenu["exported_at"] = "pas une date"
        path.write_text(_json.dumps(contenu), encoding="utf-8")
        assert load_library()["_garak"]["age_days"] is None


class TestEmptyExport:
    def test_an_export_with_no_probe_does_not_replace_the_snapshot(
            self, monkeypatch, tmp_path):
        """
        Si garak réorganise son API privée, la collecte peut ne plus rien
        ramener SANS lever d'exception. Écraser alors l'instantané priverait
        les campagnes de leurs payloads, et un « aucun constat » passerait
        pour un bon résultat.
        """
        import sys
        import types

        import payloads.garak_export as module
        faux = types.ModuleType("garak")
        faux.__version__ = "0.17.1"
        monkeypatch.setitem(sys.modules, "garak", faux)
        monkeypatch.setattr(module, "collect",
                            lambda **k: ([], [{"name": "x", "reason": "y"}]))

        output = tmp_path / "garak.json"
        assert exporter(["--sortie", str(output)]) == 1
        assert not output.exists()


class TestVersionDetection:
    """
    On DÉTECTE qu'une mise à jour existe ; on ne la fait pas. Automatiser la
    mise à jour casserait la reproductibilité (deux campagnes identiques
    doivent envoyer les mêmes payloads), exigerait les 164 dépendances de
    garak dans le venv du projet, téléchargerait des gigaoctets pendant une
    mission, et enverrait à la cible du contenu non relu.
    """

    @pytest.mark.parametrize("local, remote, expected", [
        ("0.17.1", "0.18.0", True),
        ("0.9.0", "0.17.1", True),      # numeric comparison, not textual
        ("0.17.1", "0.17.1", False),
        ("0.18.0", "0.17.1", False),
    ])
    def test_being_behind_is_detected(self, monkeypatch, local, remote,
                                   expected):
        import payloads.garak_source as source
        monkeypatch.setattr(source, "latest_version", lambda timeout=10: remote)
        assert source.compare_to_snapshot(local)[1] is expected

    def test_an_unavailable_network_blocks_nothing(self, monkeypatch):
        # A campaign must not depend on GitHub.
        import payloads.garak_source as source
        monkeypatch.setattr(source, "_fetch",
                            lambda *a, **k: (_ for _ in ()).throw(
                                RuntimeError("hors ligne")))
        assert source.latest_version() is None
        assert source.compare_to_snapshot("0.17.1") == (None, False)


class TestRedundancyWithGarak:
    """
    Deux techniques du dépôt sont écrites à la main parce que garak ne
    fournit aucune sonde pour leur famille : LLM07 (11 payloads) et LLM06
    (4 payloads). Des payloads maison pourrissent et leur entretien retombe
    sur une seule personne — c'est l'argument même qui a fait choisir garak
    comme source synchronisée. Donc le jour où garak comble le trou, il faut
    le SAVOIR.

    Détection automatique, décision humaine : le principe déjà retenu pour la
    resynchronisation. Rien n'est retiré tout seul.
    """

    def _library(self, garak_families=(), maison=()):
        techniques = [{"id": f"garak-{i}", "source": "garak",
                       "owasp_family": family, "complete_payloads": ["x"]}
                      for i, family in enumerate(garak_families)]
        techniques += list(maison)
        return {"techniques": techniques}

    def test_nothing_to_report_with_todays_families(self, snapshot):
        # The state measured on 2026-11-12: the 52 probes in scope carry
        # LLM01 or LLM02 as their primary family, never LLM06 or LLM07. The
        # two hand-written techniques therefore remain alone in covering
        # theirs.
        #
        # The snapshot is BUILT for the test, as everywhere in this file: a
        # test reading the local snapshot would pass or not depending on
        # whether the exporter had been run.
        from payloads.garak_source import redundant_techniques
        snapshot([_probe(owasp_families=("owasp:llm01",)),
                    _probe(name="probes.leakreplay.Fake",
                           owasp_families=("owasp:llm02",))])
        assert redundant_techniques(load_library()) == []

    def test_a_probe_that_fills_the_hole_is_reported(self):
        from payloads.garak_source import redundant_techniques
        library = self._library(
            garak_families=["LLM06:2025 Excessive Agency"],
            maison=[{"id": "abus-outils",
                     "owasp_family": "LLM06:2025 Excessive Agency",
                     "templates": ["a", "b"]}])
        reported = redundant_techniques(library)
        assert [t["id"] for t in reported] == ["abus-outils"]
        assert reported[0]["payloads"] == 2
        assert reported[0]["probes"] == 1

    def test_the_owasp_vintage_does_not_come_into_it(self):
        # The match is on `LLM06`, not on the full label: making the rule
        # depend on the vintage would break it at the Top 10's next
        # revision.
        from payloads.garak_source import redundant_techniques
        library = self._library(
            garak_families=["LLM06:2027 Excessive Agency"],
            maison=[{"id": "abus-outils",
                     "owasp_family": "LLM06:2025 Excessive Agency",
                     "templates": ["a"]}])
        assert len(redundant_techniques(library)) == 1

    def test_another_family_triggers_nothing(self):
        from payloads.garak_source import redundant_techniques
        library = self._library(
            garak_families=["LLM01:2025 Prompt Injection"],
            maison=[{"id": "abus-outils",
                     "owasp_family": "LLM06:2025 Excessive Agency",
                     "templates": ["a"]}])
        assert redundant_techniques(library) == []

    def test_a_secondary_family_fills_no_hole(self):
        # Ten probes carry `owasp:llm06` as a SECONDARY tag, and they aim at
        # the application around the model — exfiltration through a Markdown
        # URI, XSS, Jinja or SQL injection — not at tool calls. Counting them
        # here would announce a hole filled that is not, and would have four
        # payloads removed that test something else.
        from payloads.garak_source import redundant_techniques
        library = {"techniques": [
            {"id": "garak-web", "source": "garak",
             "owasp_family": "LLM02:2025 Sensitive Information Disclosure",
             "families_not_scorable": ["LLM06:2025 Excessive Agency"],
             "complete_payloads": ["x"]},
            {"id": "abus-outils",
             "owasp_family": "LLM06:2025 Excessive Agency",
             "templates": ["a"]}]}
        assert redundant_techniques(library) == []

    def test_an_empty_hand_written_technique_is_not_reported(self):
        # `divulgation-information` is empty: there is nothing to remove,
        # and the planner already reports its lack of payload. Reporting it
        # here would drown the one case that needs a decision.
        from payloads.garak_source import redundant_techniques
        library = self._library(
            garak_families=["LLM02:2025 Sensitive Information Disclosure"],
            maison=[{"id": "divulgation-information",
                     "owasp_family": "LLM02:2025 Sensitive Information "
                                      "Disclosure",
                     "templates": []}])
        assert redundant_techniques(library) == []

    def test_the_harmless_control_is_never_redundant(self):
        # `controle` has no OWASP family: it is the control, and no
        # sonde offensive ne le remplace.
        from payloads.garak_source import redundant_techniques
        library = self._library(
            garak_families=["LLM01:2025 Prompt Injection"],
            maison=[{"id": "controle", "owasp_family": None,
                     "templates": ["bonjour"]}])
        assert redundant_techniques(library) == []

    def test_a_garak_probe_is_not_a_hand_written_debt(self):
        from payloads.garak_source import redundant_techniques
        library = self._library(
            garak_families=["LLM01:2025 Prompt Injection",
                            "LLM01:2025 Prompt Injection"])
        assert redundant_techniques(library) == []


class TestProvenanceInTheReport:
    def _report(self, payloads):
        from report import build_report, render_markdown
        return render_markdown(build_report({
            "status": "no_finding", "profile": None,
            "plan": {"attempts": [], "skipped": []}, "findings": [],
            "call_log": {}, "cut_short": None, "payloads": payloads},
            target="attempt"))

    def test_the_report_says_what_it_tested_with(self):
        text = self._report({"version": "0.17.1", "probes": 52,
                               "age_days": 3, "stale": False})
        assert "garak 0.17.1" in text and "52 probe(s)" in text

    def test_an_ageing_library_is_reported(self):
        # A "no finding" obtained with three-month-old payloads does not say
        # not the same thing as with payloads from today.
        text = self._report({"version": "0.14.0", "probes": 48,
                               "age_days": 94, "stale": True})
        assert "Ageing library" in text

    def test_without_a_snapshot_no_stray_line(self):
        assert "Payloads :" not in self._report(None)


class TestScope:
    def test_the_out_of_scope_subjects_are_named(self):
        # They measure the model's moderation, not its resistance to
        # injection, and the judge has no criterion to score them.
        assert "harmful_behaviors.json" in OUT_OF_SCOPE
        assert all(raison for raison in OUT_OF_SCOPE.values())
