# -*- coding: utf-8 -*-
"""
Le bras TEMPORAIRE qui mesure la langue des etiquettes de la question.

Ecrits dans le MEME mouvement que le cablage : cette session a attrape trois
fois le motif inverse -- cinq gardes muets au cablage de la reconnaissance,
trois sur l'identifiant de recolte, trois sur la provenance -- et le motif est
stable. Sans eux, les gardes verifient ce que le code fait et non ce qu'on
affirme qu'il fait.
"""
import re

import pytest

import agents.judge as judge
import targets.conversation as conversation
import evaluation.measure_labels as labels
from evaluation.label import load, CORPUS_FILE


class TestTheArmSWITCHESAndRESTORES:
    """
    Les deux moities, et la seconde est celle qu'on oublie : un bras qui ne
    restaure pas laisserait un run ulterieur du MEME processus mesurer le
    bras en croyant mesurer le controle.
    """

    def test_it_changes_the_labels_the_instruction_AND_the_question(self):
        before = labels.arm_state()
        with labels.EnglishLabels() as arm:
            during = arm.after
        after = labels.arm_state()

        # Les QUATRE, parce que trois suffiraient a se croire au travail :
        # les etiquettes seules laisseraient l'instruction decrire
        # `Utilisateur` au juge qui voit `User`.
        for field in ("labels", "single-turn", "conversation", "question"):
            assert before[field] != during[field], field
        assert after == before

    def test_the_question_really_carries_the_ENGLISH_labels(self):
        with labels.EnglishLabels():
            question = judge.build_question("salut", "bonjour")
        assert "User" in question and "Assistant" in question
        assert "Utilisateur" not in question and "Chatbot" not in question

    def test_the_INSTRUCTION_describes_what_the_judge_SEES(self):
        # La moitie qui compte : une instruction qui parle d'`Utilisateur` au
        # juge qui lit `User` ferait de la mesure deux variables -- la langue
        # des etiquettes, et le DESACCORD entre l'instruction et la question.
        with labels.EnglishLabels():
            instruction = judge.system_prompt_for(False, "fr")
        assert "Utilisateur" not in instruction
        assert "Chatbot" not in instruction
        assert "User" in instruction and "Assistant" in instruction

    def test_the_addendum_is_swapped_TOO(self):
        # L'addendum porte cinq fois chaque etiquette : le laisser en
        # francais ferait que les CONVERSATIONS ne mesurent pas le bras.
        with labels.EnglishLabels():
            mono = judge.system_prompt_for(False, "fr")
            conv = judge.system_prompt_for(True, "fr")
        addendum = conv[len(mono):]
        assert addendum, "l'addendum a disparu"
        assert "Utilisateur" not in addendum and "Chatbot" not in addendum

    def test_it_restores_even_when_the_run_RAISES(self):
        before = labels.arm_state()
        with pytest.raises(RuntimeError):
            with labels.EnglishLabels():
                raise RuntimeError("le run est tombe")
        assert labels.arm_state() == before


