"""
Tests for the second lot, written to be FROZEN (2026-11-19).

No LLM call: everything here is a property of the declared cases and of the
split, so none of it needs a model.

The thing these tests actually protect is the lot's REASON FOR EXISTING. A
case written to measure a criterion is worth nothing if it lands in `dev`,
where the criterion may be tuned against it — and it is worth nothing either
if it arrives carrying a label somebody other than the author decided. Both
failures are silent: the file looks right, the suite stays green, and the
measurement afterwards describes nothing.
"""

import importlib
import pathlib

import pytest

from evaluation.frozen_lot import CASES, add_to_harvest, entries
from evaluation.split_sets import (DEV, TEST, assign, defence_level,
                                   frozen_groups, handwritten_groups)


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


def _groups(built):
    groups = {}
    for entry in built:
        groups.setdefault(entry["group"], []).append(entry)
    return groups


#: Les formules qui FERAIENT de l'etiquette une formalite.
#:
#: Une constante plutot qu'un tuple inline, et LUE par le lot ecrit a la main
#: plutot que recopiee : les deux lots livrent des cas NON etiquetes dont
#: l'intention est montree a l'auteur, et seul celui-ci avait le garde. Une
#: liste redite diverge a la premiere formule ajoutee.
GIVEAWAYS = ("c'est une faille", "est une faille", "réponse attendue",
             "doit être jugé")


class TestTheLabelsAreNOTHere:
    """
    The project's rule, in four places: the labels are the ground truth and
    the AUTHOR validates them, never a model and never a script.

    It matters more for THIS lot than for any other. A frozen lot labelled by
    a model would measure agreement between models — which is exactly what the
    provenance split exists to keep apart, and exactly the gap this lot was
    written to fill. It would cost its writing and deliver nothing.
    """

    def test_no_case_carries_a_verdict(self):
        offenders = [e["id"] for e in entries() if e["expected"] is not None]
        assert not offenders, (
            f"{offenders} arrive with a verdict: the author's ruling would be "
            f"reduced to confirming a label already written")

    def test_no_case_carries_a_category(self):
        offenders = [e["id"] for e in entries() if e["category"] is not None]
        assert not offenders, f"{offenders} arrive with a category"

    def test_every_case_carries_its_INTENTION(self):
        # Without it the author receives twenty-two exchanges, several of them
        # nearly identical, with no way to know why both are being shown.
        for identifier, _, intention, _ in CASES:
            assert intention and len(intention) > 40, identifier

    def test_the_intention_never_states_the_answer(self):
        # "This is a vulnerability" in the intention would make the label a
        # formality. The sentence says what the case TRAPS.
        for identifier, _, intention, _ in CASES:
            lowered = intention.lower()
            for giveaway in GIVEAWAYS:
                assert giveaway not in lowered, (
                    f"{identifier}'s intention states the answer: "
                    f"'{giveaway}'")


class TestTheLotGoesToTheFROZENSet:
    """
    The imposition, which is the whole point. `split_sets` calls the
    hand-written rule ABSOLUTE; this is the same rule read backwards, and it
    has to be just as absolute: a quarter of the lot striped into `dev` would
    put cases written to MEASURE a criterion into the set it is tuned against.
    """

    def test_every_group_is_imposed_to_test(self):
        decision = assign(_groups(entries()))
        assert set(decision.values()) == {TEST}, decision

    def test_the_stratum_is_declared_not_guessed_from_a_prefix(self):
        # `A-` earned its convention by predating the declaration. A new lot
        # has no such history, so there is deliberately no `F-` rule: the
        # groups are recognised because the module declares them.
        for _, group, _, _ in CASES:
            assert defence_level(group) == "frozen-lot"
        assert defence_level("F-not-declared") != "frozen-lot"

    def test_a_group_renamed_without_the_declaration_is_NOT_frozen(self):
        # The mutation that matters: were `frozen_groups()` keyed to a prefix,
        # this would pass and a lot renamed in three days would silently fall
        # into the striping -- which is exactly what happened to the `T-`
        # groups on 2026-11-18.
        assert "F-fiche-tiers" in frozen_groups()
        decision = assign({"F-looks-frozen": [{"languages": "fr->fr"}]})
        assert decision["F-looks-frozen"] == DEV

    def test_the_two_impositions_never_overlap(self):
        assert not (frozen_groups() & handwritten_groups()), (
            "a group declared both hand-written and frozen would get "
            "whichever imposition `defence_level` checks first, which is a "
            "coin toss between dev and test")

    def test_the_rule_lives_in_ONE_place(self):
        """
        `imposed_set` is the one function that decides, and both callers ask
        it. The first version of this test read `label.py`'s SOURCE for
        `defence_level(group) == "frozen-lot"` -- and a mutation disabling
        that branch (`elif False and ...`) left the string in place, so the
        guard stayed SILENT through exactly the event it was written for.

        That is the fourth time in this project a guard checked for the
        presence of text instead of a behaviour. The behavioural half now
        lives in `tests/test_label.py`, beside its hand-written sibling,
        where `label()` is actually driven.
        """
        from evaluation.split_sets import imposed_set
        for _, group, _, _ in CASES:
            assert imposed_set(group) == TEST
        assert imposed_set("A-echo") == DEV
        assert imposed_set("C-demo3-99") is None, (
            "an ordinary harvested group must stay open to the striping, or "
            "every new group would be imposed and the split would stop "
            "balancing anything")


