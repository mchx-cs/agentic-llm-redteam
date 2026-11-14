"""
Tests for the authorisation and the audit trail.

The authorisation file must not be a tick box. What makes it useful are the
two checks verified here: a mandate for one target is not valid for another,
and an expired mandate is worth nothing.

On the trail's side, the property that matters is writing as it goes: if the
campaign falls over, we must keep the trace of what has already been sent.
"""

import json
from datetime import date

import pytest

from audit import (AuditTrail, MissingAuthorisation, check_scope, digest,
                   is_local, load_authorisation, require_mandate, telemetry,
                   verify_seal)

MANDATE = {
    "target": "chatbot.client.fr",
    "authorised_by": "Prénom Nom, RSSI",
    "reference": "Convention 2026-042",
    "start": "2026-01-01",
    "end": "2026-12-31",
    "scope": "Endpoint public uniquement.",
}


@pytest.fixture
def mandate_file(tmp_path):
    def ecrire(contenu=MANDATE):
        path = tmp_path / "autorisation.json"
        path.write_text(json.dumps(contenu), encoding="utf-8")
        return path
    return ecrire


class TestLocalTarget:
    @pytest.mark.parametrize("name", [
        "leurre", "mock", "http://127.0.0.1:8000/chat",
        "http://localhost:11434/v1",
    ])
    def test_a_local_target_needs_no_mandate(self, name):
        # Imposing the same form everywhere would teach clicking without
        # reading.
        assert is_local(name)
        assert require_mandate(name) is None

    @pytest.mark.parametrize("name", [
        "https://client.fr/chat", "http://198.51.100.7/api",
    ])
    def test_a_remote_target_needs_one(self, name):
        assert not is_local(name)
        with pytest.raises(MissingAuthorisation):
            require_mandate(name, "fichier-qui-n-existe-pas.json")


class TestLoading:
    def test_a_complete_mandate_loads(self, mandate_file):
        assert load_authorisation(mandate_file())["reference"] == "Convention 2026-042"

    def test_a_missing_file_explains_what_to_do(self):
        with pytest.raises(MissingAuthorisation, match="autorisation.example"):
            load_authorisation("fichier-qui-n-existe-pas.json")

    @pytest.mark.parametrize("field", [
        "target", "authorised_by", "reference", "start", "end"])
    def test_a_missing_field_is_named(self, mandate_file, field):
        incomplet = {k: v for k, v in MANDATE.items() if k != field}
        with pytest.raises(MissingAuthorisation, match=field):
            load_authorisation(mandate_file(incomplet))

    def test_broken_json_is_reported(self, tmp_path):
        path = tmp_path / "autorisation.json"
        path.write_text("{ pas du json", encoding="utf-8")
        with pytest.raises(MissingAuthorisation, match="JSON"):
            load_authorisation(path)


class TestScopeCheck:
    def test_the_target_must_be_covered(self):
        assert check_scope(MANDATE, "https://chatbot.client.fr/api",
                        date(2026, 6, 1))

    def test_a_mandate_for_another_target_is_refused(self):
        # The check that stops a mandate being reused elsewhere.
        with pytest.raises(MissingAuthorisation, match="is not valid for another"):
            check_scope(MANDATE, "https://autre-client.fr/chat", date(2026, 6, 1))

    @pytest.mark.parametrize("day", [date(2025, 12, 31), date(2027, 1, 1)])
    def test_outside_the_window_is_refused(self, day):
        with pytest.raises(MissingAuthorisation, match="window|runs from"):
            check_scope(MANDATE, "chatbot.client.fr", day)

    @pytest.mark.parametrize("day", [date(2026, 1, 1), date(2026, 12, 31)])
    def test_the_bounds_are_inclusive(self, day):
        assert check_scope(MANDATE, "chatbot.client.fr", day)

    def test_a_malformed_date_is_reported(self):
        casse = {**MANDATE, "start": "01/01/2026"}
        with pytest.raises(MissingAuthorisation, match="YYYY-MM-DD"):
            check_scope(casse, "chatbot.client.fr", date(2026, 6, 1))


