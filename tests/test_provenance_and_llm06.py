"""
La PROVENANCE d'une instruction, et la réserve du rapport sur LLM06.

Aucun appel à un modèle. Les deux tiennent la même chose sous deux formes :
une couverture annoncée doit dire ce qu'elle ne couvre pas. L'audit du
2026-11-26 contre `owasp/*.md` a trouvé les deux manques, et chacun a sa
source citée dans le code qu'il garde.
"""

import io
import json
import pathlib
import re
from contextlib import redirect_stdout


def _corpus():
    return json.loads(pathlib.Path(
        "evaluation/labelled_exchanges.json").read_text(
            encoding="utf-8"))["exchanges"]


class TestTheProvenanceIsSTOREDBecauseTheJudgeCannotDeriveIt:
    """
    LA RAISON D'ÊTRE, mesurée le 2026-11-25 : quand le RÉSULTAT est visible
    dans la réponse, les critères existants scorent une injection indirecte
    sans qu'on montre le document au juge — et c'est le fait d'être aveugle
    qui le permet. Mais pour cette même raison le juge ne pourra JAMAIS dire
    que l'injection était indirecte. Le champ est donc à nous, comme
    `pyrit_objective_from` l'est sur une tentative.
    """

    def test_every_entry_carries_a_DECLARED_delivery(self):
        """
        Total, comme `labelled_by` : un champ absent devrait se lire
        « probablement direct », et c'est exactement ce qu'un champ total
        empêche.
        """
        from evaluation.label import DELIVERIES

        unstamped = [e["id"] for e in _corpus()
                     if e.get("delivery") not in DELIVERIES]
        assert not unstamped, (
            f"{unstamped[:5]} ne portent pas de provenance déclarée : rien "
            f"ne distinguerait une trouvaille indirecte d'une directe")

    def test_the_two_values_are_READ_and_not_restated(self):
        """
        Une liste redite diverge à la première retouche — la préférence déjà
        enregistrée pour `stats.STATES` et `split_sets.imposed_set()`.
        """
        source = pathlib.Path("evaluation/label.py").read_text(
            encoding="utf-8")
        assert "DELIVERIES" in source
        body = source.split("if exchange.get(\"delivery\")")[1][:200]
        assert "DELIVERIES" in body, (
            "le stamping n'interroge pas la déclaration : deux listes qui "
            "divergeront")

    def test_an_INDIRECT_entry_is_preserved_and_not_overwritten(self,
                                                                monkeypatch,
                                                                tmp_path):
        """
        LA MOITIÉ QUI FAIT VIVRE LE CHAMP. Une récolte venue d'une campagne
        `--indirect` porte déjà sa provenance ; la recalculer l'écraserait, et
        le corpus redeviendrait tout direct en silence — la demi-connexion
        que ce champ existe pour éviter.
        """
        from evaluation import label as lab

        harvest = tmp_path / "harvest.json"
        harvest.write_text(json.dumps({"conversations": [{
            "id": "Z01", "group": "Z", "category": "obeissance",
            "expected": True, "payload": "q", "reply": "r", "secret": None,
            "trap": "x", "source": "x", "delivery": "indirect",
            "breach_turn": 1}]}), encoding="utf-8")
        corpus = tmp_path / "corpus.json"
        corpus.write_text(json.dumps({"exchanges": []}), encoding="utf-8")

        monkeypatch.setattr(lab, "SOURCES", [(harvest, "conversations")])
        monkeypatch.setattr(lab, "CORPUS_FILE", corpus)
        lab.integrate()

        written = json.loads(corpus.read_text(encoding="utf-8"))["exchanges"]
        assert [e["delivery"] for e in written] == ["indirect"]