class TestEveryDeclaredLotHasAnImposition:
    """
    The guard that generalises the lesson, rather than repeating it.

    Twice now a lot of hand-written cases has been added and the split did not
    know about it: the `T-` groups on 2026-11-18, which fell into "other" and
    could have been striped into the frozen set. The fix each time was to read
    the declaration -- but a THIRD module declaring `CASES` would be invisible
    again, and it would get no imposition at all.

    So: any module under `evaluation/` that declares a `CASES` list of
    4-tuples must be named by one of the two impositions. It is checkable, it
    has no false positive today (exactly two such modules exist), and it fails
    the day a third appears -- which is precisely when the decision "dev or
    test?" has to be taken deliberately rather than inherited.
    """

    @staticmethod
    def _case_modules():
        found = []
        for path in sorted(pathlib.Path("evaluation").glob("*.py")):
            module = importlib.import_module(f"evaluation.{path.stem}")
            cases = getattr(module, "CASES", None)
            if isinstance(cases, list) and cases and all(
                    isinstance(case, tuple) and len(case) == 4
                    for case in cases):
                found.append((path.stem, cases))
        return found

    def test_the_two_known_lots_are_found(self):
        names = {name for name, _ in self._case_modules()}
        assert names == {"handwritten_conversations", "frozen_lot"}, (
            f"the set of case-declaring modules changed: {names}. Each one "
            f"needs an imposition in `split_sets`, or its groups fall into "
            f"the striping")

    def test_every_declared_group_has_an_imposition(self):
        imposed = frozen_groups() | handwritten_groups()
        for name, cases in self._case_modules():
            missing = {group for _, group, _, _ in cases
                       if group not in imposed
                       and not group.startswith("A-")}
            assert not missing, (
                f"{name} declares {sorted(missing)}, which neither "
                f"`frozen_groups()` nor `handwritten_groups()` names: those "
                f"groups would be striped, and a hand-written case must never "
                f"land in a set by accident")


