"""
La mesure du rappel de la chaîne : son protocole, jamais ses chiffres.

Aucun appel à un modèle. Ce qui est tenu ici est ce qui doit être VRAI quoi
qu'un juge réponde : l'issue extraite du bon champ, le bras de contrôle gardé
à part, les clés qui invalident une reprise, et la jonction entre la ligne de
commande et la mesure.

Les chiffres eux-mêmes — rappel, intervalles, faux positifs — ne se vérifient
pas sans modèle, et un test qui les devinerait serait pire qu'absent. C'est la
frontière que ce projet trace entre `tests/` et `evaluation/`.
"""

import json
import pathlib

import pytest

from evaluation import measure_recall as recall
from targets.bench import DOORS


def _outcome(attempts_and_criteria, findings=None, requests=10):
    """Ce que `one_campaign` rend, en gabarit."""
    attempt_of = [a for a, _ in attempts_and_criteria]
    criteria = [c for _, c in attempts_and_criteria]
    return {
        "attempt_of": attempt_of,
        "criteria": criteria,
        "severities": ["medium"] * len(criteria),
        "findings": findings if findings is not None else len(criteria),
        "requests": requests,
    }


class TestTheOUTCOMEIsTheATTEMPTAndNotABoolean:
    """
    Le budget auquel la chaîne trouve est ce qu'un opérateur veut savoir pour
    choisir `MAX_ATTEMPTS`. Un « trouvé / pas trouvé » le perdrait, et c'est
    pour ça que `one_campaign` a gagné `attempt_of` le 2026-11-26.
    """

    def test_it_returns_the_attempt_of_the_RIGHT_criterion(self):
        out = _outcome([(2, "obeissance"), (5, "divulgation")])
        assert recall._first_correct(out, "divulgation") == 5

    def test_a_breach_with_ANOTHER_criterion_does_not_count(self):
        """
        Le point aveugle nommé le 2026-11-19 : une chaîne qui trouve toutes
        les infractions et nomme toujours le mauvais critère scorerait 100 %
        sur les trois figures que ce projet publie.
        """
        out = _outcome([(1, "abus_outils")])
        assert recall._first_correct(out, "divulgation") is None
        # Mais elle a bien trouve quelque chose, et l'ecart entre les deux EST
        # la confusion de critere.
        assert recall._first_any(out) == 1

    def test_no_finding_at_all_gives_None_and_not_zero(self):
        """
        None et pas 0 : la tentative 0 n'existe pas, et un 0 se lirait comme
        « trouvé avant d'avoir commencé ». Le même refus que `breach_turn`,
        qui vaut `null` sur un négatif.
        """
        out = _outcome([])
        assert recall._first_any(out) is None
        assert recall._first_correct(out, "divulgation") is None

    def test_a_finding_whose_attempt_is_unknown_is_not_counted(self):
        # Un result.json anterieur au champ rend None : le compter comme
        # trouve attribuerait une faille a une tentative inconnue.
        out = _outcome([(None, "divulgation")])
        assert recall._first_correct(out, "divulgation") is None


class TestTheCONTROLArmIsNeverPooledWithTheRest:

    def test_clean_carries_no_criterion(self):
        """
        Le bras de contrôle ne mesure pas un rappel, il mesure des faux
        positifs. Lui donner un critère le ferait entrer dans le tableau des
        rappels, et additionner les deux donnerait un chiffre qui ne répond à
        aucune des deux questions.
        """
        assert DOORS["clean"]["criterion"] is None

    def test_it_is_measured_FIRST(self):
        """
        Délibérément : si la mesure meurt en route, c'est le bras dont aucun
        autre module ne donne l'équivalent qu'on veut avoir en main.
        """
        assert recall.ORDER[0] == "clean"

    def test_every_door_is_in_the_order(self):
        assert set(recall.ORDER) == set(DOORS), (
            "une porte hors de ORDER ne serait jamais mesurée, en silence")

    def test_the_summary_reports_it_apart(self, capsys):
        rows = [
            {"door": "clean", "run": 1, "criterion": None, "found_at": None,
             "any_at": 3, "findings": 1, "criteria": ["divulgation"],
             "severities": ["medium"], "requests": 20},
            {"door": "secret", "run": 1, "criterion": "divulgation",
             "found_at": 2, "any_at": 2, "findings": 1,
             "criteria": ["divulgation"], "severities": ["high"],
             "requests": 20},
        ]
        recall.summarise(rows, {"declared": True}, campaigns=1, attempts=12)
        said = capsys.readouterr().out
        assert "CONTROL ARM" in said
        assert "1/1" in said, "le bras de controle doit montrer son taux"
        # Et il ne doit pas apparaitre dans le tableau des rappels.
        head, _, control = said.partition("CONTROL ARM")
        assert "clean" not in head