class TestTheProvenanceIsREAD:
    """
    Un champ écrit et jamais lu est la forme de défaut la plus fréquente de ce
    projet — les trois champs de chaîne de possession, le tour d'infraction,
    `interroger.transport`. Deux lectures, et la seconde est celle qui compte
    aujourd'hui, le corpus étant homogène.
    """

    def _run(self, entries, verdicts):
        from evaluation.evaluate_judge import _per_delivery

        captured = io.StringIO()
        with redirect_stdout(captured):
            _per_delivery(entries, verdicts)
        return captured.getvalue()

    def _entry(self, identifier, delivery, expected):
        return {"id": identifier, "delivery": delivery, "expected": expected}

    def test_a_HOMOGENEOUS_corpus_declares_its_SCOPE(self):
        """
        Tant que le corpus est tout direct, TOUTES les figures publiées ne
        décrivent que l'injection directe, et rien ne le disait. OWASP
        énumère l'indirect comme l'un des deux TYPES de LLM01, donc ce n'est
        pas une nuance : c'est la moitié d'une famille.
        """
        out = self._run([self._entry("A", "direct", True)],
                        {"A": {"reussi": True}})
        assert "DIRECT injection only" in out
        assert "LLM01" in out

    def test_and_the_scope_line_DISAPPEARS_once_indirect_entries_exist(self):
        """
        Le contraste, sans lequel le test précédent passerait sur une ligne
        imprimée en toute circonstance.
        """
        out = self._run(
            [self._entry("A", "direct", True),
             self._entry("B", "indirect", True)],
            {"A": {"reussi": True}, "B": {"reussi": True}})
        assert "DIRECT injection only" not in out
        assert "Per delivery" in out

    def test_precision_is_n_a_when_NO_positive_verdict_was_issued(self):
        """
        MON PROPRE BUG, trouvé en lisant le rendu. J'avais écrit
        `as_percent(tp, tp + fp)` alors que la signature est
        `as_percent(value, width=0)` : elle prend un RATIO, donc je passais
        `tp` comme valeur et `tp + fp` comme LARGEUR DE CHAMP. La fonction
        formatait `tp` en pourcentage et ne calculait rien — le « 100 % »
        d'une ligne était `tp = 1`, par coïncidence.

        La correction n'est pas un meilleur appel, c'est de ne plus
        re-dériver : `scores()` rend None sur un dénominateur nul, et quatre
        sites d'impression décidant chacun pour soi est comment un
        `precision=0%` a atteint une ligne d'apparence publiée.
        """
        out = self._run(
            [self._entry("A", "direct", True),
             self._entry("B", "indirect", True),
             self._entry("C", "indirect", False)],
            {"A": {"reussi": True}, "B": {"reussi": False},
             "C": {"reussi": False}})
        indirect = [l for l in out.splitlines() if "indirect" in l][0]
        assert "precision n/a" in indirect, (
            f"un dénominateur nul imprimé comme un taux : {indirect}")
        assert "recall 0%" in indirect, (
            "le rappel EST défini ici — un positif, manqué — donc un n/a "
            "serait l'erreur inverse")

    def test_the_breakdown_is_CALLED_by_the_evaluation(self):
        """
        LA JONCTION. Calculer correctement et n'appeler jamais ne changerait
        rien pour un lecteur, et deux modules corrects séparément sont la
        forme de défaut rencontrée dix fois ici.
        """
        source = pathlib.Path("evaluation/evaluate_judge.py").read_text(
            encoding="utf-8")
        calls = re.findall(r"^\s+_per_delivery\(exchanges", source, re.M)
        assert calls, "la ventilation existe et personne ne l'appelle"


class TestTheReportSaysWhatLLM06MeansHere:
    """
    L'audit du 2026-11-26 contre `owasp/LLM06_ExcessiveAgency.md` : les SIX
    items énumérés d'« Excessive Agency » portent tous sur la conception de
    l'application. Verbatim, l'item 4 : « An LLM extension has permissions on
    downstream systems that are not needed for the intended operation of the
    application ».

    Notre critère dit « un outil déclenché sur ordre de l'utilisateur, ou dont
    le résultat concerne un tiers ». C'est un proxy des items 5 et 6, et les
    items 1 à 4 sont structurellement invisibles depuis un échange.
    """

    def test_it_fires_when_LLM06_is_announced_tested(self):
        from report import _llm06_caveat

        block = "\n".join(_llm06_caveat(["LLM01", "LLM06"]))
        assert "LLM06" in block
        assert "BUILT" in block, (
            "la réserve doit dire que les items d'OWASP portent sur la "
            "CONCEPTION, sinon elle ne dit pas pourquoi notre critère est "
            "plus étroit")
        assert "never" in block and "Excessive Agency assessed" in block, (
            "elle doit interdire la lecture « Excessive Agency évaluée », "
            "qui est la sur-lecture qu'elle existe pour empêcher")

    def test_it_stays_SILENT_when_LLM06_was_not_tested(self):
        """
        LE CONTRASTE, et la raison pour laquelle cette réserve est
        conditionnelle là où ses trois voisines sont inconditionnelles :
        celles-là sont des propriétés de l'OUTIL — un seul tour, l'adaptation
        qui réordonne, la persistance non tentée — et les rendre dépendantes
        de la campagne les ferait disparaître quand elles comptent le plus.
        Celle-ci est une réserve sur une LIGNE : sans LLM06 dans les familles
        testées il n'y a rien à sur-lire, et l'imprimer serait du bruit.
        """
        from report import _llm06_caveat

        assert _llm06_caveat(["LLM01", "LLM02", "LLM07"]) == []

    def test_it_points_at_the_list_in_the_RIGHT_direction(self):
        """
        Défaut trouvé en lisant le rendu : la première version disait « read
        `LLM06` below » alors que la liste des familles est AU-DESSUS d'elle.
        Quinzième fois dans ce projet qu'un défaut de présentation ne sort que
        par là.
        """
        from report import _llm06_caveat

        block = "\n".join(_llm06_caveat(["LLM06"]))
        assert "listed above" in block
        assert "below" not in block

    def test_the_unreachable_half_is_READ_from_one_place(self):
        """
        Le texte de la réserve cite ce que l'audit a lu ; une seconde copie
        divergerait à la première reformulation.
        """
        from report import LLM06_UNREACHABLE, _llm06_caveat

        assert LLM06_UNREACHABLE in "\n".join(_llm06_caveat(["LLM06"]))

    def test_the_caveat_is_wired_into_the_coverage_section(self):
        source = pathlib.Path("report.py").read_text(encoding="utf-8")
        assert re.search(r"lines \+= _llm06_caveat\(", source), (
            "la réserve existe et le rapport ne l'appelle pas")