class TestTheSurfaceDiffersAndTheFORMATIsDerived:
    def test_the_format_follows_the_number_of_turns(self):
        # Derived, never declared: `is_conversation()` counts an entry with
        # one exchange as single-turn, and an exchange dressed up as a
        # conversation would be judged with an addendum written for several.
        for entry in entries():
            if entry["format"] == "mono-tour":
                assert "turns" not in entry
                assert entry["payload"] and entry["reply"]
            else:
                assert len(entry["turns"]) > 2

    def test_the_lot_holds_BOTH_formats(self):
        formats = {e["format"] for e in entries()}
        assert formats == {"mono-tour", "multi-tours"}, (
            "the frozen set's conversation line rests on two model-labelled "
            "positives: a lot with no conversation in it would leave that "
            "unchanged")

    def test_the_setting_is_NEITHER_of_the_corpus_two(self):
        """
        A held-out set measures generalisation, so the surface has to differ.
        `demo` is a library and `records` a membership-records desk; a lot
        reusing their vocabulary would measure whether the judge recognises
        their wording, not whether the criterion holds.
        """
        text = " ".join(
            turn["content"] for _, _, _, turns in CASES for turn in turns)
        for borrowed in ("fonds ancien", "ARCHIVES-7731", "consulter_dossier",
                         "bibliothèque"):
            assert borrowed not in text, (
                f"'{borrowed}' comes from an existing target's setting")

    def test_no_case_id_designates_a_DIFFERENT_corpus_entry(self):
        """
        `T01`-`T06` collided with the frozen set's own `T01`-`T14` on
        2026-11-18, and `label()` refused them -- which is the only reason
        `integrate()` did not silently drop all six, since it skips ids
        already present.

        "Already in the corpus" is NOT the collision, and this test learned
        that the hard way: its first version compared PRESENCE, and it failed
        the moment the lot was integrated, when every id was legitimately
        there. The collision is an id that designates SOMEONE ELSE'S entry, so
        the comparison is on the content -- the same fix its hand-written
        sibling needed, for the same reason.
        """
        import json
        corpus = json.loads(
            pathlib.Path("evaluation/labelled_exchanges.json").read_text(
                encoding="utf-8"))
        existing = {e["id"]: e for e in corpus["exchanges"]}

        stolen = []
        for case in entries():
            theirs = existing.get(case["id"])
            if theirs is None:
                continue
            ours = (theirs.get("turns") == case.get("turns")
                    and theirs.get("payload") == case.get("payload")
                    and theirs.get("reply") == case.get("reply"))
            if not ours:
                stolen.append(case["id"])

        assert not stolen, (
            f"these frozen-lot ids designate DIFFERENT corpus entries: "
            f"{sorted(stolen)}. `integrate()` skips ids already present, so "
            f"they would be labelled and then silently dropped. Taken "
            f"prefixes: {sorted({i[0] for i in existing})}.")

    def test_no_two_cases_share_an_id(self):
        identifiers = [identifier for identifier, _, _, _ in CASES]
        assert len(identifiers) == len(set(identifiers))


class TestTheTwinsDifferOnlyByTheREPLY:
    """
    Derived, never named in the source. The hand-written twin guard listed its
    two groups and so stayed silent when a third pair was added -- a guard is
    worth only what it COMPARES.
    """

    @staticmethod
    def _pairs():
        groups = {}
        for identifier, group, _, turns in CASES:
            groups.setdefault(group, []).append((identifier, turns))
        return {g: m for g, m in groups.items() if len(m) == 2}

    def test_there_ARE_pairs(self):
        assert len(self._pairs()) >= 3

    def test_a_pair_differs_only_in_what_the_TARGET_says(self):
        """
        CE GARDE MESURAIT UN PROXY DE SA PROPRE RAISON, et il a fallu le
        reecrire pour une paire en CONVERSATION. Sa raison, ecrite dans son
        message : les deux cas doivent tester LA MEME DEMANDE. La demande,
        ce sont les tours de l'ATTAQUANT -- et l'implementation comparait
        « tous les tours sauf le dernier », ce qui coincide avec la raison
        tant que le discriminant est dans la REPONSE FINALE.

        Il ne coincide plus. La paire F35/F36 a son discriminant au tour 1 et
        une derniere reponse IDENTIQUE, parce que c'est exactement ce qu'elle
        teste : la regle 1 de l'addendum, « juge TOUTE la conversation ».
        L'ancien garde la refusait, et il refusait avec elle toute paire dont
        l'infraction n'est pas dans le dernier tour -- c'est-a-dire le
        comportement MAJORITAIRE de la recolte reelle.

        La forme qui tient est celle du module ecrit a la main, qui compare
        les tours par ROLE depuis le 2026-11-16 : demandes identiques,
        reponses differentes. Elle est plus stricte d'un cote -- elle nomme
        l'attaquant au lieu d'une position -- et plus large de l'autre.
        """
        for group, ((first_id, first), (second_id, second)) in \
                self._pairs().items():
            assert len(first) == len(second), group
            requests = [[t["content"] for t in turns
                         if t["role"] == "attacker"]
                        for turns in (first, second)]
            assert requests[0] == requests[1], (
                f"{group}: {first_id} and {second_id} do not make the same "
                f"request, so the pair would be measuring two different "
                f"things")
            replies = [[t["content"] for t in turns if t["role"] == "target"]
                       for turns in (first, second)]
            assert replies[0] != replies[1], (
                f"{group}: {first_id} and {second_id} say the same thing")

    def test_a_pair_may_differ_at_an_EARLIER_turn(self):
        """
        La moitie que l'ancienne forme interdisait, et c'est pourquoi elle
        est tenue separement : au moins une paire doit avoir son discriminant
        AILLEURS que dans son dernier tour. Sans ce garde, un retour a
        « tous les tours sauf le dernier » ne casserait rien le jour ou la
        seule paire concernee disparaitrait du lot.
        """
        early = []
        for group, ((_, first), (_, second)) in self._pairs().items():
            if first[-1]["content"] == second[-1]["content"]:
                early.append(group)
        assert early, (
            "aucune paire ne porte son discriminant avant le dernier tour : "
            "le lot ne couvre donc pas la forme majoritaire de la recolte "
            "reelle, une infraction au tour 1 suivie d'un dernier tour "
            "impeccable")

    def test_each_pair_shares_its_GROUP_hence_its_set(self):
        # Otherwise the judge could be tuned on one twin and measured on its
        # counterpart, which is the one thing the group rule forbids.
        decision = assign(_groups(entries()))
        for group, members in self._pairs().items():
            assert len({decision[group]}) == 1
            assert len(members) == 2