class TestTheDEPARTURESFromTheProtocolAreNamed:

    def test_nothing_changed_is_nothing_said(self):
        assert recall.departures_from_the_protocol() == []

    @pytest.mark.parametrize("field,value", [
        ("campaigns", 2), ("attempts", 3), ("target", "demo")])
    def test_a_change_is_declared_exploratory(self, field, value):
        said = recall.departures_from_the_protocol(**{field: value})
        assert said and field in said[0]

    def test_the_summary_SAYS_it_when_exploratory(self, capsys):
        recall.summarise([], {"declared": False}, campaigns=1, attempts=1)
        assert "EXPLORATORY" in capsys.readouterr().out


class TestAResumeIsInvalidatedByFourThings:
    """
    Chaque clé répond à une façon de CORROMPRE le chiffre, jamais de le
    périmer. Un désaccord REFUSE au lieu d'écraser : la récolte qui a
    silencieusement effacé la précédente a coûté une soirée d'étiquetage.
    """

    PROTOCOL = {"target": "bench", "campaigns": 5, "attempts": 12,
                "judge": "groq/x", "code": "abcd"}

    def _write(self, path, protocol, complete=False, campaigns=()):
        path.write_text(json.dumps({
            "protocol": protocol, "complete": complete,
            "campaigns": list(campaigns)}), encoding="utf-8")

    def test_an_absent_file_resumes_from_nothing(self, tmp_path):
        assert recall.already_measured(
            tmp_path / "absent.json", self.PROTOCOL, show=lambda *_: None
        ) == []

    def test_a_COMPLETE_file_is_refused(self, tmp_path):
        path = tmp_path / "done.json"
        self._write(path, self.PROTOCOL, complete=True, campaigns=[{"a": 1}])
        with pytest.raises(SystemExit, match="COMPLETE"):
            recall.already_measured(path, self.PROTOCOL, show=lambda *_: None)

    @pytest.mark.parametrize("key,value", [
        ("target", "demo"), ("campaigns", 9), ("attempts", 3),
        ("judge", "groq/other"), ("code", "ffff")])
    def test_a_different_protocol_is_refused(self, tmp_path, key, value):
        path = tmp_path / "other.json"
        self._write(path, {**self.PROTOCOL, key: value})
        with pytest.raises(SystemExit, match=key):
            recall.already_measured(path, self.PROTOCOL, show=lambda *_: None)

    def test_a_matching_protocol_resumes(self, tmp_path):
        path = tmp_path / "same.json"
        self._write(path, self.PROTOCOL, campaigns=[{"door": "clean"}])
        done = recall.already_measured(path, self.PROTOCOL,
                                       show=lambda *_: None)
        assert len(done) == 1


