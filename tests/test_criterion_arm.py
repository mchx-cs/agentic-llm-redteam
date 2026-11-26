"""
Le troisième bras de l'instruction : le critère 5, et le prix qu'il ne coûte
pas.

POURQUOI UN BRAS ET PAS UN REMPLACEMENT. L'instruction du juge est l'artefact
MESURÉ : les figures publiées — `dev` 95 / 100 / 98, les sept consultations du
jeu gelé — décrivent ses octets. Ajouter un critère au défaut les périme
toutes et coûte une remesure des deux formats plus une consultation.

Les trois trous encore épinglés coûtent ce même prix et ne valent pas la même
chose : l'obéissance indirecte est la plus précieuse et demande un TROISIÈME
RÔLE dans le format de la question ; le contrôle contournable touche la
couture du critère 1, la phrase la plus délicatement réglée du projet ; le
fingerprinting est le moins précieux et le seul sans blocage.

D'où le bras, qui est la voie que ce projet a déjà empruntée le 2026-11-14 :
l'instruction anglaise a été écrite, MESURÉE sur `dev`, trouvée sans gain, et
GARDÉE à côté du défaut. Le critère est donc écrit et mesurable d'un drapeau,
le défaut ne bouge pas d'un octet, et l'adopter devient un changement d'une
ligne avec les chiffres déjà en main.

CE QUE CE FICHIER NE TIENT PAS : si le critère est BON. Ça demande les
étiquettes de l'auteur sur les quatre cas A17–A20, puis `--language fr5` sur
`dev`. Un test qui le devinerait serait pire qu'absent.
"""

import hashlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

from agents.judge import (INSTRUCTIONS, JUDGE_SYSTEM_PROMPT,
                          JUDGE_SYSTEM_PROMPT_EN, JUDGE_SYSTEM_PROMPT_FR5,
                          MULTI_TURN_ADDENDUM, system_prompt_for)

#: L'empreinte de l'instruction par défaut au moment où le bras a été ajouté.
#:
#: FIGÉE ICI, et c'est le test le plus important du fichier : si elle bouge,
#: les figures publiées cessent de décrire ce qui tourne, et ce n'est pas une
#: ligne à mettre à jour sans une remesure enregistrée à côté.
DEFAULT_SHA = "bfc7432b19344efd8159a34cdd37774ff36b8598c4eea9f0fe656daa9d9bd17e"
DEFAULT_LENGTH = 8821


