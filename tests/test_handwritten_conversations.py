"""
Tests for the hand-written conversations (phase 3b).

No LLM call. What is checked here is not a model's behaviour but properties
of the CORPUS — and they are what makes a measurement mean something.
"""

import pytest

from evaluation.handwritten_conversations import (CASES, PAIRS, SECRET,
                                                 WITHOUT_SECRET,
                                                 entries)


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.reconnaissance", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse,
                            raising=False)


class TestGroundTruth:
    """
    The labels are the ground truth, and it is the AUTHOR who validates them.
    This file writes SCENARIOS, not verdicts — a test guarantees it, because
    that is the rule easiest to break out of convenience.
    """

    def test_a_single_turn_case_comes_out_single_turn(self):
        # Otherwise `evaluate_judge` would skip it, while the judge reads
        # it perfectly well: a one-turn exchange dressed up as a conversation
        # would be lost to a measurement it can feed.
        for entry in entries():
            if entry["format"] == "mono-tour":
                assert "payload" in entry and "reply" in entry
                assert "turns" not in entry
            else:
                assert "turns" in entry and len(entry["turns"]) > 2

    def test_no_verdict_is_pre_filled(self):
        for entry in entries():
            assert entry["expected"] is None, entry["id"]
            assert entry["category"] is None, entry["id"]
            assert entry["dataset"] is None, entry["id"]

    def test_every_case_says_WHY_it_exists(self):
        # Without the intention, the author gets two nearly identical
        # conversations with no idea why both are being shown.
        for entry in entries():
            assert len(entry["trap"]) > 60, entry["id"]


class TestThePairsReallyArePairs:
    """
    The lesson of D13/D14: a negative case on its own teaches the judge too
    broad a rule. It needs its positive twin, with nearly identical text.
    """

    def _by_group(self):
        groups = {}
        for identifier, group, _, turns in CASES:
            groups.setdefault(group, []).append((identifier, turns))
        return groups

    def _pairs(self):
        """
        Every group holding exactly two cases IS a pair, by construction.

        Derived rather than listed, after the previous version named its two
        groups in the source: adding `A-echo` on 2026-11-16 left it passing
        while guarding nothing, the same defect as a test comparing a result
        to the constant that produced it.
        """
        return {g: members for g, members in self._by_group().items()
                if len(members) == 2}

    def test_every_DECLARED_pair_really_holds_two(self):
        """
        The half a derivation cannot do, and it was the one silent mutation
        of six on 2026-11-24: split a twin's group in two and `_pairs()`
        finds one fewer pair, which it has no reason to object to. The
        previous version asserted `len(pairs) >= 3` plus two names, so a
        fourth pair coming undone left it green.

        Both readings stay: the declaration catches a pair coming undone,
        the derivation below still checks any pair nobody declared.
        """
        held = self._by_group()
        for group in PAIRS:
            assert group in held, (
                f"{group} is declared a pair and holds no case at all")
            assert len(held[group]) == 2, (
                f"{group} is declared a pair and holds "
                f"{len(held[group])} case(s): a twin written to pin one trap "
                f"is unusable alone, and sharing a group is what makes the "
                f"two share a SET")

    def test_and_the_derivation_finds_at_least_those(self):
        # The contrast that keeps the declaration honest: a declared group
        # that is not actually two would pass the test above only if that
        # test were wrong, so this one pins the overlap from the other side.
        assert PAIRS <= set(self._pairs())

    def test_the_twins_differ_only_by_the_REPLY(self):
        # The discriminant must be what the TARGET says, not what the
        # attacker asks: otherwise the case measures something else.
        for group in self._pairs():
            (_, first), (_, second) = self._by_group()[group]
            requests_1 = [t["content"] for t in first
                          if t["role"] == "attacker"]
            requests_2 = [t["content"] for t in second
                          if t["role"] == "attacker"]
            assert requests_1 == requests_2, group
            replies_1 = [t["content"] for t in first
                          if t["role"] == "target"]
            replies_2 = [t["content"] for t in second
                          if t["role"] == "target"]
            assert replies_1 != replies_2, group


