"""
Un POSITIF que le bras ne peut pas nommer quitte la mesure, et c'est DIT.

Aucun appel à un modèle. Ce qui est tenu ici est la forme d'une exclusion sur
une figure publiée, et il y a une raison précise à chaque garde : une
exclusion est le genre de mécanisme qui peut servir à faire disparaître un
vrai raté, donc elle doit être lisible, étroite, et impossible à élargir sans
qu'un test tombe.

LE CAS QUI L'A RENDU NÉCESSAIRE. `A17` est un positif `fingerprinting`, et le
critère n'est que dans le bras `fr5`. Sous le défaut `fr`, l'énum JSON que
l'instruction impose au juge ne contient pas le mot — donc le juge n'a pas de
case pour le dire, et c'est un faux négatif GARANTI. Le rappel publié de `dev`
serait tombé de 100 % à 98 % pour une raison qui n'est pas celle du juge.

LE PRÉCÉDENT QUI A DÉCIDÉ LA FORME est dans `evaluate_judge` lui-même : il
exclut les conversations de la ligne mono-tour et le DIT, parce que les juger
sur un format que l'instruction ne connaît pas déplacerait silencieusement une
mesure de référence. Même cas, un critère au lieu d'un format.
"""

import io
import json
from contextlib import redirect_stdout

import pytest

from evaluation.evaluate_judge import (criteria_the_arm_can_name,
                                       unscorable_positives)


def _case(identifier, category, expected):
    return {"id": identifier, "category": category, "expected": expected}


POSITIVE = _case("A17", "fingerprinting", True)
NEGATIVES = [_case("A18", "role-nomme", False),
             _case("A19", "modele-dit-par-l-attaquant", False),
             _case("A20", "ia-generique", False)]
SCORABLE = _case("P01", "fuite-donnees-tiers", True)


class TestWhatTheArmCanNameIsREADFromTheInstruction:
    """
    LU, jamais redit, et la seconde raison est la plus importante.

    Une liste à nous divergerait du prompt à la première retouche — la dérive
    par duplication que ce projet refuse partout. Et surtout : une liste à
    nous permettrait de faire disparaître un vrai raté en déclarant un
    critère inscorable. Ce que le juge peut NOMMER est dans la sortie JSON
    qu'on lui impose, et c'est la seule source qui ne puisse pas mentir sur
    ce point.
    """

    def test_the_default_arm_cannot_name_the_fifth_criterion(self):
        assert "fingerprinting" not in criteria_the_arm_can_name("fr")

    def test_the_fr5_arm_CAN(self):
        """
        LE CONTRASTE, sans lequel le reste ne mesure rien : si les deux bras
        se comportaient pareil, l'exclusion n'aurait aucune raison d'exister
        et le bras `fr5` n'aurait aucun objet.
        """
        assert "fingerprinting" in criteria_the_arm_can_name("fr5")

    def test_the_four_measured_criteria_are_in_EVERY_arm(self):
        for arm in ("fr", "en", "fr5"):
            nameable = criteria_the_arm_can_name(arm)
            for criterion in ("divulgation", "obeissance", "abus_outils",
                              "fuite_donnees_tiers"):
                assert criterion in nameable, (arm, criterion)

    def test_it_comes_from_the_REAL_instruction_and_not_a_list(self):
        """
        Le set doit être une FONCTION de l'instruction : le même nom de bras
        rendant toujours la même chose ne prouve rien si rien ne le relie au
        prompt.
        """
        from agents.judge import system_prompt_for

        for arm in ("fr", "fr5"):
            prompt = system_prompt_for(False, arm)
            for criterion in criteria_the_arm_can_name(arm):
                assert f'"{criterion}"' in prompt, (arm, criterion)

    def test_a_MISSING_enum_raises_instead_of_excluding_everything(self,
                                                                  monkeypatch):
        """
        Un set vide exclurait TOUS les positifs du corpus, donc rendrait un
        rappel sur rien. Échouer bruyamment est la seule issue acceptable —
        la même raison qui fait échouer la collecte du compte de tests plutôt
        que de la sauter.
        """
        monkeypatch.setattr("evaluation.evaluate_judge.system_prompt_for",
                            lambda *a, **k: "une instruction sans enum")
        with pytest.raises(RuntimeError, match="critere"):
            criteria_the_arm_can_name("fr")


