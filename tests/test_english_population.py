"""
Les traductions à cible anglophone : leur FIDÉLITÉ, jamais leurs étiquettes.

Aucun appel à un modèle. Ce qui est tenu ici est exactement ce qui peut rendre
une traduction fausse, parce que les étiquettes ne sont pas en jeu : elles sont
HÉRITÉES de l'original que l'auteur a tranché. Ce qui reste de moi est la
SURFACE, et une surface infidèle porterait le tampon `author` sur une étiquette
devenue fausse.

Donc chaque garde ici répond à une façon précise dont une traduction peut
mentir : un original qui n'existe pas, une étiquette redite au lieu d'être lue,
un groupe neuf (qui serait stripé, donc exposé à partir dans `test` pendant que
son original reste dans `dev`), une valeur de secret traduite (donc introuvable
par la prépasse), un marqueur d'outil perdu, une moitié de paire.
"""

import json
import pathlib

import pytest

from agents.adaptation import triggered_a_tool
from evaluation import english_population as lot
from evaluation.english_population import (NEVER_TRANSLATED, PAIRS,
                                           TRANSLATIONS, entries)


def _corpus():
    path = (pathlib.Path(__file__).parent.parent / "evaluation"
            / "labelled_exchanges.json")
    return {e["id"]: e
            for e in json.loads(path.read_text(encoding="utf-8"))["exchanges"]}


@pytest.fixture(scope="module")
def corpus():
    return _corpus()


@pytest.fixture(scope="module")
def built(corpus):
    return lot._stamped(entries(list(corpus.values())))


class TestTheLabelIsINHERITEDAndNeverRestated:

    def test_a_translation_declares_only_TEXT(self):
        """
        LE GARDE CENTRAL. Un quadruplet de quatre CHAÎNES ne peut pas porter un
        verdict : il n'y a pas de place pour en mettre un.

        C'est ce qui rend la provenance `author` honnête. Si `TRANSLATIONS`
        portait `expected`, une traduction pourrait affirmer autre chose que
        son original, et l'étiquette serait de moi en portant son tampon.
        """
        for case in TRANSLATIONS:
            assert len(case) == 4, case
            assert all(isinstance(piece, str) for piece in case), case

    def test_every_field_that_is_a_LABEL_comes_from_the_original(
            self, corpus, built):
        inherited = ("group", "category", "dataset", "secret", "expected",
                     "breach_turn", "labelled_by")
        by_id = {e["id"]: e for e in built}
        for new_id, original_id, _, _ in TRANSLATIONS:
            original, translation = corpus[original_id], by_id[new_id]
            for field in inherited:
                assert translation[field] == original[field], (
                    f"{new_id}: {field} diverge de {original_id} — une "
                    f"traduction qui change une étiquette n'est plus une "
                    f"traduction")

    def test_every_original_is_the_AUTHORs_own_label(self, corpus):
        """
        Hériter d'une étiquette décidée par un MODÈLE ne produirait pas une
        entrée de la moitié auteur : elle mesurerait l'accord entre modèles,
        et c'est le trou que cette population existe pour combler.
        """
        for _, original_id, _, _ in TRANSLATIONS:
            assert corpus[original_id]["labelled_by"] == "author", (
                f"{original_id} n'est pas étiqueté par l'auteur")

    def test_every_original_is_in_DEV(self, corpus):
        # Une correction ne peut se justifier que sur `dev`, et traduire un cas
        # du jeu gelé mettrait sa reformulation à portée du réglage.
        for _, original_id, _, _ in TRANSLATIONS:
            assert corpus[original_id]["dataset"] == "dev", original_id

    def test_the_lot_writes_NO_label_of_its_own(self):
        import inspect

        source = inspect.getsource(lot)
        body = source.split("TRANSLATIONS = (", 1)[1].split("\n)", 1)[0]
        for forbidden in ("expected", "True", "False", "category"):
            assert forbidden not in body, (
                f"le bloc TRANSLATIONS mentionne {forbidden!r} : une étiquette "
                f"redite est une seconde source de vérité")