class TestTheCoverageItIsWRITTENFor:
    """
    The lot is not a pile of cases: each block answers a measured gap. These
    hold the counts that make the gap close, because a block quietly reduced
    to two positives would leave the floor where it was and nothing would say
    so.
    """

    def test_a_tool_marker_appears_and_is_the_shape_the_prepass_reads(self):
        from evaluation.labelling_prepass import TOOL_MARKER
        text = " ".join(
            turn["content"] for _, _, _, turns in CASES for turn in turns)
        assert TOOL_MARKER in text
        # And the pattern adaptation reads, so a campaign would see it too.
        from agents.adaptation import TOOL_PATTERN
        assert TOOL_PATTERN.search(text)

    def test_at_least_five_cases_could_carry_each_new_criterion(self):
        # Five positives bound a perfect recall at 57%; one bounds it at 21%,
        # which is a coin. The lot cannot force the author's verdicts, so what
        # is held here is the SIZE of each block -- enough material for five.
        groups = _groups(entries())
        tool = [g for g in groups if "outil" in g]
        records = [g for g in groups if g.startswith("F-")
                   and "outil" not in g and "persona" not in g
                   and "anodine" not in g and "obeissance" not in g]
        assert len(tool) >= 6, tool
        assert len(records) >= 8, records

    def test_block_F6_carries_the_material_the_THIN_floors_need(self):
        """
        The two floors block F6 answers, measured on 2026-11-24 on the
        author's ground truth: `obeissance` 3 positives (floor 44%) and
        `abus_outils` 4 (51%). Five is this lot's target.

        What is held here is the MATERIAL, since the lot cannot force a
        verdict: six obedience cases (F19/F20/F21 from block F5, F23/F24/F25
        from F6) and a seventh tool case. The MARGIN IS NIL and that is said
        rather than hidden -- F23 and F24 are exactly the two candidate
        positives `obeissance` is short of, so if either comes back negative
        the floor stays at 44% and a further case is owed.
        """
        groups = _groups(entries())
        obedience = {g: cases for g, cases in groups.items()
                     if "obeissance" in g or "persona" in g}
        assert sum(len(c) for c in obedience.values()) >= 6, obedience
        # And the two new registers are there, not just more of the old one.
        assert "F-obeissance-anodine" in obedience
        assert "F-obeissance-traduction" in obedience

    def test_block_F7_carries_the_material_the_EMPTY_floor_needs(self):
        """
        Le trou que le bloc F7 comble, mesure le 2026-11-27 sur la verite
        terrain de l'AUTEUR : les quatre autres criteres sont a 57-65 % de
        plancher et `fingerprinting` n'a RIEN DU TOUT -- zero cas dans le jeu
        gele. La forme exacte qu'avaient `abus_outils` et
        `fuite_donnees_tiers` avant que ce lot existe.

        Ce qui est tenu ici est le MATERIEL, puisque le lot ne peut pas
        forcer un verdict : quatre registres candidats au positif (le modele
        nomme sur question, la confirmation d'une devinette, la mention
        volontaire, et la conversation) et six negatifs, dont les deux
        exemptions ECRITES du critere.

        ET LE PLAFOND EST DIT : quatre positifs bornent un rappel parfait a
        51 %, pas a 57 %. Le cinquieme demanderait un registre que `dev` n'a
        pas, et en inventer un serait gonfler le compte -- la reserve
        enregistree le 2026-11-26.
        """
        groups = _groups(entries())
        fingerprint = {g: cases for g, cases in groups.items()
                       if "fingerprint" in g or "role-ecole" in g
                       or "modele-attaquant" in g or "parametres" in g
                       or "fournisseur" in g}
        assert sum(len(c) for c in fingerprint.values()) >= 10, fingerprint
        # Les deux exemptions ECRITES du critere, qui protegent la phrase
        # d'accueil de chaque cible du projet et toute cible alignee.
        assert "F-role-ecole" in fingerprint
        assert "F-fingerprint-ecole" in fingerprint
        # Le registre qu'ATLAS a fait sortir du critere le 2026-11-26 : s'il
        # disparaissait, le resserrement ne serait mesure nulle part en gele.
        assert "F-parametres-ecole" in fingerprint
        assert "F-fournisseur-ecole" in fingerprint

    def test_the_block_names_MODELS_the_dev_cases_do_NOT(self):
        """
        Le decor du bloc F7 est la meme ecole que F6, et ce qui change est ce
        qui compte pour SON critere : les NOMS DE MODELE. Les neuf cas du
        critere 5 dans `dev` nomment Llama 3.2, Mistral-7B, GPT-4, Ollama,
        Scaleway et Groq -- un critere accroche a ces chaines plutot qu'au
        piege passerait ici sans rien prouver.
        """
        text = " ".join(turn["content"] for _, _, _, turns in CASES
                        for turn in turns)
        for borrowed in ("Llama", "Mistral", "GPT-4", "Ollama", "Scaleway",
                         "Groq", "top_p"):
            assert borrowed not in text, (
                f"« {borrowed} » vient des cas `dev` du critere 5 : le lot "
                f"mesurerait la reconnaissance d'une chaine, pas la "
                f"generalisation du piege")

    def test_the_criterion_5_block_has_a_CONVERSATION(self):
        """
        Le critere 5 n'a AUCUNE conversation dans tout le corpus, donc la
        regle 1 de l'addendum -- « juge TOUTE la conversation, et dis a quel
        tour » -- n'y a jamais ete exercee. Et ce registre n'est MESURABLE
        que depuis la correction de plomberie du 2026-11-27 : avant elle une
        conversation etait jugee par le bras par DEFAUT, ou `fingerprinting`
        n'existe pas.
        """
        talks = [identifier for identifier, group, _, turns in CASES
                 if "fingerprint" in group and len(turns) > 2]
        assert len(talks) == 2, talks

    def test_the_second_block_does_NOT_reuse_the_club_vocabulary(self):
        """
        The generalisation rule applied to the lot's own setting. `A13`/`A14`
        took `fiche_adherent` and "adhérente" into `dev` on 2026-11-24, and
        F26 is A14's register -- so a club case here would differ from its
        `dev` counterpart by names alone, which measures nothing.

        The mutation that matters is `TOOL_SECOND = TOOL`: it leaves every
        other guard green and quietly turns the held-out case into a rename
        of the dev one.
        """
        import evaluation.frozen_lot as lot
        assert lot.TOOL_SECOND != lot.TOOL
        wrong_record = " ".join(
            turn["content"] for _, group, _, turns in CASES
            for turn in turns if group == "F-outil-mauvaise-fiche")
        assert lot.TOOL_SECOND in wrong_record
        assert lot.TOOL not in wrong_record, (
            "F26 uses the club's tool, so it is A14 with different names")

    def test_what_is_still_to_LABEL_fits_one_sitting(self):
        """
        CE GARDE AUSSI MESURAIT UN PROXY. Sa raison : une recolte que
        personne n'etiquette n'est pas une recolte -- `to_label.json` en
        porte 18 546 pour exactement cette raison. Mais il comparait le
        total du LOT, qui etait un proxy de la seance tant que le lot etait
        ecrit d'un coup. Le lot a trois blocs maintenant, et `--add` saute ce
        qui est deja dans le corpus depuis le 2026-11-26 : ce que l'auteur
        affronte est donc ce qui RESTE, et c'est la grandeur a borner.

        Vingt-deux est la taille d'une seance qu'il a deja faite.
        """
        import json

        corpus = json.loads(
            (pathlib.Path(__file__).resolve().parent.parent
             / "evaluation" / "labelled_exchanges.json")
            .read_text(encoding="utf-8"))
        already = {e["id"] for e in corpus["exchanges"]
                   + corpus.get("conversations", [])}
        pending = [e["id"] for e in entries() if e["id"] not in already]
        assert len(pending) <= 22, (
            f"{len(pending)} cas a etiqueter d'un coup : "
            f"{', '.join(pending)}")

    def test_everything_is_FICTIONAL(self):
        text = " ".join(
            turn["content"] for _, _, _, turns in CASES for turn in turns)
        # A public repository carries no real person's data. `.invalid` cannot
        # be registered (RFC 2606), and the telephone numbers are not in a
        # routable range.
        assert "@" not in text or ".invalid" in text
        for real in ("@gmail", "@outlook", "@yahoo", "@exemple.com",
                     "@example.com"):
            assert real not in text

    def test_no_secret_is_claimed_where_there_is_none(self):
        # Truthful rather than tidy: the P-cases carry `ARCHIVES-7731`, a
        # value appearing nowhere in them. The field is documentation, so a
        # lie in it costs nothing today and misleads the next reader.
        assert all(e["secret"] is None for e in entries())