class TestOnlyThePOSITIVESLeaveTheMeasurement:
    """
    L'ASYMÉTRIE EST LA CORRECTION, et ce n'est pas ce que j'avais proposé
    d'abord : j'allais exclure toutes les entrées du critère.

    Un positif dont le critère est hors du bras est inscorable par
    construction. Un NÉGATIF est scoré correctement par n'importe quel bras —
    le juge dit `aucun`, l'étiquette dit non, vrai négatif — et l'exclure
    jetterait une mesure RÉUSSIE : le raisonnement exact qui garde
    `hallucination` scorable dans `stats.py`.
    """

    def test_the_positive_is_set_aside_under_the_default_arm(self):
        aside = unscorable_positives([POSITIVE] + NEGATIVES, "fr")
        assert [e["id"] for e in aside] == ["A17"]

    def test_the_NEGATIVES_are_KEPT(self):
        aside = unscorable_positives(NEGATIVES, "fr")
        assert aside == [], (
            "un négatif est scoré correctement par tout bras : `aucun` contre "
            "une étiquette `false` est un vrai négatif, et l'exclure jetterait "
            "une mesure réussie")

    def test_nothing_is_set_aside_by_the_arm_that_CARRIES_the_criterion(self):
        assert unscorable_positives([POSITIVE] + NEGATIVES, "fr5") == []

    def test_a_positive_the_arm_CAN_name_is_never_set_aside(self):
        # Sans ce contraste, un garde qui exclut tout passerait.
        assert unscorable_positives([SCORABLE], "fr") == []

    def test_a_control_has_no_criterion_and_is_never_set_aside(self):
        # `CRITERION_OF` rend None pour un contrôle : « aucun critère à
        # scorer » est une vraie réponse, pas un critère absent du bras.
        control = _case("E01", "controle", False)
        assert unscorable_positives([control], "fr") == []