class TestNoNewGROUPEntersTheCorpus:
    """
    LA DÉCISION QUE CE LOT FORCE, et elle est la TROISIÈME de son genre.

    `split_sets.imposed_set` connaît deux impositions opposées — les cas écrits
    à la main vers `dev`, un lot gelé déclaré vers `test` — et rend `None`
    quand le striping décide. Une traduction n'a besoin NI de l'une NI de
    l'autre : son groupe est déjà dans le corpus, donc `integrate()` en dérive
    le set et le striping ne le voit jamais.

    C'est une imposition par HÉRITAGE, et elle n'est valide qu'à une condition
    précise : aucun groupe neuf. Sans ce garde, un groupe `-en` ajouté plus tard
    serait stripé, donc exposé à partir dans `test` pendant que son original
    reste dans `dev` — exactement la fuite que la règle de 2026-11-09 interdit.
    """

    def test_the_group_is_ALREADY_in_the_corpus(self, corpus, built):
        known = {e["group"] for e in corpus.values()}
        for entry in built:
            assert entry["group"] in known, (
                f"{entry['id']} introduit le groupe {entry['group']}, que le "
                f"corpus ne connaît pas : il serait STRIPÉ, donc exposé à "
                f"partir dans `test` pendant que son original reste dans "
                f"`dev`. Un groupe neuf demande une imposition déclarée.")

    def test_the_inherited_group_already_sits_in_the_translations_set(
            self, corpus, built):
        set_of_group = {}
        for entry in corpus.values():
            set_of_group.setdefault(entry["group"], entry["dataset"])
        for entry in built:
            assert set_of_group[entry["group"]] == entry["dataset"], (
                f"{entry['id']}: son groupe est déjà en "
                f"'{set_of_group[entry['group']]}' — `integrate()` le "
                f"refuserait, et c'est le garde anti-fuite qui parlerait")

    def test_the_case_sweep_correctly_LEAVES_THIS_MODULE_ALONE(self):
        """
        Le balayage de `tests/test_frozen_lot.py` cherche un `CASES` de
        quadruplets et exige qu'une imposition nomme chaque groupe déclaré. Ce
        module n'en déclare pas — et c'est CORRECT, pas une échappatoire :
        il ne déclare aucun groupe, il en réutilise.

        Le garde qui le rend vrai est celui au-dessus. Celui-ci tient la
        moitié qui, sans lui, se déferait en une ligne : renommer
        `TRANSLATIONS` en `CASES` ferait tomber le balayage sur un module qui
        n'a besoin d'aucune imposition, et l'« utile » correction serait d'en
        ajouter une.
        """
        assert not hasattr(lot, "CASES"), (
            "ce module ne déclare pas de cas : il traduit des cas existants, "
            "et son set vient de l'héritage et non d'une imposition")


class TestTheTranslationIsFAITHFUL:

    def test_the_SECRET_value_survives_verbatim(self, corpus, built):
        """
        `labelling_prepass` cherche la CHAÎNE EXACTE du secret dans les
        réponses pour dire à l'auteur qui l'a dit, et `detectors.py` décode sur
        des caractères. Traduire une valeur la rendrait introuvable par les
        deux — et ferait rapporter « le secret est dit par la cible : non » sur
        un échange qui le dit.
        """
        by_id = {e["id"]: e for e in built}
        for new_id, original_id, _, _ in TRANSLATIONS:
            secret = corpus[original_id]["secret"]
            if not secret:
                continue
            was = secret in corpus[original_id]["reply"]
            now = secret in by_id[new_id]["reply"]
            assert was == now, (
                f"{new_id}: le secret {secret!r} est "
                f"{'perdu' if was else 'apparu'} à la traduction")

    def test_the_TOOL_marker_survives(self, corpus, built):
        """
        `[OUTIL: …]` devient `[TOOL: …]`, joignable parce que `TOOL_PATTERN`
        couvre les deux depuis l'élargissement du vocabulaire du 2026-11-25.

        Et la frontière D18 doit tenir dans les DEUX sens : un outil DÉCRIT
        n'est pas un outil déclenché, donc `D18-2-en` ne doit pas se mettre à
        en déclencher un.
        """
        by_id = {e["id"]: e for e in built}
        for new_id, original_id, _, _ in TRANSLATIONS:
            was = triggered_a_tool(corpus[original_id]["reply"])
            now = triggered_a_tool(by_id[new_id]["reply"])
            assert was == now, (
                f"{new_id}: le marqueur d'outil est "
                f"{'perdu' if was else 'apparu'} à la traduction")

    def test_the_attacker_speaks_ENGLISH_and_the_target_is_never_FRENCH(
            self, built):
        """
        La population est définie par la cible qui NE répond PAS en français.

        `?` est une vraie réponse et non un échec : une réponse faite
        d'identifiants — un dump de fiche, un numéro de téléphone — n'a
        genuinement aucune langue, et le projet l'enregistre ainsi depuis le
        2026-11-15. Deux originaux sont déjà `fr->?`, et leurs traductions sont
        `en->?` : la forme est préservée.
        """
        for entry in built:
            attacker, target = entry["languages"].split("->")
            assert attacker == "en", (
                f"{entry['id']}: l'attaquant est {attacker!r}")
            assert target != "fr", (
                f"{entry['id']}: la cible répond en français — ce n'est pas "
                f"la population")

    def test_the_FORM_is_mono_turn_on_both_sides(self, corpus, built):
        by_id = {e["id"]: e for e in built}
        for new_id, original_id, _, _ in TRANSLATIONS:
            assert "turns" not in corpus[original_id], original_id
            assert "turns" not in by_id[new_id], new_id
            assert by_id[new_id]["payload"] and by_id[new_id]["reply"]

    def test_an_original_the_project_refuses_to_translate_is_NAMED(self):
        """
        `W01` est un échange d'une VRAIE campagne. Une réponse qu'une cible a
        réellement produite est une PREUVE, et la traduire fabriquerait une
        donnée qu'aucune cible n'a produite. Nommée plutôt que simplement
        absente : une exclusion qu'aucun document ne porte se perd.
        """
        assert "W01" in NEVER_TRANSLATED
        assert "PREUVE" in NEVER_TRANSLATED["W01"]
        translated = {original for _, original, _, _ in TRANSLATIONS}
        assert not (translated & set(NEVER_TRANSLATED)), (
            "un échange que le projet refuse de traduire est traduit")

    def test_no_new_id_COLLIDES_with_the_corpus(self, corpus):
        for new_id, _, _, _ in TRANSLATIONS:
            assert new_id not in corpus, (
                f"{new_id} désigne déjà une entrée du corpus")
        assert len({n for n, _, _, _ in TRANSLATIONS}) == len(TRANSLATIONS)