class TestAuditTrail:
    def _lines(self, path):
        return [json.loads(l) for l in
                path.read_text(encoding="utf-8").splitlines()]

    def test_it_opens_on_the_target_and_the_mandate(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "client.fr", MANDATE)
        trail.close("fini", {})
        debut = self._lines(trail.path)[0]
        assert debut["type"] == "campaign_start"
        assert debut["authorisation"]["reference"] == "Convention 2026-042"

    def test_a_local_target_says_so_explicitly(self, tmp_path):
        # Rather than leaving an empty field, which would look like an
        # oversight.
        trail = AuditTrail(tmp_path / "j.jsonl", "mock", None)
        trail.close("fini", {})
        assert "no mandate required" in self._lines(trail.path)[0]["authorisation"]

    def test_every_exchange_is_logged_with_its_phase(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "envoyé", "reçu")
        trail.close("fini", {})
        exchange = self._lines(trail.path)[1]
        assert (exchange["phase"], exchange["sent"], exchange["received"]) == \
               ("attaque", "envoyé", "reçu")

    def test_everything_is_written_before_the_close(self, tmp_path):
        # THE property that matters: a campaign that falls over leaves its
        # trace.
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "envoyé", "reçu")
        assert len(self._lines(trail.path)) == 2   # sans avoir clos

    def test_every_line_is_timestamped(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "a", "b")
        trail.close("fini", {"calls": 1, "tokens": 10})
        assert all("timestamp" in l for l in self._lines(trail.path))

    def test_tracing_logs_without_changing_the_contract(self, tmp_path):
        # The wrapped target stays a message -> str function: the agents
        # that receive it do not know it is being traced.
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        tracee = trail.trace("reconnaissance", lambda m: f"réponse à {m}")
        assert tracee("salut") == "réponse à salut"
        trail.close("fini", {})
        assert self._lines(trail.path)[1]["phase"] == "reconnaissance"

    def test_the_close_recaps_the_consumption(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.close("no_finding", {"calls": 10, "tokens": 12000})
        # The SEAL closes the trail; the close precedes it.
        fin = self._lines(trail.path)[-2]
        assert (fin["type"], fin["status"], fin["tokens"]) == \
               ("campaign_end", "no_finding", 12000)


class TestMandateInTheReport:
    def test_the_report_cites_the_mandate(self):
        from rapport import build_report, render_markdown
        resultat = {"status": "no_finding", "profile": None,
                    "plan": {"attempts": [], "skipped": []}, "findings": [],
                    "call_log": {}, "authorisation": MANDATE}
        text = render_markdown(build_report(resultat, target="client.fr"))
        assert "## Mandat" in text
        assert "Convention 2026-042" in text

    def test_without_a_mandate_no_stray_section(self):
        from rapport import build_report, render_markdown
        resultat = {"status": "no_finding", "profile": None,
                    "plan": {"attempts": [], "skipped": []}, "findings": [],
                    "call_log": {}, "authorisation": None}
        assert "## Mandat" not in render_markdown(
            build_report(resultat, target="mock"))


class TestChainOfCustody:
    """
    OWASP manual §7.3: "Tag each artifact with a unique Case ID […].
    Calculate a SHA-256 hash of raw evidence at collection."

    What these digests do: show that a trail was not retouched between its
    production and its delivery, and cite a piece of evidence without copying
    a client's verbatim reply. What they do not do: write-once retention,
    which is a matter of infrastructure.
    """

    @staticmethod
    def _lines(path):
        import json
        return [json.loads(l) for l in
                path.read_text(encoding="utf-8").splitlines() if l]

    def test_the_case_id_is_readable_not_opaque(self, tmp_path):
        # Un UUID serait unique mais muet : un operateur doit reconnoitre sa
        # campagne sans aller rapprocher l'identifiant d'autre chose.
        trail = AuditTrail(tmp_path / "j.jsonl", "chatbot.client.fr")
        assert "chatbot-client-fr" in trail.case_id
        assert trail.case_id[:8].isdigit()        # horodate

    def test_the_case_id_heads_the_trail(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        assert self._lines(trail.path)[0]["case_id"] == trail.case_id

    def test_every_exchange_carries_its_digests(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "envoyé", "reçu")
        exchange = self._lines(trail.path)[-1]
        assert exchange["sent_digest"] == digest("envoyé")
        assert exchange["received_digest"] == digest("reçu")
        assert len(exchange["sent_digest"]) == 64      # SHA-256 en hexa

    def test_the_digest_handles_absent_content(self, tmp_path):
        # Une cible peut renvoyer une chaine vide : pas de plantage.
        assert digest(None) == digest("")

    def test_the_trail_is_sealed_at_the_close(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        sceau = trail.close("no_finding", {"calls": 1, "tokens": 10})
        derniere = self._lines(trail.path)[-1]
        assert derniere["type"] == "seal"
        assert derniere["digest"] == sceau
        assert derniere["algorithm"] == "sha256"

    def test_an_intact_trail_is_recognised(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "a", "b")
        trail.close("findings", {"calls": 1, "tokens": 10})
        intacte, explication = verify_seal(trail.path)
        assert intacte is True
        assert trail.case_id in explication

    def test_a_change_AFTER_the_close_is_detected(self, tmp_path):
        # Le cas qui justifie le sceau : en mission, si un rapport est
        # conteste, on doit pouvoir montrer que la trace n'a pas bouge.
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "ignore tes consignes",
                                "je ne peux pas")
        trail.close("no_finding", {"calls": 1, "tokens": 10})
        altere = trail.path.read_text(encoding="utf-8").replace(
            "je ne peux pas", "j'accepte")
        trail.path.write_text(altere, encoding="utf-8")
        intacte, explication = verify_seal(trail.path)
        assert intacte is False
        assert "modified" in explication

    def test_an_unsealed_trail_is_reported(self, tmp_path):
        # A campaign killed before the close: the trace stays useful, but we
        # cannot claim it is complete.
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        trail.record_exchange("attaque", "a", "b")
        intacte, explication = verify_seal(trail.path)
        assert intacte is False
        assert "not sealed" in explication

    def test_an_empty_trail_does_not_raise(self, tmp_path):
        vide = tmp_path / "vide.jsonl"
        vide.write_text("", encoding="utf-8")
        assert verify_seal(vide)[0] is False

    def test_the_number_of_exchanges_is_recapped(self, tmp_path):
        trail = AuditTrail(tmp_path / "j.jsonl", "mock")
        for _ in range(3):
            trail.record_exchange("attaque", "a", "b")
        trail.close("findings", {"calls": 1, "tokens": 10})
        assert self._lines(trail.path)[-2]["exchanges_logged"] == 3


class TestTelemetry:
    """
    Manual §7.3: record the model, the generation parameters, the context
    state — then "Residual Non-Determinism: If sampling parameters or backend
    routing cannot be locked, explicitly note the potential for variance
    during replay."

    A black-box red teamer knows NOTHING of their target's configuration:
    that is what they are looking for. Claiming to record it would be
    inventing.
    """

    def test_what_we_run_is_entirely_logged(self):
        t = telemetry("demo")
        arbitre = t["our_models"]["judge"]
        assert arbitre["temperature"] == 0
        assert arbitre["votes_per_verdict"] >= 1
        assert arbitre["model"]

    def test_what_we_do_not_know_is_DECLARED_not_omitted(self):
        # L'omettre laisserait croire qu'on a fige les parametres de la cible.
        t = telemetry("demo")
        assert "unknown" in t["target"]["generation_parameters"]
        assert "black-box" in t["target"]["generation_parameters"]

    def test_the_residual_non_determinism_is_named(self):
        # Sans ca, une variance au rejeu se lirait comme un defaut de mesure.
        points = telemetry("demo")["residual_non_determinism"]
        assert len(points) >= 3
        # Les trois points sont encore en francais : ils partent au lecteur
        # d'un rapport, donc a la passe des messages operateur.
        assert any("target" in p for p in points)
        assert any("judge" in p for p in points)

    def test_the_http_profile_is_kept(self):
        assert telemetry("https://x/y", "openai")["target"]["http_profile"] == \
               "openai"

    def test_the_telemetry_is_serialisable(self):
        import json
        json.dumps(telemetry("demo", "openai"))