class TestItREFUSESToMeasureAnUnchangedArm:
    """
    La lecon de `measure_judges`, dont la premiere version aurait fait
    tourner trois bras sur le MEME modele en silence : trois figures
    identiques se seraient lues comme << les criteres portent le resultat >>,
    la plus flatteuse des issues, obtenue d'un bug.
    """

    def test_a_no_op_swap_is_REFUSED(self, monkeypatch):
        monkeypatch.setattr(labels, "SWAP",
                            {"Utilisateur": "Utilisateur",
                             "Chatbot": "Chatbot"})
        with pytest.raises(SystemExit) as refusal:
            with labels.EnglishLabels():
                pass
        assert "REFUS DE MESURER" in str(refusal.value)

    def test_a_swap_that_misses_the_LABELS_is_refused(self):
        """
        LE CAS REALISTE : on traduit l'instruction et on oublie le dict. Le
        juge lirait alors `Utilisateur` dans la question et `User` dans son
        instruction -- PIRE qu'aucun bras, puisque la mesure aurait deux
        variables dont un desaccord qu'on n'a pas declare.

        Pilote sur `verify()` avec une paire FABRIQUEE, et c'est pourquoi
        elle est une fonction a part : la premiere version de ce test
        affirmait la presence d'un champ dans `arm_state()`, donc elle ne
        comparait rien de ce que son nom promet.
        """
        before = {"labels": {"attacker": "Utilisateur"},
                  "single-turn": "aaa", "conversation": "bbb",
                  "question": "ccc"}
        forgot = {**before, "single-turn": "xxx", "conversation": "yyy",
                  "question": "zzz"}          # tout bouge SAUF les labels
        with pytest.raises(SystemExit) as refusal:
            labels.verify(before, forgot)
        assert "`labels`" in str(refusal.value)

    def test_and_a_COMPLETE_swap_passes(self):
        # Le contraste, sans quoi le garde ci-dessus passerait sur un
        # `verify` qui refuse tout.
        before = {"labels": {"attacker": "Utilisateur"},
                  "single-turn": "aaa", "conversation": "bbb",
                  "question": "ccc"}
        after = {"labels": {"attacker": "User"}, "single-turn": "xxx",
                 "conversation": "yyy", "question": "zzz"}
        labels.verify(before, after)

    @pytest.mark.parametrize(
        "field", ["labels", "single-turn", "conversation", "question"])
    def test_EVERY_field_is_checked(self, field):
        # Les quatre, un par un : un champ oublie dans la boucle laisserait
        # passer exactement le bras qu'il surveille.
        before = {"labels": {"attacker": "Utilisateur"},
                  "single-turn": "aaa", "conversation": "bbb",
                  "question": "ccc"}
        after = {"labels": {"attacker": "User"}, "single-turn": "xxx",
                 "conversation": "yyy", "question": "zzz"}
        after[field] = before[field]
        with pytest.raises(SystemExit):
            labels.verify(before, after)


class TestTheSwapIsMECHANICAL:
    """
    La discipline du 2026-11-14 : la traduction doit etre FIDELE, parce
    qu'un bras aussi MIEUX ECRIT rendrait un ecart inattribuable a la
    variable declaree.
    """

    def test_nothing_but_the_two_words_moves(self):
        control = judge.system_prompt_for(True, "fr")
        with labels.EnglishLabels():
            arm = judge.system_prompt_for(True, "fr")
        # On remonte du bras vers le controle en defaisant les deux
        # remplacements : si quoi que ce soit d'autre avait bouge, on ne
        # retomberait pas dessus.
        back = arm
        for french, english in labels.SWAP.items():
            back = back.replace(english, french)
        assert back == control, (
            "le bras ne differe pas du controle par les deux seuls mots : "
            "un ecart mesure serait inattribuable a la langue des etiquettes")

    def test_the_swap_covers_BOTH_labels(self):
        assert set(labels.SWAP) == {"Utilisateur", "Chatbot"}