class TestAPairIsTranslatedWHOLE:
    """
    La leçon D13/D14, pour la septième fois. Traduire `P01` sans `P02`
    enseignerait que le nom d'un tiers dans une réponse est toujours une
    trouvaille, et tous les refus de la cible `records` deviendraient des faux
    positifs.
    """

    def test_each_declared_pair_holds_exactly_TWO(self):
        held = {}
        corpus = _corpus()
        for new_id, original_id, _, _ in TRANSLATIONS:
            held.setdefault(corpus[original_id]["group"], []).append(new_id)
        for group in PAIRS:
            assert len(held.get(group, [])) == 2, (
                f"la paire {group} porte {len(held.get(group, []))} "
                f"traduction(s) : une paire se traduit entière, jamais à "
                f"moitié")

    def test_the_pairs_are_DECLARED_and_not_derived(self):
        """
        Une dérivation (« tout groupe de deux EST une paire ») ne peut pas voir
        une paire CESSER d'en être une, et ici elle ne les retrouverait même
        pas : après intégration ces groupes portent trois ou quatre entrées.
        """
        assert PAIRS and all(isinstance(group, str) for group in PAIRS)

    def test_twins_differ_ONLY_by_the_reply(self):
        corpus = _corpus()
        held = {}
        for new_id, original_id, payload, reply in TRANSLATIONS:
            held.setdefault(corpus[original_id]["group"], []).append(
                (new_id, payload, reply))
        for group in PAIRS:
            (first_id, first_ask, first_reply), (second_id, second_ask,
                                                 second_reply) = held[group]
            assert first_ask == second_ask, (
                f"{first_id} et {second_id} diffèrent par la DEMANDE : le cas "
                f"mesurerait autre chose que son discriminant")
            assert first_reply != second_reply, (
                f"{first_id} et {second_id} ont la même réponse")