class TestTheCLIReallyReachesTheMeasurement:
    """
    La jonction, PILOTÉE et non lue dans la source. La leçon du 2026-11-19 :
    un argument inséré dans le mauvais appel est passé devant treize tests
    parce qu'aucun ne pilotait `main()`.
    """

    def test_the_flags_reach_measure(self, monkeypatch, tmp_path):
        seen = {}

        def fake(campaigns, attempts, target, output, show=print,
                 doors=None):
            seen.update(campaigns=campaigns, attempts=attempts,
                        target=target, output=output, doors=doors)
            return [], {"declared": True}

        monkeypatch.setattr(recall, "measure", fake)
        monkeypatch.setattr(recall, "_widths", lambda *a, **k: {})
        out = tmp_path / "x.json"
        recall.main(["--campaigns", "2", "--attempts", "4",
                     "--target", "bench", "--output", str(out)])
        assert seen == {"campaigns": 2, "attempts": 4, "target": "bench",
                        "output": pathlib.Path(str(out)), "doors": None}

    def test_a_single_DOOR_can_be_rerun(self, monkeypatch, tmp_path):
        """
        Reserve aux REPARATIONS, et la regle est non selective : seuls les
        bras dont la PORTE a bouge sont relances, ce qui est determine par le
        changement d'instrument et jamais par le resultat.
        """
        seen = {}

        def fake(campaigns, attempts, target, output, show=print, doors=None):
            seen["doors"] = doors
            return [], {"declared": True}

        monkeypatch.setattr(recall, "measure", fake)
        monkeypatch.setattr(recall, "_widths", lambda *a, **k: {})
        recall.main(["--door", "consignes", "--door", "outil",
                     "--output", str(tmp_path / "x.json")])
        assert seen["doors"] == ["consignes", "outil"]

    def test_widths_only_calls_NO_model(self, monkeypatch, capsys):
        """
        La largeur est gratuite, et c'est la moitié de la mesure qui dit ce
        que l'autre vaut. Elle doit donc être joignable sans dépenser un
        jeton.
        """
        def refuse(*a, **k):
            raise AssertionError("un modèle a été appelé")

        monkeypatch.setattr(recall, "measure", refuse)
        recall.main(["--widths-only"])
        said = capsys.readouterr().out
        assert "DOOR WIDTH" in said
        for door in DOORS:
            assert door in said


class TestTheWIDTHTravelsWithTheRecall:
    """
    Le garde-fou contre la circularité n'est pas que les déclencheurs soient
    parfaits — ils ne le sont pas — c'est que leur largeur soit PUBLIÉE à
    côté du rappel.
    """

    def test_the_summary_prints_the_blind_reference(self, capsys):
        rows = [{"door": "secret", "run": 1, "criterion": "divulgation",
                 "found_at": 1, "any_at": 1, "findings": 1,
                 "criteria": ["divulgation"], "severities": ["high"],
                 "requests": 10}]
        recall.summarise(rows, {"declared": True}, campaigns=1, attempts=12,
                         widths={"secret": (440, 9304)})
        said = capsys.readouterr().out
        assert "440/9304" in said
        assert "blind ref" in said
        # 1-(1-0.0473)^12 = 44 %, donc la reference doit paraitre.
        assert "44." in said or "44%" in said

    def test_a_recall_without_its_width_still_prints_the_recall(self, capsys):
        # La largeur demande le catalogue, donc le snapshot garak : sans lui,
        # le rappel doit rester lisible plutot que de disparaitre.
        rows = [{"door": "secret", "run": 1, "criterion": "divulgation",
                 "found_at": 1, "any_at": 1, "findings": 1,
                 "criteria": ["divulgation"], "severities": ["high"],
                 "requests": 10}]
        recall.summarise(rows, {"declared": True}, campaigns=1, attempts=12,
                         widths=None)
        said = capsys.readouterr().out
        assert "secret" in said and "1/1" in said
        assert "blind ref" not in said


class TestWhatTheMeasurementSAYSItDoesNotMeasure:

    def test_the_summary_declares_the_variance_is_the_JUDGE_s(self, capsys):
        """
        La cible est déterministe, le plan l'est, l'adaptation l'est à
        verdicts donnés — donc deux campagnes ne diffèrent QUE par le juge.
        Sans cette phrase un lecteur lirait le chiffre comme la difficulté
        d'une vraie cible.
        """
        recall.summarise([], {"declared": True}, campaigns=1, attempts=1)
        said = capsys.readouterr().out
        assert "deterministic" in said and "JUDGE" in said

    def test_the_protocol_declares_NO_significance_test(self):
        """
        Ceci est une mesure de taux, pas une comparaison. Déclarer un test de
        signes serait inventer une comparaison qui n'existe pas — les trois
        modules voisins en déclarent un parce qu'ils en ont un.
        """
        assert not hasattr(recall, "sign_test")
        assert "AUCUN TEST DE SIGNIFICATIVITÉ" in recall.__doc__

    def test_and_it_declares_the_unit_is_the_CAMPAIGN(self):
        # Sinon un lecteur croira la regle de stats.py enfreinte : elle
        # refuse de borner des TENTATIVES, pas des campagnes.
        assert "L'UNITÉ EST LA CAMPAGNE" in recall.__doc__
