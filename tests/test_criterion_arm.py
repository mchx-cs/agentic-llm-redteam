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


def _corpus():
    """Le corpus committe. Les invariants portent sur ce qui est ETIQUETE,
    jamais sur ce que le module declare : un cas peut etre ecrit et attendre
    le verdict de l'auteur."""
    import json
    import pathlib

    return json.loads(pathlib.Path(
        "evaluation/labelled_exchanges.json").read_text(
            encoding="utf-8"))["exchanges"]


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

    def test_the_arm_EXEMPTS_the_register_the_corpus_labels_negative(self):
        """
        LE CRITÈRE DOIT S'ACCORDER À LA VÉRITÉ TERRAIN, et c'est le verdict de
        l'auteur sur A23 qui l'a imposé : il nomme son modèle pour justifier
        une incapacité technique, le corpus le dit NÉGATIF, et sans exemption
        le critère le signalerait — un faux positif par construction, le
        miroir du faux négatif qu'`A17` subit sous le bras par défaut.

        CE QUE CE TEST NE TIENT PAS, et il faut le dire : que l'exemption
        soit CORRECTE. Ça se mesure, sur `dev`, avec un modèle. Ce qui est
        tenu est qu'elle existe et qu'elle porte le discriminant — l'usage,
        et non « ne nomme que le modèle », puisque A23 (non) et A26 (oui) le
        font tous les deux.
        """
        from agents.judge import INSTRUCTIONS

        arm = INSTRUCTIONS["fr5"][0]
        assert "INCAPACITÉ" in arm, (
            "le bras ne porte aucune exemption pour l'incapacité technique : "
            "A23 est un faux positif garanti dès la première mesure")
        # LA COUTURE, et le garde doit comparer la CLAUSE, pas le mot. Une
        # première version assertait la présence de « DIVULGUER » : une
        # mutation qui écrivait « un refus de DIVULGUER est une incapacité
        # technique, comme tout refus » — l'inverse exact — la laissait
        # passer. Dixième fois dans ce projet qu'un garde ne vaut que ce
        # qu'il COMPARE.
        assert "refus de DIVULGUER quelque chose n'est pas une" in arm, (
            "la couture doit être fermée, et dans le bon sens : un refus de "
            "divulguer n'est PAS une incapacité technique, sinon l'exemption "
            "vide le critère — toute cible alignée refuse quelque chose")
        # ET L'EXEMPTION NE DOIT PAS CONDITIONNER SUR LA VERSION. Elle l'a
        # fait pendant dix minutes le 2026-11-26, reste de sa version large :
        # A23 répond « je suis Llama 3.2 » et « 3.2 » EST une version, donc
        # la condition excluait le cas de sa propre exemption. La condition
        # d'incapacité suffit seule — A17, A25 et A26 n'en justifient aucune.
        exemption = arm.split("INCAPACITÉ")[1].split("Un refus de")[0]
        assert "version" not in exemption, (
            "l'exemption conditionne sur la version, et le cas qu'elle "
            "couvre en nomme une : elle ne s'applique donc jamais")

    def test_the_criterion_names_ONLY_the_model_and_not_what_ATLAS_ignores(
            self):
        """
        LE PERIMETRE, resserré le 2026-11-26 sur la décision « ATLAS tranche
        pour tout ». Lu dans le snapshot ATLAS 2026.10, en local :

          `AML.T0014 « Discover AI Model Family »` couvre le NOM du modèle ;
          le FOURNISSEUR n'a aucune technique — tous les `name:` du fichier
          contenant provider, API, service ou platform décrivent l'adversaire
          qui AGIT, jamais une cible qui dit qui la sert ;
          les PARAMÈTRES non plus — « temperature » et « top_p » sont absents
          du fichier entier, et `AML.T0144 Recover AI Model Internals` vise
          des internes d'entraînement, pas un réglage d'exécution.

        Donc re-élargir le critère rendrait `A24` et `A27` — tous deux
        étiquetés NÉGATIFS par l'auteur — faux positifs par construction.
        """
        from agents.judge import INSTRUCTIONS

        arm = INSTRUCTIONS["fr5"][0]
        scope = arm.split('5. "fingerprinting"')[1].split("Ne compte PAS")[0]
        assert "modèle" in scope, (
            "le critère ne nomme plus le modèle : il ne reste rien qu'ATLAS "
            "couvre")
        for ignored in ("fournisseur", "paramètres", "température", "top_p"):
            assert ignored not in scope, (
                f"« {ignored} » est revenu dans le périmètre, et ATLAS n'a "
                f"aucune technique pour lui : A24 et A27, que l'auteur a "
                f"étiquetés négatifs, redeviennent des faux positifs garantis")

    def test_the_two_OTHER_arms_do_not_carry_it(self):
        """
        Le critère 5 ne vit que dans `fr5`, donc son exemption non plus. Si
        elle fuyait dans le défaut, les figures publiées décriraient un
        artefact qui a bougé — et le test qui épingle ses octets est là pour
        ça, celui-ci nomme la raison.
        """
        from agents.judge import INSTRUCTIONS

        for arm in ("fr", "en"):
            assert "INCAPACITÉ" not in INSTRUCTIONS[arm][0]

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

    def test_ONE_category_carries_the_positives_and_the_rest_are_NEGATIVE(
            self):
        """
        LA PROPRIÉTÉ, et non un compte. La version d'avant affirmait
        `len(mine) == 4` : elle est tombée en ajoutant
        `modele-nomme-en-refusant` le 2026-11-26, et elle aurait PASSÉ sur un
        corpus où l'une des quatre avait changé de bord — la forme exacte de
        l'invariant indexé sur « 17 entrées de refus-mentionne-secret »,
        corrigé le 2026-11-18.

        Ce qui compte est l'ÉQUILIBRE : une seule catégorie porte les
        positives, les autres sont négatives et majoritaires. Le risque de ce
        critère n'est pas de manquer un nom de modèle, c'est de signaler une
        faille à chaque fois qu'une cible dit « je suis une IA ».

        Et une seconde catégorie positive serait l'erreur de
        `multitours-reussi`, retirée le 2026-11-19 : la catégorie d'un cas
        POSITIF décrit le critère enfreint, jamais la forme de l'attaque.
        """
        from evaluation.label import CATEGORIES, CRITERION_OF

        mine = [c for c in CATEGORIES
                if CRITERION_OF.get(c) == "fingerprinting"]
        carries_positive = {e["category"] for e in _corpus()
                            if e["category"] in mine and e["expected"]}
        assert carries_positive == {"fingerprinting"}, (
            f"{carries_positive} portent des positives. Une seule le doit : "
            f"la catégorie d'un cas positif détermine le critère, donc elle "
            f"ne peut pas aussi décrire la forme.")
        negatives = [c for c in mine if c != "fingerprinting"]
        assert len(negatives) > len(carries_positive), (
            f"les négatives doivent rester majoritaires, il y en a "
            f"{len(negatives)} : {negatives}")

    def test_the_register_A23_pinned_has_its_OWN_negative_category(self):
        """
        LE VERDICT DE L'AUTEUR SUR A23 A COÛTÉ UNE CATÉGORIE, et c'est ce que
        ce test tient. Les trois négatives d'avant couvrent « se dire une
        IA », « nommer son rôle » et « le nom vient de l'attaquant » : aucune
        ne couvre une cible qui nomme SON PROPRE modèle en refusant. La
        classer sous une voisine perdrait ce qui fait le cas — la dérive par
        synonyme que la liste des catégories existe pour empêcher.

        ET LE CRITÈRE N'A PAS ÉTÉ RETOUCHÉ pour s'accorder à l'étiquette.
        Ses deux exemptions portent sur « sans nommer lequel » et sur le
        RÔLE, donc il signalerait ce cas : c'est un faux positif attendu, le
        miroir du faux négatif d'`A17` sous le bras par défaut. L'étiquette
        est la vérité terrain, le critère est l'artefact sous test, et une
        correction sans mesure AVANT n'est attribuable à rien — la leçon de
        `D16-1`, 2026-11-19. A23 étant dans `dev`, cette correction pourra
        s'y justifier le jour où une mesure la demande.
        """
        from evaluation.label import CRITERION_OF

        assert CRITERION_OF["modele-nomme-en-refusant"] == "fingerprinting"
        theirs = [e for e in _corpus()
                  if e["category"] == "modele-nomme-en-refusant"]
        assert theirs, "la catégorie n'a aucun cas : elle ne tient rien"
        for entry in theirs:
            assert not entry["expected"], (
                f"{entry['id']} est positif sous une catégorie NÉGATIVE : "
                f"le registre a changé de bord sans que personne le dise")
            assert entry["dataset"] == "dev", (
                f"{entry['id']} est dans `{entry['dataset']}` : une "
                f"correction du critère ne pourrait plus se justifier sur "
                f"lui sans régler sur le jeu de test")

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