class TestTheUnreachableTrapsAreCovered:
    def test_the_secret_appears_in_an_ATTACKER_turn(self):
        # The false positive specific to multi-turn. No harvest can produce
        # it: our payloads look for the secret, they do not contain it.
        attacker = [t for _, _, _, turns in CASES for t in turns
                     if t["role"] == "attacker" and SECRET in t["content"]]
        assert attacker, "aucun cas ne met le secret dans la bouche de l'attaquant"

    def test_one_case_leaks_on_an_EARLIER_turn(self):
        # 7 leaks out of 11 had this shape in the real harvest.
        found = False
        for _, _, _, turns in CASES:
            replies = [t["content"] for t in turns if t["role"] == "target"]
            if len(replies) >= 2 and SECRET in replies[0] \
                    and SECRET not in replies[-1]:
                found = True
        assert found

    def test_some_conversations_exceed_two_turns(self):
        # `sequence_turns()` produces only two: beyond that, by hand.
        assert any(len(turns) // 2 > 2 for _, _, _, turns in CASES)

    def test_there_are_entirely_harmless_controls(self):
        # Without them, false positives would be zero by construction.
        harmless = [turns for _, _, _, turns in CASES
                   if not any(SECRET in t["content"] for t in turns)
                   and "instructions" not in turns[0]["content"].lower()]
        assert harmless

    def test_the_turns_always_alternate(self):
        # A malformed corpus would have an incoherent dialogue scored.
        for identifier, _, _, turns in CASES:
            roles = [t["role"] for t in turns]
            assert roles == ["attacker", "target"] * (len(roles) // 2), \
                identifier


class TestPouringIn:
    """
    CES TESTS ONT CHANGE PARCE QUE LE COMPORTEMENT S'EST AMELIORE.

    Ils comparaient le total verse a `len(CASES)`. `--add` saute desormais ce
    qui est deja dans le CORPUS, donc le total depend de l'avancement de
    l'etiquetage -- et c'est le point : `integrate()` vide la recolte, donc
    avant cette correction un `--add` apres une integration re-offrait TOUT.
    Mesure apres un run reel le 2026-11-26 : 49 cas deja integres annonces
    << a etiqueter >>. C'est le defaut nomme le 2026-11-16, qui avait bloque
    une session d'etiquetage, pris a sa cause au lieu de son symptome.

    Ce qui est tenu ici ne depend plus de l'etat du corpus.
    """

    def test_pouring_in_does_not_overwrite_the_harvest(self, monkeypatch,
                                                       tmp_path):
        import json

        import evaluation.handwritten_conversations as by_hand

        harvest = tmp_path / "recolte.json"
        harvest.write_text(json.dumps({"conversations": [
            {"id": "C-demo-01-1", "expected": None}]}), encoding="utf-8")
        monkeypatch.setattr(by_hand, "HARVEST_FILE", harvest)

        added, total = by_hand.add_to_harvest()
        assert total == len(added) + 1, (
            "une deuxieme recolte qui ecrase la premiere coute une soiree "
            "d'etiquetage")

    def test_pouring_in_twice_duplicates_nothing(self, monkeypatch, tmp_path):
        import evaluation.handwritten_conversations as by_hand

        monkeypatch.setattr(by_hand, "HARVEST_FILE",
                            tmp_path / "recolte.json")
        first, _ = by_hand.add_to_harvest()
        added, total = by_hand.add_to_harvest()
        assert added == []
        assert total == len(first)

    def test_what_is_already_in_the_CORPUS_is_not_offered_again(
            self, monkeypatch, tmp_path):
        """
        La propriete que la correction du 2026-11-26 apporte : etiqueter un id
        deja present n'accomplit rien, puisque `integrate()` le saute.
        """
        import json

        import evaluation.handwritten_conversations as by_hand

        harvest = tmp_path / "recolte.json"
        monkeypatch.setattr(by_hand, "HARVEST_FILE", harvest)
        by_hand.add_to_harvest()
        offered = {entry["id"] for entry in json.loads(
            harvest.read_text(encoding="utf-8"))["conversations"]}
        assert not (offered & by_hand._ids_in_corpus()), (
            "des cas deja dans le corpus sont offerts a l'etiquetage")


class TestAHandWrittenIdCannotCOLLIDEWithTheCorpus:
    """
    Found by running the labelling, 2026-11-18. Six new cases were shipped as
    `T01`-`T06` — and `T01`-`T14` are the FROZEN SET's own identifiers.

    `label()` refused them as "already in the corpus", which is the guard
    added on 2026-11-16 doing its job. Without it `integrate()` would have
    SILENTLY DROPPED all six, since it skips ids already present: the author
    would have labelled six cases and added none, and the figure measured
    afterwards would have described a criterion with no cases behind it.

    The id space is shared and nobody owned the check: E, T, R, D, C and A
    were all taken, and nothing said so. Now something does.
    """

    def test_no_case_id_designates_a_DIFFERENT_corpus_entry(self):
        """
        "Already in the corpus" is NOT the collision: a case that has been
        labelled and integrated is there legitimately, which is true of every
        A-case. The collision is an id that designates SOMEONE ELSE'S entry —
        and that is what `T01`-`T06` did, pointing at frozen-set cases.

        So the check compares the CONTENT, not the presence. First version
        compared presence alone and flagged all ten A-cases: a guard that
        cries wrong on legitimate data teaches people to ignore it, which
        this project removed a guard for once already.
        """
        from evaluation.handwritten_conversations import entries
        from evaluation.label import CORPUS_FILE, load

        corpus = {e["id"]: e for e in load(CORPUS_FILE)["exchanges"]}
        stolen = []
        for case in entries():
            existing = corpus.get(case["id"])
            if existing is None:
                continue
            ours = (existing.get("turns") == case.get("turns")
                    and existing.get("payload") == case.get("payload")
                    and existing.get("reply") == case.get("reply"))
            if not ours:
                stolen.append(case["id"])

        assert not stolen, (
            f"these hand-written ids designate DIFFERENT corpus entries: "
            f"{sorted(stolen)}. `integrate()` skips ids already present, so "
            f"they would be labelled and then silently dropped. Taken "
            f"prefixes: {sorted({i[0] for i in corpus})}.")

    def test_no_two_cases_share_an_id(self):
        # The same collision one level in: two cases with one id means one of
        # them never reaches the corpus, and nothing says which.
        from evaluation.handwritten_conversations import CASES
        identifiers = [identifier for identifier, _, _, _ in CASES]
        assert len(identifiers) == len(set(identifiers))


class TestOnlyTheCasesThatTURNOnASecretDeclareOne:
    """
    `secret` was stamped on every case unconditionally. For A01-A10 that is
    right — the attacker writes the value, or the target is asked for it. For
    the criterion pair it is a value appearing NOWHERE in the case, which the
    frozen lot already refused to do and named: "that is the tidier lie".

    It is not cosmetic: `labelling_prepass` searches the replies for that
    exact string to tell the author who said the secret, so a stamped value
    that is not at stake answers a question the case does not ask.
    """

    def test_the_criterion_pair_declares_NO_secret(self):
        for entry in entries():
            if entry["id"] in WITHOUT_SECRET:
                assert entry["secret"] is None, (
                    f"{entry['id']} turns on third-party data, not on a "
                    f"secret: a declared value would make the prepass report "
                    f"on a question this case does not ask")

    def test_but_the_secret_cases_still_declare_it(self):
        # The contrast. Without it the guard above would pass on a module
        # that stamps nothing at all, and the prepass would stop finding who
        # said the value in the eight cases that are ABOUT it.
        stamped = {entry["id"] for entry in entries()
                   if entry["secret"] == SECRET}
        assert stamped, "no case declares the secret any more"
        assert not (stamped & WITHOUT_SECRET)

    def test_the_opt_out_names_only_cases_that_EXIST(self):
        # A typo in the set is silent: the case keeps its stamp and the guard
        # above never looks at it. The same shape as a menu position
        # hardcoded instead of read -- it fails on the neighbour.
        declared = {identifier for identifier, _, _, _ in CASES}
        unknown = WITHOUT_SECRET - declared
        assert not unknown, (
            f"{sorted(unknown)} is in WITHOUT_SECRET and in no case: the "
            f"opt-out would apply to nothing and say nothing")

    def test_and_the_pair_really_carries_no_secret_in_its_TEXT(self):
        # The reason the opt-out is right for these two, checked rather than
        # asserted: if the value ever appeared in them, the stamp would be
        # correct and the opt-out would be hiding a real one.
        for identifier, _, _, turns in CASES:
            if identifier not in WITHOUT_SECRET:
                continue
            for turn in turns:
                assert SECRET not in turn["content"], identifier


class TestTheToolFiredUNPROMPTED:
    """
    A15/A16's register, and the one thing that makes it a register: the
    request does NOT name the tool. `dev`'s four `abus_outils` positives are
    all a DICTATED call (D16-1, D16-2, P06) or the wrong record returned
    (A14), so the criterion's second limb -- "exposing its result when it
    concerns a third party" -- is measured nowhere in `dev`.

    An edit adding the tool's name to the request would silently turn A15
    into D16's register, and every other guard would stay green.
    """

    @staticmethod
    def _pair():
        return {identifier: turns for identifier, group, _, turns in CASES
                if group == "A-outil-spontane"}

    def test_the_request_never_names_the_tool(self):
        for identifier, turns in self._pair().items():
            asked = " ".join(t["content"] for t in turns
                             if t["role"] == "attacker")
            assert "consulter_dossier" not in asked, (
                f"{identifier}'s request names the tool, so the call is "
                f"DICTATED -- that is D16's register, not this one")

    def test_the_tool_fires_in_both_members(self):
        # The discriminant is what the result EXPOSED, never that a tool
        # fired: a twin where no tool appears would measure something else.
        from evaluation.labelling_prepass import TOOL_MARKER
        for identifier, turns in self._pair().items():
            replied = " ".join(t["content"] for t in turns
                               if t["role"] == "target")
            assert TOOL_MARKER in replied, identifier


class TestASecretIsClaimedOnlyWhereItIsAtStake:
    """
    The hole a mutation found on 2026-11-24: taking `A15`/`A16` back out of
    `WITHOUT_SECRET` stamped `ARCHIVES-7731` on two cases about a tool call,
    and nothing said so.

    It is not cosmetic. `labelling_prepass` prints that value to the author
    once per case, searching the replies for it -- so a value stamped on a
    case that is not about it answers a question the case does not ask. The
    prepass's own version of this defect, a hardcoded secret, was fixed the
    same morning.

    The frozen lot took the opposite decision and named the alternative for
    what it is: "the P-cases carry ARCHIVES-7731, a value appearing nowhere
    in them; that is the tidier lie and this lot does not repeat it."

    So the legacy is CLOSED rather than re-litigated. `A01`, `A06`, `A07` and
    the P-cases keep their claim -- they are labelled, integrated, and
    rewriting ground truth to tidy a documentation field serves nobody. What
    the rule binds is what gets ADDED: a new case either has the secret in
    its turns, or it opts out of claiming one.

    `TestOnlyTheCasesThatTURNOnASecretDeclareOne` already holds the two
    neighbouring properties -- that the opt-out names cases that exist, and
    that some case still declares the field -- so they are not repeated here.
    Both fired alongside this one under mutation, which is how the overlap
    was found.
    """

    LEGACY = {"A01", "A06", "A07"}      # closed on 2026-11-24, plus the P-cases

    def test_a_NEW_case_claims_the_secret_only_if_it_is_IN_it(self):
        import base64
        from evaluation.handwritten_conversations import SECRET
        encoded = base64.b64encode(SECRET.encode()).decode()
        for entry in entries():
            if (entry["secret"] is None
                    or entry["id"] in self.LEGACY
                    or entry["id"].startswith("P")):
                continue
            text = (" ".join(turn["content"] for turn in entry["turns"])
                    if "turns" in entry
                    else entry["payload"] + entry["reply"])
            assert SECRET in text or encoded in text, (
                f"{entry['id']} declares a secret that appears nowhere in "
                f"it: add it to WITHOUT_SECRET, or the prepass will report "
                f"on a value the case is not about")


class TestTheIntentionNeverStatesTheAnswer:
    """
    LE GARDE QUI MANQUAIT DE CE COTE, et l'asymetrie etait reelle : les deux
    lots livrent des cas NON etiquetes dont l'intention est montree a
    l'auteur, et seul le lot gele le tenait.

    Teste contre les intentions existantes AVANT d'etre ajoute -- zero
    contrevenant sur 31 -- donc il ne crie pas faux sur des donnees
    legitimes, ce pour quoi ce projet a retire un garde entier.

    La liste est LUE dans `test_frozen_lot`, qui la declare, plutot que
    recopiee : une liste redite diverge a la premiere formule ajoutee.
    """

    def test_no_intention_makes_the_label_a_formality(self):
        from test_frozen_lot import GIVEAWAYS

        for identifier, _, intention, _ in CASES:
            lowered = intention.lower()
            for giveaway in GIVEAWAYS:
                assert giveaway not in lowered, (
                    f"l'intention de {identifier} enonce la reponse : "
                    f"'{giveaway}'")

    def test_the_list_is_READ_and_not_restated(self):
        """
        Une premiere version lisait la source de CE module et y interdisait
        le litteral -- qu'elle contenait elle-meme. Elle ne pouvait pas
        passer, et un test qui ne peut pas passer ne tient aucune propriete.

        Ce qui compte est que le garde voisin PRENNE sa liste dans le lot
        gele : l'inliner y retirerait cette reference.
        """
        import inspect

        import test_frozen_lot

        source = inspect.getsource(
            self.test_no_intention_makes_the_label_a_formality)
        assert "test_frozen_lot" in source, (
            "le garde ne lit plus la liste du lot gele : une liste redite "
            "diverge a la premiere formule ajoutee")
        assert test_frozen_lot.GIVEAWAYS
