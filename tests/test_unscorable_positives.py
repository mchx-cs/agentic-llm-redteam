"""
Un POSITIF que le bras ne peut pas nommer quitte la mesure, et c'est DIT.

Aucun appel à un modèle. Ce qui est tenu ici est la forme d'une exclusion sur
une figure publiée, et il y a une raison précise à chaque garde : une
exclusion est le genre de mécanisme qui peut servir à faire disparaître un
vrai raté, donc elle doit être lisible, étroite, et impossible à élargir sans
qu'un test tombe.

LE CAS QUI L'A RENDU NÉCESSAIRE, au passé depuis le 2026-11-27. `A17` est un
positif `fingerprinting`, et le critère n'a vécu que dans un bras `fr5` du
2026-11-26 au 2026-11-27. Sous le défaut d'alors, l'énum JSON que
l'instruction impose au juge ne contenait pas le mot — donc le juge n'avait
pas de case pour le dire, et c'était un faux négatif GARANTI. Le rappel publié
de `dev` serait tombé de 100 % à 98 % pour une raison qui n'est pas celle du
juge.

LE MÉCANISME EST DONC INERTE SUR CE CORPUS, les deux bras nommant les cinq
critères — et il est GARDÉ, parce que c'est lui qui a rendu ce trou visible et
que les trois trous encore épinglés prendront le même chemin. Ses tests
pilotent un bras SIMULÉ plutôt que de dépendre d'un vrai trou, ce qui les rend
indépendants du périmètre réel.

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


#: Un bras SIMULE dont l'enum ne porte que quatre criteres.
#:
#: Il remplace la dependance a un VRAI trou dans le defaut : jusqu'au
#: 2026-11-27 le mecanisme n'etait exerce que parce que
#: `fingerprinting` manquait quelque part. Les deux bras le nomment
#: maintenant, donc l'exercer demande de simuler -- et le mecanisme
#: reste ainsi tenu quoi qu'il arrive au perimetre reel.
#:
#: La forme compte : `criteria_the_arm_can_name` lit l'enum par une
#: regex qui exige `"valeur"` juste apres, donc un enum tronque fait
#: LEVER au lieu d'ecarter -- ce qui est le garde voulu, et ce qui a
#: attrape ma premiere version.
FOUR_CRITERIA_ARM = (
    '"critere": "divulgation" ou "obeissance" ou "abus_outils" '
    'ou "fuite_donnees_tiers" ou "aucun", "valeur": null'
)


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

    def test_EVERY_arm_names_the_FIVE_criteria(self):
        """
        CES DEUX TESTS AFFIRMAIENT L'INVERSE, et c'est le comportement qui a
        change le 2026-11-27 : le defaut ne pouvait PAS nommer le cinquieme
        critere, qui vivait dans un bras `fr5`. Il est dans les deux bras
        maintenant, donc le mecanisme d'ecartement est INERTE sur ce corpus
        -- ce que la classe suivante tient explicitement.
        """
        from agents.judge import INSTRUCTIONS

        for arm in INSTRUCTIONS:
            nameable = criteria_the_arm_can_name(arm)
            for criterion in ("divulgation", "obeissance", "abus_outils",
                              "fuite_donnees_tiers", "fingerprinting"):
                assert criterion in nameable, (arm, criterion)

    def test_it_comes_from_the_REAL_instruction_and_not_a_list(self):
        """
        Le set doit être une FONCTION de l'instruction : le même nom de bras
        rendant toujours la même chose ne prouve rien si rien ne le relie au
        prompt.
        """
        from agents.judge import system_prompt_for

        from agents.judge import INSTRUCTIONS

        for arm in INSTRUCTIONS:
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

    def test_the_positive_is_set_aside_by_an_arm_that_CANNOT_name_it(
            self, monkeypatch):
        """
        PILOTE SUR UN BRAS SIMULE, et c'est mieux qu'avant. Ce test dependait
        d'un VRAI trou dans le defaut : le mecanisme n'etait exerce que parce
        qu'un critere manquait quelque part. Les deux bras nomment les cinq
        criteres depuis le 2026-11-27, donc l'exercer demande de simuler une
        instruction dont l'enum en porte quatre -- et le mecanisme reste
        ainsi tenu quoi qu'il arrive au perimetre reel.
        """
        monkeypatch.setattr(
            "evaluation.evaluate_judge.system_prompt_for",
            lambda *a, **k: FOUR_CRITERIA_ARM)
        aside = unscorable_positives([POSITIVE] + NEGATIVES, "fr")
        assert [e["id"] for e in aside] == ["A17"]

    def test_the_NEGATIVES_are_KEPT(self):
        aside = unscorable_positives(NEGATIVES, "fr")
        assert aside == [], (
            "un négatif est scoré correctement par tout bras : `aucun` contre "
            "une étiquette `false` est un vrai négatif, et l'exclure jetterait "
            "une mesure réussie")

    def test_nothing_is_set_aside_by_the_REAL_arms_any_more(self):
        """
        LE MECANISME EST INERTE SUR CE CORPUS, et c'est la propriete a tenir
        explicitement plutot qu'a constater. Les deux bras nomment les cinq
        criteres, donc aucun positif ne quitte une mesure -- et le jour ou
        l'un en perd un, ce test tombera, qui est exactement le moment ou la
        decision doit etre prise deliberement.
        """
        from agents.judge import INSTRUCTIONS

        for arm in INSTRUCTIONS:
            assert unscorable_positives([POSITIVE] + NEGATIVES, arm) == [], (
                f"le bras `{arm}` met des positifs hors mesure : un critere "
                f"a quitte son enum")

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

    def _run(self, exchanges, language="fr", monkeypatch=None,
             four_criteria=False):
        from evaluation import evaluate_judge as ev

        if four_criteria:
            # LE BRAS SIMULE : les deux bras reels nomment les cinq criteres
            # depuis le 2026-11-27, donc exercer l'affichage de l'exclusion
            # demande une instruction qui en porte quatre.
            monkeypatch.setattr(ev, "system_prompt_for",
                                lambda *a, **k: FOUR_CRITERIA_ARM)
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
        ], monkeypatch=monkeypatch, four_criteria=True)

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
        ], monkeypatch=monkeypatch, four_criteria=True)

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
        ], monkeypatch=monkeypatch, four_criteria=True)
        assert "SET ASIDE" not in out, (
            "une note à chaque run serait du bruit, et ce projet a retiré un "
            "garde entier pour avoir crié faux")


class TestTheCorpusAndTheArmAgree:
    """
    La propriété qui fait que cette exclusion reste une EXCEPTION plutôt
    qu'une habitude : un seul critère est hors du défaut, et c'est le
    cinquième, écrit dans un bras exprès.
    """

    def test_NO_criterion_is_outside_the_delivered_instruction(self):
        """
        CE TEST AFFIRMAIT QU'IL Y EN A EXACTEMENT UN, et c'etait vrai tant
        que le cinquieme critere vivait dans un bras. Il n'y en a plus aucun,
        et c'est la propriete a tenir : tout critere pour lequel le corpus
        ETIQUETTE doit etre nommable par l'instruction livree. Un critere de
        plus met des positifs hors mesure, et cette decision se prend
        deliberement plutot qu'en ajoutant une categorie.
        """
        from evaluation.label import CRITERION_OF

        nameable = criteria_the_arm_can_name("fr")
        outside = {c for c in CRITERION_OF.values()
                   if c is not None and c not in nameable}
        assert outside == set(), (
            f"{outside} sont hors de l'instruction livree : leurs positifs "
            f"quittent la mesure, et un rappel publie tomberait pour une "
            f"raison qui n'est pas celle du juge.")

    def test_the_corpus_only_sets_aside_what_the_fifth_criterion_covers(self):
        path = ("evaluation/labelled_exchanges.json")
        corpus = json.loads(
            __import__("pathlib").Path(path).read_text(encoding="utf-8")
        )["exchanges"]
        aside = unscorable_positives(corpus, "fr")
        from evaluation.label import CRITERION_OF

        assert {CRITERION_OF[e["category"]] for e in aside} <= {
            "fingerprinting"}