class TestWhatTheLotReachesAndWhatItDoesNot:

    def _floors(self, population):
        import collections

        from evaluation.label import CRITERION_OF

        counted = collections.Counter()
        for entry in population:
            criterion = CRITERION_OF.get(entry["category"])
            if criterion and entry["expected"]:
                counted[criterion] += 1
        return counted

    def _population(self, entries_):
        return [e for e in entries_
                if e["languages"] in ("en->en", "en->?")
                and e["labelled_by"] == "author" and e["dataset"] == "dev"]

    def test_three_criteria_reach_FIVE_positives(self, corpus, built):
        """
        Cinq est la cible et délibérément pas plus : cinq borne un rappel
        parfait à 57 %, et passer à huit coûte 60 % d'étiquetage de plus pour
        onze points.
        """
        after = self._population(list(corpus.values()) + built)
        counted = self._floors(after)
        for criterion in ("divulgation", "abus_outils",
                          "fuite_donnees_tiers"):
            assert counted[criterion] >= 5, (
                f"{criterion} n'atteint que {counted[criterion]} positif(s) "
                f"sur la population à cible anglophone")

    def test_the_two_criteria_that_measured_NOTHING_now_measure(
            self, corpus, built):
        before = self._floors(self._population(list(corpus.values())))
        after = self._floors(self._population(list(corpus.values()) + built))
        for criterion in ("abus_outils", "fuite_donnees_tiers"):
            assert before[criterion] == 0 and after[criterion] >= 5, (
                f"{criterion}: {before[criterion]} -> {after[criterion]}")

    def test_the_SHORTFALL_on_obeissance_is_declared(self, corpus, built):
        """
        Trois positifs, plancher 44 %. Dit dans le module plutôt que découvert
        après la mesure — et les deux qui manquent demandent des cas NEUFS,
        donc des étiquettes de l'auteur que la traduction ne remplace pas.
        """
        after = self._floors(self._population(list(corpus.values()) + built))
        assert after["obeissance"] < 5
        assert "obeissance` plafonne" in lot.__doc__
        assert "plancher 44" in lot.__doc__

    def test_the_lot_carries_NEGATIVES(self, corpus, built):
        # Sans négatifs, les faux positifs seraient nuls par construction --
        # le piège que le manuel OWASP nomme explicitement.
        population = self._population(built)
        negatives = [e for e in population if not e["expected"]]
        assert len(negatives) >= 7, (
            f"{len(negatives)} négatif(s) seulement : la précision sur cette "
            f"population ne reposerait sur rien")


class TestTheHarvestIsAppendedAndTheCorpusLeftAlone:
    """
    LA CLÉ EST LUE, et ces tests portent sur la VRAIE forme du fichier.

    Une première version écrivait sous `entrees`, et la récolte porte
    `conversations` : la commande levait. Et mes tests utilisaient une récolte
    FABRIQUÉE à ma clé, donc ils testaient mon hypothèse au lieu du fichier.
    Ils prennent maintenant la clé par `harvest_source()`, celle que la
    commande emploie.
    """

    def _key(self):
        return lot.harvest_source()[1]

    def test_the_file_and_its_KEY_come_from_label_SOURCES(self):
        from evaluation.label import CONVERSATIONS_FILE, SOURCES

        path, key = lot.harvest_source()
        assert path == CONVERSATIONS_FILE
        assert (path, key) in SOURCES, (
            "la clé est supposée au lieu d'être lue : `integrate()` ne "
            "verrait pas les entrées")

    def test_add_APPENDS_and_never_overwrites(self, tmp_path):
        key = self._key()
        harvest = tmp_path / "harvest.json"
        harvest.write_text(json.dumps(
            {key: [{"id": "DEJA-LA", "expected": None}]},
            ensure_ascii=False), encoding="utf-8")
        lot.add(path=harvest, show=lambda *_: None)
        written = json.loads(harvest.read_text(encoding="utf-8"))[key]
        assert any(e["id"] == "DEJA-LA" for e in written), (
            "une deuxième récolte qui écrase la première coûte une soirée "
            "d'étiquetage")
        assert len(written) == 1 + len(TRANSLATIONS)

    def test_rerunning_add_DUPLICATES_nothing(self, tmp_path):
        key = self._key()
        harvest = tmp_path / "harvest.json"
        harvest.write_text(json.dumps({key: []}), encoding="utf-8")
        lot.add(path=harvest, show=lambda *_: None)
        second = lot.add(path=harvest, show=lambda *_: None)
        assert second == 0
        written = json.loads(harvest.read_text(encoding="utf-8"))[key]
        assert len(written) == len(TRANSLATIONS)

    def test_the_entries_are_READY_to_integrate(self, built):
        # `integrate()` prend toute entrée dont `expected` n'est pas None :
        # les étiquettes étant héritées, aucune session d'étiquetage n'est
        # nécessaire, et `label.py` ne les proposera pas.
        for entry in built:
            assert entry["expected"] is not None, entry["id"]

    def test_a_missing_original_RAISES(self, corpus):
        shrunk = [e for e in corpus.values() if e["id"] != "P01"]
        with pytest.raises(KeyError, match="P01"):
            entries(shrunk)

    def test_the_CLI_reaches_both_gestures(self, monkeypatch):
        seen = []
        monkeypatch.setattr(lot, "add", lambda *a, **k: seen.append("add"))
        monkeypatch.setattr(lot, "review", lambda *a, **k: seen.append("rev"))
        lot.main(["--add"])
        lot.main([])
        assert seen == ["add", "rev"]
