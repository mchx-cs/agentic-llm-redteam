"""
La comparaison de trois juges : son protocole, jamais ses chiffres.

Aucun appel à un modèle. Ce qui est tenu ici est le CÂBLAGE, et il y a une
raison précise : la première version de ce module aurait fait tourner les
trois bras sur le MÊME modèle, en silence.

LE DÉFAUT, attrapé avant le run et non après. `llm_client` fait
`from config import PROFILES`, une référence LIÉE. La première version posait
`GROQ_MODEL` dans l'environnement puis rechargeait `config` — ce qui crée un
NOUVEAU dict dans le module config, tandis que `llm_client.PROFILES` pointe
toujours sur l'ancien. Les trois bras auraient rendu trois figures
identiques, que j'aurais lues comme « les critères portent le résultat » : la
conclusion la plus flatteuse des trois, obtenue d'un bug.

C'est la famille que ce projet traque depuis le gabarit sans `{message}` :
rien ne lève, rien ne casse, et le résultat n'est pas celui qu'on croit. Ici
il aurait INVERSÉ la conclusion, et c'est pour ça que le garde du module
REFUSE de mesurer quand le juge n'a pas bougé.
"""

import json
import pathlib

import pytest

from evaluation import measure_judges as judges


class TestTheModelReallyCHANGESFromArmToArm:

    def test_llm_client_SEES_the_model_the_measurement_sets(self):
        """
        La propriété sur laquelle la correction repose, tenue par le
        COMPORTEMENT et non par l'identité de deux objets.

        Une première version comparait `llm_client.PROFILES is
        config.PROFILES`. Elle passait seule et échouait dans la suite
        complète : `tests/test_config_env.py` recharge `config`, donc
        l'identité n'y survit pas — et un test dépendant de l'ordre
        d'exécution ne dit rien de fiable.

        Ce qui compte n'est pas que les deux objets soient le même, c'est que
        `llm_client` VOIE le modèle que la mesure pose. C'est exactement le
        défaut qu'il garde : un rechargement de module laissait
        `llm_client.PROFILES` sur l'ancien dict, les trois bras tournaient sur
        le même modèle, et trois figures identiques se seraient lues comme
        « les critères portent le résultat ».

        UN SOUS-PROCESSUS, et pas un `importlib.reload` dans la suite : une
        version qui rechargeait `llm_client` ici faisait tomber
        `test_BUDGET_EXCEEDED_still_PROPAGATES` ailleurs, parce qu'un
        rechargement recrée la classe `BudgetExceeded` et qu'un `except`
        tenant l'ancienne ne l'attrape plus. Un test qui casse ses voisins ne
        vaut pas la propriété qu'il tient.
        """
        import subprocess
        import sys

        code = (
            "import config, llm_client\n"
            "from config import JUDGE_PROFILE as p\n"
            "config.PROFILES[p]['model'] = 'sentinel/model-x'\n"
            "assert llm_client.PROFILES[p]['model'] == 'sentinel/model-x'\n"
            "print('SEEN')\n")
        done = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True,
                              cwd=str(pathlib.Path(__file__).parent.parent))
        assert "SEEN" in done.stdout, (
            "llm_client ne voit pas le modèle que la mesure pose : les trois "
            "bras tourneraient sur le même modèle sans que rien ne le dise.\n"
            + done.stderr[-400:])

    def test_an_arm_sets_the_model_and_RESTORES_it(self, monkeypatch):
        from config import JUDGE_PROFILE, PROFILES

        seen = []
        before = PROFILES[JUDGE_PROFILE]["model"]

        def fake_evaluate(dataset, language):
            seen.append(PROFILES[JUDGE_PROFILE]["model"])
            return {"TP": 1}, {"precision": 1.0}

        monkeypatch.setattr("evaluation.evaluate_judge.evaluate",
                            fake_evaluate)
        monkeypatch.setattr("evaluation.evaluate_judge.judge_identity",
                            lambda: f"x/{PROFILES[JUDGE_PROFILE]['model']}")
        judges._one_arm("qwen/qwen3.8-27b", show=lambda *_: None)

        assert seen == ["qwen/qwen3.8-27b"], (
            "le corpus a été jugé par un autre modèle que celui demandé")
        assert PROFILES[JUDGE_PROFILE]["model"] == before, (
            "le modèle n'est pas restitué : la mesure laisserait le projet "
            "dans un état qu'elle a choisi")

    def test_it_REFUSES_to_measure_if_the_judge_did_not_move(
            self, monkeypatch):
        """
        LE GARDE QUI COMPTE. Sans lui, le défaut d'origine reviendrait à la
        première refonte, et il ne lève rien de lui-même.
        """
        monkeypatch.setattr("evaluation.evaluate_judge.judge_identity",
                            lambda: "groq/openai/gpt-oss-120b")
        monkeypatch.setattr(
            "evaluation.evaluate_judge.evaluate",
            lambda **k: pytest.fail("mesuré alors que le juge n'a pas bougé"))
        with pytest.raises(RuntimeError, match="three copies"):
            judges._one_arm("qwen/qwen3.8-27b", show=lambda *_: None)

    def test_the_profile_is_READ_and_not_guessed(self, monkeypatch):
        """
        UNE SENTINELLE, et pas la valeur configuree.

        Une premiere version comparait `_judge_profile()` a l'import
        `JUDGE_PROFILE` : les deux cotes venaient du MEME endroit, donc elle
        passait quelle que soit la valeur -- et elle serait passee aussi si la
        fonction rendait cette constante en dur, ce qui est exactement ce
        qu'elle pretend interdire.

        Elle lisait de surcroit le juge AMBIANT pour decider son assertion,
        ce que `TestNoTestReadsTheAmbientJudge` interdit depuis qu'une CI
        rouge l'a coute : vert ici ou `.env` existe, rouge la ou il n'existe
        pas.
        """
        monkeypatch.setattr("config.JUDGE_PROFILE", "sentinelle-de-test")
        assert judges._judge_profile() == "sentinelle-de-test", (
            "le profil est devine au lieu d'etre lu dans `config`")


