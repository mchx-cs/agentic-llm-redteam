"""
Tests for reading data written before the data keys were translated.

Three kinds of file live outside git, so the in-place migration never reached
them: the local garak snapshot, a harvest waiting to be labelled, and every
`resultat.json` and sealed trail already produced. The project explicitly
supports reading older results, so a key rename cannot simply break them.

The last class here is the one that matters most: it pins the EIGHT names that
did NOT move, and says why.
"""

import json

from migration import LEGACY_KEYS, LEGACY_VALUES, modernise


class TestModernise:
    def test_it_is_a_no_op_on_current_data(self):
        """
        The property that makes it safe to call on every read: running it on
        data that is already current must change nothing at all.
        """
        current = {"campaign": {"target": "demo", "status": "no_finding"},
                   "findings": [], "coverage": {"families_tested": ["LLM01"]}}
        assert modernise(current) == current

    def test_a_key_moves(self):
        assert modernise({"constats": []}) == {"findings": []}

    def test_it_recurses_through_lists_and_dicts(self):
        old = {"constats": [{"gravite": "elevee", "reponse": "r"}]}
        assert modernise(old) == {
            "findings": [{"severity": "high", "reply": "r"}]}

    def test_an_enumerated_value_moves(self):
        assert modernise({"etats": ["faille", "juge_indecis"]}) == {
            "states": ["vulnerability", "judge_undecided"]}

    def test_a_count_keyed_by_state_moves(self):
        assert modernise({"taux_de_succes": {"comptes": {"faille": 2}}}) == {
            "success_rate": {"counts": {"vulnerability": 2}}}

    def test_a_targets_sentence_is_NEVER_translated(self):
        """
        The guard that keeps this module honest. A target can perfectly well
        write the word "faille" in its reply; only fields known to hold an
        enumeration get their value renamed.
        """
        old = {"reponse": "il y a une faille ici", "statut": "aucun_constat"}
        new = modernise(old)
        assert new["reply"] == "il y a une faille ici"
        assert new["status"] == "no_finding"

    def test_the_two_maps_do_not_overlap(self):
        # A name that was both a key and an enumerated value would be renamed
        # twice in different ways depending on where it appeared.
        assert not set(LEGACY_KEYS) & set(LEGACY_VALUES)


class TestAnOlderReportStillRenders:
    def test_a_french_keyed_result_renders(self):
        from rapport import build_report, render_markdown

        old = {
            "statut": "aucun_constat", "fiche": None,
            "plan": {"essais": [], "candidats": [], "ecartees": []},
            "constats": [], "ecourtee": None,
            "journal": {"appels": 3, "tokens": 100, "tronquees": []},
            "lances": [{"technique": "dan", "famille_owasp": "LLM01",
                        "objectif": "o", "transformation": "identite",
                        "texte": "p"}],
        }
        text = render_markdown(build_report(old, target="demo"))
        assert "LLM01" in text
        assert "## Couverture" in text

    def test_an_older_finding_keeps_its_severity(self):
        from rapport import build_report

        old = {
            "statut": "constats", "fiche": None,
            "plan": {"essais": [], "candidats": [], "ecartees": []},
            "constats": [{
                "essai": 1,
                "payload": {"technique": "dan", "famille_owasp": "LLM01",
                            "objectif": None, "transformation": "identite",
                            "texte": "p"},
                "reponse": "le code est X",
                "verdict": {"reussi": True, "critere": "divulgation",
                            "analyse": "a", "valeur": "X"},
                "verification": {"statut": "confirmee",
                                 "explication": "e", "valeurs_rejeu": ["X"]},
                "tronquee": False}],
            "journal": {},
        }
        report = build_report(old, target="demo")
        assert report["findings"][0]["severity"] == "high"


class TestAnOlderSealedTrailStillVerifies:
    def test_a_trail_written_with_french_keys_verifies(self, tmp_path):
        """
        The seal hashes the trail's raw BYTES, so modernising the parsed dict
        to find `digest` changes nothing about the hash.
        """
        from audit import digest, verify_seal

        trail = tmp_path / "ancienne.jsonl"
        lines = [
            {"horodatage": "2026-11-12T18:00:00", "type": "debut_campagne",
             "case_id": "20261112-180000-mock", "cible": "mock"},
            {"horodatage": "2026-11-12T18:00:01", "type": "fin_campagne",
             "statut": "aucun_constat", "appels": 3},
        ]
        body = "".join(json.dumps(line, ensure_ascii=False) + "\n"
                       for line in lines)
        trail.write_text(body, encoding="utf-8")
        seal = digest(body)
        with trail.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"horodatage": "2026-11-12T18:00:02",
                                "type": "sceau",
                                "case_id": "20261112-180000-mock",
                                "algorithme": "sha256",
                                "empreinte": seal}) + "\n")

        intact, explanation = verify_seal(trail)
        assert intact is True, explanation

    def test_a_retouched_older_trail_is_still_caught(self, tmp_path):
        from audit import digest, verify_seal

        trail = tmp_path / "retouchee.jsonl"
        body = json.dumps({"type": "debut_campagne", "cible": "mock"}) + "\n"
        trail.write_text(body, encoding="utf-8")
        with trail.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "sceau", "algorithme": "sha256",
                                "empreinte": digest(body)}) + "\n")
        # Someone rewrites the first line afterwards.
        altered = trail.read_text(encoding="utf-8").replace("mock", "autre")
        trail.write_text(altered, encoding="utf-8")
        assert verify_seal(trail)[0] is False


class TestTheJudgesPromptDidNotMove:
    """
    EIGHT names stayed French, and the reason is measured, not aesthetic.

    The judge's output schema (`analyse`, `enfreint`, `critere`, `valeur`) and
    its four criterion values live INSIDE `JUDGE_SYSTEM_PROMPT`. Renaming them
    would change the artefact the 89 / 100 / 96 were measured on, so the
    published figures would no longer describe the prompt in the repository.
    Re-measuring costs a dev run and a frozen-set consultation.

    These tests exist so the next rename pass hits a wall instead of a
    published number.
    """

    HELD = ("analyse", "enfreint", "critere", "valeur",
            "divulgation", "obeissance", "abus_outils", "aucun")

    def test_the_eight_held_names_are_still_in_the_prompt(self):
        from agents.arbitre import JUDGE_SYSTEM_PROMPT
        for name in self.HELD:
            assert name in JUDGE_SYSTEM_PROMPT, name

    def test_none_of_them_is_in_the_migration_map(self):
        # If one appeared there, a future `modernise` would rewrite the very
        # values the judge is instructed to emit.
        for name in self.HELD:
            assert name not in LEGACY_KEYS, name
            assert name not in LEGACY_VALUES, name

    def test_the_prompt_is_the_one_that_was_measured(self):
        # Its length is pinned: any edit, a key rename included, moves it.
        from agents.arbitre import JUDGE_SYSTEM_PROMPT
        assert len(JUDGE_SYSTEM_PROMPT) == 4375

    def test_the_verdict_still_speaks_the_prompts_language(self):
        # The reader of a verdict dict and the judge's instruction must agree.
        import agents.arbitre as arbitre

        original = arbitre.ask_llm
        arbitre.ask_llm = lambda *a, **k: (
            '{"analyse": "a", "enfreint": true, '
            '"critere": "divulgation", "valeur": "X"}')
        try:
            verdict = arbitre.judge("p", "r")
        finally:
            arbitre.ask_llm = original
        assert verdict["critere"] == "divulgation"
        assert verdict["valeur"] == "X"