class TestTheExclusionIsSAIDAndNotSilent:
    """
    Calculer correctement et ne rien imprimer ne changerait rien pour un
    lecteur — la forme de défaut la plus fréquente de ce projet, rencontrée
    sur les trois champs de chaîne de possession, sur le tour d'infraction et
    sur la télémétrie.
    """

    def _run(self, exchanges, language="fr", monkeypatch=None):
        from evaluation import evaluate_judge as ev

        monkeypatch.setattr(ev, "load_exchanges", lambda dataset: exchanges)
        monkeypatch.setattr(ev, "ask_the_judge", lambda e, lang: {
            "reussi": False, "critere": "aucun", "analyse": "", "valeur": None,
            "votes": [False]})
        captured = io.StringIO()
        with redirect_stdout(captured):
            ev.evaluate(dataset="dev", language=language)
        return captured.getvalue()

    def _entry(self, identifier, category, expected, payload="q", reply="r"):
        return {"id": identifier, "group": identifier, "category": category,
                "dataset": "dev", "expected": expected, "payload": payload,
                "reply": reply, "secret": None, "labelled_by": "author",
                "languages": "fr->fr", "breach_turn": 1 if expected else None,
                "trap": "x", "source": "x"}

    def test_the_set_aside_entries_are_NAMED_above_the_figures(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr("evaluation.resume.Cache.__len__",
                            lambda self: 0)
        monkeypatch.setattr("evaluation.resume.Cache.get",
                            lambda self, *a, **k: None)
        monkeypatch.setattr("evaluation.resume.Cache.put",
                            lambda self, *a, **k: None)
        monkeypatch.setattr("evaluation.resume.Cache.discard",
                            lambda self: None)
        out = self._run([
            self._entry("A17", "fingerprinting", True),
            self._entry("D01", "fuite-directe", True),
            self._entry("E01", "controle", False),
        ], monkeypatch=monkeypatch)

        assert "SET ASIDE" in out
        assert "A17" in out.split("SET ASIDE")[1][:600]
        assert "fingerprinting" in out
        # Et la RAISON, pas seulement le fait : sans elle un lecteur lit une
        # entrée écartée sans savoir que c'est le bras et non le juge.
        assert "GUARANTEED false negative" in out

    def test_the_set_aside_entry_LEAVES_the_figure_too(self, monkeypatch):
        """
        LA MOITIÉ QUE L'AVERTISSEMENT NE PROUVE PAS. Imprimer l'exclusion et
        compter quand même l'entrée donnerait un lecteur rassuré devant un
        rappel baissé — la jonction entre deux pièces correctes séparément,
        la forme de défaut la plus fréquente de ce projet.

        Le juge simulé répond toujours `aucun`, donc un positif compté serait
        un faux négatif : s'il n'y en a aucun, l'entrée a bien quitté la
        mesure.
        """
        monkeypatch.setattr("evaluation.resume.Cache.__len__",
                            lambda self: 0)
        monkeypatch.setattr("evaluation.resume.Cache.get",
                            lambda self, *a, **k: None)
        monkeypatch.setattr("evaluation.resume.Cache.put",
                            lambda self, *a, **k: None)
        monkeypatch.setattr("evaluation.resume.Cache.discard",
                            lambda self: None)
        out = self._run([
            self._entry("A17", "fingerprinting", True),
            self._entry("E01", "controle", False),
        ], monkeypatch=monkeypatch)

        assert "FN=0" in out.replace(" ", ""), (
            "le positif inscorable est encore compté : l'avertissement "
            "s'imprime et la figure baisse quand même.\n" + out[-1500:])

    def test_it_says_NOTHING_when_every_criterion_is_nameable(
            self, monkeypatch):
        monkeypatch.setattr("evaluation.resume.Cache.__len__",
                            lambda self: 0)
        monkeypatch.setattr("evaluation.resume.Cache.get",
                            lambda self, *a, **k: None)
        monkeypatch.setattr("evaluation.resume.Cache.put",
                            lambda self, *a, **k: None)
        monkeypatch.setattr("evaluation.resume.Cache.discard",
                            lambda self: None)
        out = self._run([
            self._entry("D01", "fuite-directe", True),
            self._entry("E01", "controle", False),
        ], monkeypatch=monkeypatch)
        assert "SET ASIDE" not in out, (
            "une note à chaque run serait du bruit, et ce projet a retiré un "
            "garde entier pour avoir crié faux")


class TestTheCorpusAndTheArmAgree:
    """
    La propriété qui fait que cette exclusion reste une EXCEPTION plutôt
    qu'une habitude : un seul critère est hors du défaut, et c'est le
    cinquième, écrit dans un bras exprès.
    """

    def test_exactly_ONE_criterion_is_outside_the_default_arm(self):
        from evaluation.label import CRITERION_OF

        nameable = criteria_the_arm_can_name("fr")
        outside = {c for c in CRITERION_OF.values()
                   if c is not None and c not in nameable}
        assert outside == {"fingerprinting"}, (
            f"{outside} sont hors du bras par défaut. Chaque critère de plus "
            f"met des positifs hors mesure : la décision se prend "
            f"délibérément, pas en ajoutant une catégorie.")

    def test_the_corpus_only_sets_aside_what_the_fifth_criterion_covers(self):
        path = ("evaluation/labelled_exchanges.json")
        corpus = json.loads(
            __import__("pathlib").Path(path).read_text(encoding="utf-8")
        )["exchanges"]
        aside = unscorable_positives(corpus, "fr")
        from evaluation.label import CRITERION_OF

        assert {CRITERION_OF[e["category"]] for e in aside} <= {
            "fingerprinting"}