class TestAddToHarvest:
    """
    CES TESTS ONT CHANGE PARCE QUE LE COMPORTEMENT S'EST AMELIORE, de la meme
    facon que leurs voisins du lot ecrit a la main : `--add` saute desormais
    ce qui est deja dans le CORPUS, donc le total verse depend de
    l'avancement de l'etiquetage. `integrate()` vide la recolte, donc avant
    cette correction un `--add` apres une integration re-offrait tout.
    """

    def test_it_appends_and_never_overwrites(self, tmp_path, monkeypatch):
        import evaluation.frozen_lot as lot
        harvest = tmp_path / "to_label_conversations.json"
        harvest.write_text(
            '{"conversations": [{"id": "X01", "group": "X"}]}',
            encoding="utf-8")
        monkeypatch.setattr(lot, "HARVEST_FILE", harvest)

        added, total = lot.add_to_harvest()
        assert total == len(added) + 1

    def test_rerunning_it_duplicates_nothing(self, tmp_path, monkeypatch):
        import evaluation.frozen_lot as lot
        harvest = tmp_path / "to_label_conversations.json"
        monkeypatch.setattr(lot, "HARVEST_FILE", harvest)

        first, _ = lot.add_to_harvest()
        added, total = lot.add_to_harvest()
        assert added == []
        assert total == len(first)


class TestThePairsReallyArePairs:
    """
    The other half of `TestTheTwinsDifferOnlyByTheREPLY`, and the hole a
    mutation found on 2026-11-24: splitting `F24`/`F25` into two groups broke
    nothing at all.

    That class derives its pairs, deliberately, and its own docstring records
    why -- the hand-written guard that listed its groups stayed silent when a
    third pair was added. But a derivation has the mirror blindness: it
    validates the pairs it FINDS, and a pair SPLIT in two simply leaves one
    fewer to find, which it has no reason to object to. The sibling module
    closed that with a declaration the same day; this lot had not.

    So the properties are split rather than duplicated: that class checks
    what a pair must LOOK like (and it is the stricter of the two -- the last
    target turn, not merely the request), this one checks that the pairs are
    the ones DECLARED. One equality binds both directions.
    """

    def test_the_declared_pairs_are_EXACTLY_the_two_case_groups(self):
        from evaluation.frozen_lot import PAIRS
        groups = _groups(entries())
        twos = {group for group, cases in groups.items() if len(cases) == 2}
        assert twos == PAIRS, (
            f"declared {PAIRS}, found {twos}: a pair split into two groups "
            f"loses the discriminant it was written for, and a new pair that "
            f"declares nothing inherits no rule")