class TestTheThreeArmsAreWhatMakesTheResultREADABLE:

    def test_there_are_exactly_three(self):
        assert len(judges.ARMS) == 3

    def test_the_INCUMBENT_is_measured_FIRST(self):
        """
        Délibérément : s'il ne reproduit pas la figure publiée, rien n'est
        comparable, et il vaut mieux l'apprendre avant d'avoir payé les deux
        autres.
        """
        first, role = judges.ARMS[0]
        assert "gpt-oss-120b" in first
        assert "CONTRÔLE" in role or "CONTROLE" in role

    def test_the_third_arm_separates_FAMILY_from_CAPABILITY(self):
        """
        Sans lui, un Qwen plus faible serait inattribuable : famille ou
        capacité ? Le troisième bras est de la MÊME famille que l'incumbent
        et d'une taille comparable au second.
        """
        models = [m for m, _ in judges.ARMS]
        assert any("qwen" in m for m in models), "aucune autre famille"
        same_family = [m for m in models if m.startswith("openai/")]
        assert len(same_family) == 2, (
            "il faut DEUX modèles de la même famille et de tailles "
            "différentes, sinon famille et capacité restent confondues")

    def test_the_published_figure_the_control_must_reproduce_is_PINNED(self):
        """
        « le contrôle a reproduit » est une affirmation que personne ne peut
        vérifier si la figure n'est pas écrite.
        """
        assert set(judges.PUBLISHED) == {"precision", "recall", "accuracy"}
        assert judges.PUBLISHED["recall"] == 1.00