class TestTheComparisonHasONEVariable:
    """
    LA PROPRIETE QUI REND LA MESURE PROPRE, et elle est verifiee plutot que
    supposee : des etiquettes anglaises ARMENT le forgeage de tour que 60
    payloads de la bibliotheque permettent, et le durcissement livre le
    2026-11-14 le couvre en ajoutant une cloture a la question.

    S'il se declenchait sur une entree du corpus, cette entree aurait DEUX
    variables -- la langue des etiquettes et la cloture -- et l'ecart ne
    serait attribuable a aucune des deux.
    """

    PATTERNS = {
        "fr": (r"Utilisateur\s*:", r"Chatbot\s*:"),
        "en": (r"User\s*:", r"Assistant\s*:"),
    }

    @staticmethod
    def _texts(entry):
        out = [entry.get("payload") or "", entry.get("reply") or "",
               entry.get("planted") or ""]
        out += [turn.get("content", "")
                for turn in (entry.get("turns") or [])]
        return [text for text in out if text]

    def test_NO_corpus_entry_triggers_the_hardening_in_either_language(self):
        corpus = load(CORPUS_FILE)["exchanges"]
        for language, patterns in self.PATTERNS.items():
            carrying = [entry["id"] for entry in corpus
                        if any(re.search(pattern, text)
                               for text in self._texts(entry)
                               for pattern in patterns)]
            assert not carrying, (
                f"ces entrees portent une etiquette {language} dans leur "
                f"contenu, donc le durcissement se declencherait et la "
                f"comparaison aurait deux variables sur elles : "
                f"{', '.join(carrying[:8])}")

    def test_and_the_corpus_is_not_EMPTY(self):
        # Sans ce contraste, le garde ci-dessus passerait sur un corpus vide
        # en ne comparant rien.
        assert len(load(CORPUS_FILE)["exchanges"]) > 200


class TestTheProtocolIsDECLARED:

    def test_the_CONTROL_comes_first(self):
        # L'ordre est declare dans le protocole, donc il est tenu : decider
        # apres coup quel bras passe d'abord est le genre de liberte qu'un
        # protocole declare existe pour retirer.
        assert labels.ARMS[0] == "fr"
        assert len(labels.ARMS) == 2

    def test_the_control_arm_is_the_LIVE_instruction(self):
        # Et non une copie : une copie se perimerait a la premiere retouche
        # de l'instruction, et le bras mesurerait un controle disparu.
        assert labels.arm_state()["single-turn"] == __import__(
            "hashlib").sha256(
            judge.system_prompt_for(False, "fr").encode("utf-8")
        ).hexdigest()[:16]

    def test_ONE_arm_announces_itself_as_exploratory(self, capsys,
                                                     monkeypatch):
        seen = []
        monkeypatch.setattr(labels, "evaluate",
                            lambda **kwargs: seen.append(kwargs) or {})
        monkeypatch.setattr(labels, "judge_identity", lambda: "fake/judge")
        labels.main(["--arm", "fr", "--output",
                     str(__import__("tempfile").mkstemp(suffix=".json")[1])])
        out = capsys.readouterr().out
        assert "exploratory" in out
        assert len(seen) == 1

    def test_BOTH_arms_do_not(self, capsys, monkeypatch):
        # Le contraste : sans lui le garde passerait sur une annonce
        # permanente, c'est-a-dire du bruit.
        seen = []
        monkeypatch.setattr(labels, "evaluate",
                            lambda **kwargs: seen.append(kwargs) or {})
        monkeypatch.setattr(labels, "judge_identity", lambda: "fake/judge")
        labels.main(["--output",
                     str(__import__("tempfile").mkstemp(suffix=".json")[1])])
        out = capsys.readouterr().out
        assert "exploratory" not in out
        assert len(seen) == 2


class TestTheOtherHALFIsNotTouched:
    """
    Les VALEURS des criteres sont l'autre moitie de la question de l'auteur,
    et elles sont une MIGRATION : cles de la table de severite, des etats de
    denominateur, de `CRITERION_OF`, et persistees dans dix-huit pistes
    scellees. Ce module ne les touche pas, et un test le dit pour que
    personne ne l'elargisse sans decider.
    """

    def test_the_criterion_values_stay_FRENCH_in_the_arm(self):
        with labels.EnglishLabels():
            instruction = judge.system_prompt_for(False, "fr")
        for value in ("divulgation", "obeissance", "abus_outils",
                      "fuite_donnees_tiers", "fingerprinting", "aucun"):
            assert value in instruction, (
                f"`{value}` a disparu du bras : ce module mesure les "
                f"ETIQUETTES, et traduire les valeurs serait l'autre "
                f"moitie -- une migration sur dix-huit pistes scellees")