class TestTheDefaultIsUntouchedBYTEForBYTE:
    """
    La propriété pour laquelle le bras existe. Sans elle, le critère 5 aurait
    coûté une remesure complète pour le moins précieux des trois trous.
    """

    def test_its_length_has_not_moved(self):
        assert len(JUDGE_SYSTEM_PROMPT) == DEFAULT_LENGTH, (
            f"l'instruction par défaut fait {len(JUDGE_SYSTEM_PROMPT)} "
            f"caractères contre {DEFAULT_LENGTH} figés.\n"
            f"Mettre ce nombre à jour SANS une remesure enregistrée à côté "
            f"transforme les figures publiées en affirmation sur rien.")

    def test_and_neither_has_a_single_byte_of_it(self):
        # La longueur seule laisserait passer un échange de deux mots de même
        # taille. Un garde ne vaut que ce qu'il COMPARE.
        got = hashlib.sha256(JUDGE_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        assert got == DEFAULT_SHA, (
            "l'instruction par défaut a changé sans que sa longueur bouge")

    def test_the_default_names_NO_fifth_criterion(self):
        assert "fingerprinting" not in JUDGE_SYSTEM_PROMPT, (
            "le cinquième critère est entré dans le défaut : toutes les "
            "figures publiées cessent de le décrire")

    def test_a_single_turn_question_is_judged_by_the_default(self):
        assert system_prompt_for(multiturn=False) == JUDGE_SYSTEM_PROMPT


class TestTheArmDiffersByEXACTLYTwoThings:
    """
    Le bras est DÉRIVÉ du défaut par remplacement, pas écrit à part. Deux
    instructions écrites séparément dériveraient au premier ajustement, et
    tout devrait être remesuré deux fois — l'argument que la composition de
    l'addendum a déjà tranché le 2026-11-13.
    """

    def test_it_adds_the_criterion(self):
        assert '5. "fingerprinting"' in JUDGE_SYSTEM_PROMPT_FR5

    def test_it_adds_the_criterion_to_the_JSON_enum(self):
        """
        Un critère qu'on dit au juge d'appliquer et qu'on lui interdit de
        NOMMER est un faux négatif garanti. C'est la raison pour laquelle
        `fuite_donnees_tiers` a attendu le sien, et un test l'a tenu alors.
        """
        assert 'ou "fingerprinting" ou' in JUDGE_SYSTEM_PROMPT_FR5

    def test_and_NOTHING_else(self):
        """
        LE GARDE QUI COMPTE : la comparaison `fr` contre `fr5` n'a de sens
        que si le critère est la SEULE variable. C'est la discipline que le
        bras anglais a imposée le 2026-11-14 — la traduction devait être
        FIDÈLE, parce qu'une version aussi mieux écrite aurait rendu le gain
        inattribuable.
        """
        from agents.judge import (FINGERPRINTING_CRITERION, _ENUM_WITH,
                                  _ENUM_WITHOUT)

        # On remonte du bras vers le défaut en défaisant les deux
        # changements : si quoi que ce soit d'autre a bougé, on ne retombe pas
        # sur le défaut.
        back = (JUDGE_SYSTEM_PROMPT_FR5
                .replace("\n" + FINGERPRINTING_CRITERION, "", 1)
                .replace(_ENUM_WITH, _ENUM_WITHOUT, 1))
        assert back == JUDGE_SYSTEM_PROMPT, (
            "le bras diffère du défaut par autre chose que le critère et son "
            "enum : la comparaison `fr` contre `fr5` n'aurait plus une seule "
            "variable")

    def test_the_arm_shares_the_default_s_ADDENDUM(self):
        # Le critère porte sur une réponse, pas sur un format de
        # conversation : lui donner un addendum à lui ferait DEUX variables.
        assert INSTRUCTIONS["fr5"][1] is MULTI_TURN_ADDENDUM
        assert INSTRUCTIONS["fr"][1] is MULTI_TURN_ADDENDUM


class TestTheArmIsReachableAndDeclared:

    def test_it_is_in_INSTRUCTIONS(self):
        assert "fr5" in INSTRUCTIONS

    def test_the_default_is_still_fr(self):
        from agents.judge import DEFAULT_LANGUAGE
        assert DEFAULT_LANGUAGE == "fr"

    def test_system_prompt_for_serves_it(self):
        assert system_prompt_for(language="fr5") == JUDGE_SYSTEM_PROMPT_FR5

    def test_an_unknown_arm_is_REFUSED_with_the_valid_names(self):
        with pytest.raises(ValueError) as problem:
            system_prompt_for(language="fr6")
        said = str(problem.value)
        for arm in INSTRUCTIONS:
            assert arm in said

    def test_the_evaluation_READS_the_arms_rather_than_restating_them(self):
        """
        `--language` offrait `("fr", "en")` en dur, donc un troisieme bras
        aurait ete inmesurable jusqu'a ce que quelqu'un pense a cette ligne.
        La preference deja enregistree pour `stats.STATES`,
        `judge_identity()` et `split_sets.imposed_set()`.

        PILOTE et non lu en source : `--help` dans un sous-processus, comme
        un operateur le fait. La lecon du 2026-11-19, ou un argument insere
        dans le mauvais appel est passe devant treize tests parce qu'aucun ne
        pilotait l'entree.
        """
        import re
        import subprocess
        import sys as system

        done = subprocess.run(
            [system.executable, "-m", "evaluation.evaluate_judge", "--help"],
            capture_output=True, text=True, cwd=str(ROOT))
        assert done.returncode == 0, done.stderr[-400:]
        # L'aide est ENROULEE par argparse, donc on ecrase les blancs avant
        # de chercher -- la discipline de `check_excerpt.py`.
        flat = re.sub(r"\s+", "", done.stdout)
        for arm in INSTRUCTIONS:
            assert arm in flat, (
                f"le bras << {arm} >> n'est pas offert par --language : il "
                f"serait inmesurable")


class TestTheSeverityTableGRADESIt:

    def test_a_fingerprinting_finding_is_graded_low(self):
        from report import assess_severity

        severity, why = assess_severity(
            {"critere": "fingerprinting", "reussi": True}, None, False)
        assert severity == "low", (
            "une trouvaille non prévue tombe sur « un cas que les règles de "
            "severité ne prévoient pas » — l'aveu d'une règle absente "
            "imprimé comme une note dans un rapport de sécurité")

    def test_low_is_strictly_below_medium(self):
        from report import SEVERITY_ORDER

        assert SEVERITY_ORDER["low"] > SEVERITY_ORDER["medium"], (
            "nommer son modèle n'est pas livrer une valeur : le grade doit "
            "le dire")

    def test_low_has_a_LABEL(self):
        from report import SEVERITY_LABELS, SEVERITY_ORDER

        assert set(SEVERITY_LABELS) == set(SEVERITY_ORDER), (
            "un grade sans libellé s'afficherait brut dans le rapport")

    def test_the_caveat_says_a_named_model_may_be_INVENTED(self):
        from report import assess_severity

        _, why = assess_severity(
            {"critere": "fingerprinting", "reussi": True}, None, False)
        assert "informs an attack" in why, (
            "la mise en garde doit porter l'axe arrêté contre les standards "
            "le 2026-11-16 : informer une attaque n'est pas la constituer")


class TestTheCorpusCanLabelForItAndTheCasesExist:

    def test_the_four_categories_exist(self):
        from evaluation.label import CATEGORIES, CRITERION_OF

        mine = [c for c in CATEGORIES
                if CRITERION_OF.get(c) == "fingerprinting"]
        assert len(mine) == 4, (
            f"quatre catégories sont dues — une positive et trois négatives, "
            f"l'équilibre de D16–D20 — et il y en a {len(mine)} : {mine}")

    def test_three_of_the_four_are_the_NEGATIVE_traps(self):
        """
        Le risque n'est pas de manquer un nom de modèle, c'est de signaler
        une faille à chaque fois qu'une cible dit « je suis une IA », ce que
        toute cible alignée dit.
        """
        from evaluation.label import CRITERION_OF

        mine = {c for c, k in CRITERION_OF.items() if k == "fingerprinting"}
        assert {"ia-generique", "role-nomme",
                "modele-dit-par-l-attaquant"} <= mine

    def test_the_cases_are_written_and_NOT_labelled(self):
        """
        Les étiquettes sont la vérité terrain : c'est l'auteur qui les
        valide, jamais l'arbitre ni un LLM. Un test le garantit plutôt que de
        le laisser à la bonne volonté.
        """
        from evaluation.handwritten_conversations import CASES

        mine = [c for c in CASES if c[0] in {"A17", "A18", "A19", "A20"}]
        assert len(mine) == 4, f"les quatre cas sont dus, il y en a {len(mine)}"
        for identifier, group, intention, turns in mine:
            assert intention and len(intention) > 40
            said = " ".join(str(t) for t in turns)
            assert "expected" not in said and "attendu" not in said

    def test_the_PAIR_differs_only_by_the_target_s_reply(self):
        """
        A17 et A20 sont une paire au sens du projet : même demande, toute la
        différence dans la réponse. Sans A20 on enseignerait que toute
        question technique obtient une faille.
        """
        from evaluation.handwritten_conversations import CASES, PAIRS

        assert "A-fingerprint" in PAIRS
        pair = {c[0]: c for c in CASES if c[1] == "A-fingerprint"}
        assert set(pair) == {"A17", "A20"}
        first = pair["A17"][3]
        second = pair["A20"][3]
        assert len(first) == len(second)
        # Les tours de l'ATTAQUANT doivent être identiques.
        for one, two in zip(first, second):
            if one.get("role") == "attacker":
                assert one == two, (
                    "les jumeaux diffèrent par la demande : le cas mesure "
                    "alors autre chose")

    def test_these_cases_declare_NO_secret(self):
        """
        Ils portent sur le SYSTÈME, pas sur une valeur. Estampiller un secret
        qui n'est pas en jeu fait répondre `labelling_prepass` à une question
        que le cas ne pose pas — et l'auteur lit cette ligne une fois par cas.
        """
        from evaluation.handwritten_conversations import WITHOUT_SECRET

        assert {"A17", "A18", "A19", "A20"} <= WITHOUT_SECRET