class TestTheProtocolIsDeclaredAndItsDeparturesNamed:

    def test_nothing_changed_is_nothing_said(self):
        assert judges.departures_from_the_protocol() == []

    @pytest.mark.parametrize("field,value", [
        ("dataset", "test"), ("language", "en")])
    def test_a_change_is_declared_exploratory(self, field, value):
        said = judges.departures_from_the_protocol(**{field: value})
        assert said and field in said[0]

    def test_a_subset_of_arms_is_also_a_departure(self):
        said = judges.departures_from_the_protocol(
            arms=["qwen/qwen3.8-27b"])
        assert said and "arms" in said[0]

    def test_the_FROZEN_set_is_not_the_declared_dataset(self):
        """
        Comparer des modèles de juge n'est pas un « moment clé » : ce qui
        change n'est pas l'artefact mesuré, c'est l'instrument qui le lit. Le
        consulter trois fois brûlerait sa valeur de référence pour une
        question que `dev` répond.
        """
        assert judges.DATASET == "dev"
        assert "LE JEU GELÉ N'EST PAS CONSULTÉ" in judges.__doc__

    def test_it_declares_NO_significance_test(self):
        # Les trois bras jugent les MÊMES entrées, donc un test apparié
        # existe (McNemar) -- et ce projet n'en a aucun. En inventer un
        # mettrait une statistique non éprouvée sous un résultat.
        assert not hasattr(judges, "sign_test")
        assert "AUCUN TEST DE SIGNIFICATIVITÉ" in judges.__doc__

    def test_the_three_way_reading_is_declared_in_ADVANCE(self):
        """
        Les trois issues sont écrites avant le run, pour qu'aucune ne soit
        habillée après coup. C'est la discipline des quatre protocoles de la
        semaine.
        """
        said = judges.__doc__
        for branch in ("CAPACITÉ", "FAMILLE", "CRITÈRES"):
            assert branch in said


class TestTheRunIsResumableAndReadOnTheAuthorHalf:

    def test_it_resumes_from_the_arms_on_disk(self, tmp_path, monkeypatch):
        output = tmp_path / "judges.json"
        output.write_text(json.dumps({
            "protocol": {}, "arms": {"openai/gpt-oss-120b": {"counts": {}}}}),
            encoding="utf-8")
        asked = []
        monkeypatch.setattr(judges, "_one_arm",
                            lambda m, *a, **k: asked.append(m) or ({}, {}))
        judges.measure(output=output, show=lambda *_: None)
        assert "openai/gpt-oss-120b" not in asked, (
            "un bras déjà sur le disque a été repayé")
        assert len(asked) == 2

    def test_the_resume_cache_already_invalidates_on_the_JUDGE(self):
        """
        Gratuit et déjà correct : la clé de `resume.py` porte le juge, donc
        chaque bras met en cache à part sans qu'on ait rien à ajouter. C'est
        exactement la clé qui existe pour empêcher qu'une reprise mélange
        deux modèles dans un chiffre.
        """
        import inspect

        from evaluation import resume

        source = inspect.getsource(resume)
        assert "judge" in source.lower()

    def test_the_summary_says_it_reads_the_AUTHOR_half(self):
        # Une figure sur des étiquettes décidées par un modèle mesure
        # l'accord entre modèles -- ici entre le juge testé et celui qui a
        # étiqueté.
        # Les blancs sont à NOUS (l'enroulement du docstring) et les mots
        # sont la revendication : on écrase avant de comparer, la discipline
        # de `check_excerpt.py`.
        import re

        flat = re.sub(r"\s+", " ", judges.__doc__)
        assert "MOITIÉ ÉTIQUETÉE PAR L'AUTEUR" in flat


class TestTheCLIReachesTheMeasurement:

    def test_the_flags_reach_measure(self, monkeypatch, tmp_path):
        seen = {}

        def fake(arms, dataset, language, output, show=print):
            seen.update(arms=arms, dataset=dataset, language=language,
                        output=output)
            return {}

        monkeypatch.setattr(judges, "measure", fake)
        out = tmp_path / "x.json"
        judges.main(["--arm", "qwen/qwen3.8-27b", "--dataset", "dev",
                     "--language", "fr", "--output", str(out)])
        assert seen["arms"] == ["qwen/qwen3.8-27b"]
        assert seen["output"] == pathlib.Path(str(out))

    def test_its_output_prefix_is_DECLARED(self):
        # Sinon le balayage du gitignore ne couvrirait pas ses fichiers, et
        # un log de campagne -- chaque payload complet, chaque réponse
        # verbatim -- pourrait entrer dans un dépôt public.
        assert judges.OUTPUT_PREFIX == "judges"
