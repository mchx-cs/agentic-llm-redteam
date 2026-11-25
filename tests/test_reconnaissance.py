"""
Tests for reconnaissance, with no call to a model at all.

We do not test the QUALITY of the profile here — that is the job of
`evaluation/check_reconnaissance.py`, which needs a real model and simulated
targets. We test what must be true whatever a model answers: the profile's
normalisation, and above all the two TRI-STATES added on 2026-11-11.

Why they deserve tests of their own: `produit_du_code` and
`traite_des_documents` are True, False or None, and the difference between
False ("the target says it cannot") and None ("it said nothing about it")
decides whether nine to sixteen probes are skipped. A `bool()` dropped in by
accident would turn every silence into a refusal, and the campaign would lose
whole families — without raising the slightest exception.
"""

import pytest

import agents.reconnaissance as reconnaissance
from agents.reconnaissance import (DEFAULT_PROBE_LANGUAGE, KNOWN_CONTEXTS,
                                  PROBES, reconnoitre,
                                   summarise)

CHAMPS_ATTENDUS = {"role", "language", "tools", "refused_subjects",
                   "mentions_instructions", "writes_code",
                   "handles_documents", "context", "evidence", "exchanges",
                   "warning"}


@pytest.fixture
def analyst(monkeypatch):
    """Replaces the call to the analyst model with a chosen output."""
    def installer(output):
        monkeypatch.setattr(reconnaissance, "ask_llm",
                            lambda *a, **k: output)
    return installer


def _target(reply="une réponse"):
    return lambda message: reply


class TestProfileShape:
    def test_every_field_is_present(self, analyst):
        analyst('{"role": "assistant", "langue": "fr"}')
        assert set(reconnoitre(_target())) == CHAMPS_ATTENDUS

    def test_an_unreadable_analysis_gives_an_empty_profile_not_an_invented_one(
            self, analyst):
        # An incomplete profile is useful, an invented one is harmful.
        analyst("ceci n'est pas du JSON")
        profile = reconnoitre(_target())
        assert set(profile) == CHAMPS_ATTENDUS
        assert profile["warning"]
        assert profile["role"] is None
        assert profile["tools"] == []

    def test_an_empty_profile_keeps_the_exchanges(self, analyst):
        # Without them, there is no way to understand why the analysis
        # failed.
        analyst("pas du JSON")
        assert len(reconnoitre(_target())["exchanges"]) == len(
            PROBES[DEFAULT_PROBE_LANGUAGE])

    def test_the_types_are_enforced(self, analyst):
        # Un champ du mauvais type deviendrait une erreur beaucoup plus loin,
        # dans le planificateur.
        analyst('{"role": 42, "tools": "pas une liste", '
                 '"refused_subjects": [1, "vrai sujet"], "evidence": null}')
        profile = reconnoitre(_target())
        assert profile["role"] is None
        assert profile["tools"] == []
        assert profile["refused_subjects"] == ["vrai sujet"]
        assert profile["evidence"] == []


class TestTriStates:
    """
    The False / None distinction decides whether `packagehallucination`
    (7 probes) and `latentinjection` (9 probes) are skipped.
    """

    @pytest.mark.parametrize("field", ["writes_code",
                                       "handles_documents"])
    @pytest.mark.parametrize("valeur, attendu", [
        ("true", True),
        ("false", False),
        ("null", None),
    ])
    def test_the_three_states_survive(self, analyst, field, valeur,
                                       attendu):
        analyst('{"%s": %s}' % (field, valeur))
        assert reconnoitre(_target())[field] is attendu

    @pytest.mark.parametrize("field", ["writes_code",
                                       "handles_documents"])
    def test_a_missing_field_means_none_not_false(self, analyst, field):
        # THE trap: `bool()` or `.get(field, False)` would turn every
        # silence into a refusal, and the campaign would lose sixteen probes.
        analyst('{"role": "assistant"}')
        assert reconnoitre(_target())[field] is None

    @pytest.mark.parametrize("field", ["writes_code",
                                       "handles_documents"])
    def test_a_non_boolean_value_means_none(self, analyst, field):
        # A model can answer "oui" instead of true: we do not guess, we fall
        # back on "not declared".
        analyst('{"%s": "oui"}' % field)
        assert reconnoitre(_target())[field] is None

    def test_an_empty_profile_sets_them_to_none(self, analyst):
        analyst("unreadable")
        profile = reconnoitre(_target())
        assert profile["writes_code"] is None
        assert profile["handles_documents"] is None


class TestDeclaredContext:
    """
    The context comes from the OPERATOR, never from a probe: a target does not
    know what its output is rendered in, and asking it would invite
    hallucination.
    """

    def test_reconnaissance_never_fills_it(self, analyst):
        # Even if the analyst model claims to know it.
        analyst('{"contexte": ["terminal", "rendu-riche"]}')
        assert reconnoitre(_target())["context"] == []

    def test_no_probe_asks_about_the_context(self):
        # Garde-fou contre la tentation : si quelqu'un ajoute « ta sortie est
        # rendered as Markdown?" is ever added to the probes, this test
        for langue, sondes in PROBES.items():
            questions = " ".join(sondes).lower()
            for interdit in ("markdown", "html", "terminal", "rendu",
                             "rendered"):
                assert interdit not in questions, (langue, interdit)

    def test_the_context_names_are_documented(self):
        # Ils apparaissent dans le message d'erreur de la ligne de commande :
        # un nom sans explication ne guiderait personne.
        assert KNOWN_CONTEXTS
        for name, explication in KNOWN_CONTEXTS.items():
            assert name == name.lower()
            assert explication.strip()


class TestBudgetAndDisplay:
    def test_the_probing_loop_is_bounded(self, monkeypatch, analyst):
        # Toute boucle a sa limite : ici RECON_BUDGET, distinct de
        # MAX_ATTEMPTS, because probing can already wake the defences.
        monkeypatch.setattr(reconnaissance, "RECON_BUDGET", 2)
        analyst("{}")
        assert len(reconnoitre(_target())["exchanges"]) == 2

    def test_every_probe_targets_one_field(self):
        # A recorded principle: one probe fewer must mean one fact fewer,
        # never a false profile. Hence one probe per probed field -- IN EVERY
        # LANGUAGE, because `RECON_BUDGET` slices by position: a set with one
        # probe fewer would silently stop gating a family.
        champs = {"role", "capacites", "refused_subjects", "tools",
                  "writes_code", "handles_documents"}
        for langue, sondes in PROBES.items():
            assert len(sondes) == len(champs), langue

    def test_the_summary_shows_the_new_fields(self, analyst):
        analyst('{"writes_code": true, "handles_documents": false}')
        rendu = summarise(reconnoitre(_target()))
        assert "writes code : yes" in rendu
        assert "reads documents : no" in rendu
        assert "context declared : none" in rendu

    def test_the_summary_tells_no_from_not_declared(self, analyst):
        analyst('{"produit_du_code": null}')
        assert "writes code : not declared" in summarise(reconnoitre(_target()))


class TestTheANALYSTCanFail:
    """
    `reconnoitre` was built to survive a model that returns GARBAGE — the
    empty profile, never an invented one — and until 2026-11-23 it did not
    survive a provider REFUSING to answer. Same outcome, no usable analysis;
    two endings, and the loud one took the campaign with it.

    Measured cost: Groq answered `400 - Failed to generate JSON` on pair 13
    of a 20-pair measurement. Twelve pairs had succeeded and the eight
    remaining ones died with it.
    """

    @staticmethod
    def _refusing(monkeypatch, failure):
        def refuse(*a, **k):
            raise failure
        monkeypatch.setattr(reconnaissance, "ask_llm", refuse)

    def test_a_provider_refusal_yields_a_profile_not_a_crash(self,
                                                             monkeypatch):
        self._refusing(monkeypatch, RuntimeError("400 Failed to generate JSON"))
        profile = reconnoitre(_target())
        assert set(profile) == CHAMPS_ATTENDUS
        assert profile["warning"], (
            "an empty profile must carry its reason, or the report shows "
            "dashes with nothing to explain them")

    def test_and_the_OBSERVED_facts_survive_it(self, monkeypatch):
        """
        The facts that need no model to establish are exactly the ones worth
        keeping when the model is unavailable. A tool marker seen in a probe
        reply is a tool DEMONSTRATED, and losing it because an analysis
        failed would narrow the campaign for a reason that has nothing to do
        with the target.
        """
        self._refusing(monkeypatch, RuntimeError("provider down"))
        profile = reconnoitre(_target("[OUTIL : consulter_dossier(nom)]"))
        assert profile["tools"], (
            "a tool seen in a reply must survive a failed analysis")
        assert any(line.startswith(reconnaissance.OBSERVED)
                   for line in profile["evidence"])

    def test_BUDGET_EXCEEDED_still_PROPAGATES(self, monkeypatch):
        """
        THE exception to the exception, and the one that must not be
        swallowed. `BudgetExceeded` is the circuit breaker: `main` catches it
        around this very call to stop the campaign CLEANLY — status
        `budget_exhausted`, findings kept, report announcing it was cut short
        — rather than as a failure.

        Catching it here would disarm phase 11 at the one moment the campaign
        would otherwise keep spending, and it would do so silently: the
        campaign would carry on with an empty profile, against a ceiling it
        has already reached.
        """
        from llm_client import BudgetExceeded
        self._refusing(monkeypatch, BudgetExceeded("ceiling reached"))
        with pytest.raises(BudgetExceeded):
            reconnoitre(_target())

    def test_the_warning_records_the_failure_VERBATIM(self, monkeypatch):
        """
        The type and the message, not a diagnosis. This agent must not know
        which SDK is behind `ask_llm`, so it cannot tell a provider's refusal
        from a bug of ours — and announcing both as "the provider refused"
        would blame the wrong component. This project shipped that defect
        once, when a failing attacker model made the orchestrator advise
        `--probe-target` at an innocent target.
        """
        self._refusing(monkeypatch, TypeError("une erreur bien a nous"))
        warning = reconnoitre(_target())["warning"]
        assert "TypeError" in warning and "une erreur bien a nous" in warning

    def test_both_readings_say_what_an_empty_profile_COSTS(self, monkeypatch,
                                                           analyst):
        """
        A reader of the report cannot tell which of the two produced their
        empty profile, and the cost is the same either way: the planner's
        prerequisites rule families out for want of facts ABOUT the target,
        not because the target lacks what they need. Hence one shared
        sentence rather than two copies, which would diverge on the first
        edit.
        """
        self._refusing(monkeypatch, RuntimeError("boom"))
        refused = reconnoitre(_target())["warning"]
        analyst("pas du JSON du tout")
        unreadable = reconnoitre(_target())["warning"]

        assert refused != unreadable, "the CAUSE must still be nameable"
        for warning in (refused, unreadable):
            assert reconnaissance._WHAT_AN_EMPTY_PROFILE_COSTS in warning

    def test_an_empty_profile_asserts_NO_DENIAL(self, monkeypatch):
        """
        `mentions_instructions` was a hard `False` in the empty profile,
        which ASSERTS A DENIAL THE TARGET NEVER MADE — there was no analysis
        for it to be made in. Found by running the guard above against a real
        campaign, not by reading the code.

        The tri-state exists since 2026-11-20 precisely so that silence
        cannot be read as a refusal; the empty profile predates it and kept
        fabricating one. Its two siblings were already `None`, with the
        reason written beside them.
        """
        self._refusing(monkeypatch, RuntimeError("provider down"))
        profile = reconnoitre(_target())
        assert profile["mentions_instructions"] is None, (
            "silence is not a denial, and an absent analysis is not even "
            "silence from the target")

    def test_and_the_PLAN_no_longer_skips_the_leak_families(self, monkeypatch):
        """
        The consequence, and the reason this is not cosmetic. That reason
        text is what skips the prompt-leak families, and on the campaign that
        exposed it the plan skipped seven techniques plus three more on a
        denial that was never made — the zero-attempt failure mode of
        2026-11-19 reached from the other side.

        It is tested through the PLANNER rather than on the field alone,
        because the field is only wrong by what it causes, and two modules
        correct on their own are the defect shape this project keeps meeting.
        """
        from agents.planner import plan_campaign

        self._refusing(monkeypatch, RuntimeError("provider down"))
        plan = plan_campaign(reconnoitre(_target()), budget=3)
        reasons = " ".join(reason for skip in plan["skipped"]
                           for reason in skip["reasons"])
        assert "SAYS it has no internal instruction" not in reasons, (
            "a target that never answered cannot be reported as DENYING it "
            "has instructions")


class TestTheCAMPAIGNSurvivesIt:
    """
    The junction, and the thing that actually broke. `reconnoitre` and
    `run_campaign` were each correct on their own; nothing covered the glue —
    the defect shape this project has now met ten times, from `_inject` to
    the mangled `measure()` call.

    So this drives `run_campaign` with the REAL reconnaissance and a refusing
    analyst, rather than replacing `reconnoitre` the way the other campaign
    tests do. Replacing it would test the stub.
    """

    def test_a_refused_analysis_no_longer_ends_the_campaign(self, monkeypatch):
        import contextlib
        import io

        import main

        def refuse(*a, **k):
            raise RuntimeError("400 Failed to generate JSON")
        monkeypatch.setattr(reconnaissance, "ask_llm", refuse)
        monkeypatch.setattr(main, "judge_by_vote",
                            lambda payload, reply: {
                                "reussi": False, "critere": "aucun",
                                "analyse": "x", "valeur": None,
                                "votes": [False] * 3, "brut": ""})
        monkeypatch.setattr(main, "MAX_ATTEMPTS", 2)

        with contextlib.redirect_stdout(io.StringIO()):
            result = main.run_campaign(lambda m: "Je ne peux pas.", "mock")

        assert result["status"] != "interrupted", (
            "a provider that refuses one analysis must not end the campaign")
        assert result["profile"]["warning"], (
            "and the result must carry WHY the profile is empty — it is the "
            "only place the report can read it from")


class TestTheProbeLanguageIsDECLARED:
    """
    French only until 2026-11-25, so every profile of an English-speaking
    target was built on an exchange opened in French — and probing is the
    first thing this tool does.

    The target's language is exactly what the probes are meant to discover,
    so there is nothing to read before the first one goes out: it is the
    operator's declaration, like `--context`.
    """

    def test_french_is_the_default(self):
        # Every bundled target and every published figure is French.
        assert DEFAULT_PROBE_LANGUAGE == "fr"

    def test_both_sets_exist(self):
        assert set(PROBES) == {"fr", "en"}

    def test_the_english_set_is_really_english(self, analyst):
        analyst("{}")
        profile = reconnoitre(_target(), language="en")
        asked = " ".join(e["question"] for e in profile["exchanges"])
        assert "Could you introduce yourself" in asked
        assert "Peux-tu" not in asked

    def test_the_declared_language_is_what_goes_OUT(self, analyst):
        # The junction: a flag parsed and not reaching the probes would leave
        # the campaign believing it had probed in English.
        analyst("{}")
        for langue in PROBES:
            profile = reconnoitre(_target(), language=langue)
            asked = [e["question"] for e in profile["exchanges"]]
            assert asked == PROBES[langue][:6], langue

    def test_an_unknown_language_is_REFUSED(self):
        # A typo must not quietly probe in the wrong language, which is the
        # defect this parameter exists to fix.
        with pytest.raises(ValueError, match="Unknown probe language"):
            reconnoitre(_target(), language="de")

    def test_the_english_probes_gate_the_SAME_families(self):
        # Each probe gates something: `packagehallucination` on whether the
        # target writes code, `latentinjection` on whether it reads a
        # document handed to it. A reworded probe would gate another thing,
        # and `RECON_BUDGET` counts POSITIONS.
        assert "code" in PROBES["en"][4].lower()
        assert "document" in PROBES["en"][5].lower()
        assert "code" in PROBES["fr"][4].lower()
        assert "document" in PROBES["fr"][5].lower()


class TestAMismatchIsFLAGGED:
    """
    Probing an English-speaking target in French still produces a profile —
    models answer across languages — so the mistake is SILENT and the profile
    is built on an exchange nobody meant to have. Free to detect: the analyst
    already reports the language it read.
    """

    def test_it_warns_when_the_target_answers_in_another_language(self,
                                                                  analyst):
        analyst('{"language": "en"}')
        profile = reconnoitre(_target(), language="fr")
        assert profile["warning"]
        assert "--target-language en" in profile["warning"]

    def test_it_says_NOTHING_when_they_agree(self, analyst):
        # The contrast: a warning on every run would be noise, and this
        # project has removed a guard for crying wrong.
        analyst('{"language": "fr"}')
        assert reconnoitre(_target(), language="fr")["warning"] is None

    def test_a_locale_still_counts_as_agreement(self, analyst):
        # "fr-FR" is French: comparing the first two characters is what keeps
        # this from firing on a locale tag.
        analyst('{"language": "fr-FR"}')
        assert reconnoitre(_target(), language="fr")["warning"] is None

    def test_and_the_PROFILE_still_stands(self, analyst):
        # A warning, never a refusal: a bilingual target, or one answering in
        # the user's language, is a legitimate case this must not block.
        analyst('{"language": "en", "tools": ["un_outil"]}')
        profile = reconnoitre(_target(), language="fr")
        assert profile["tools"] == ["un_outil"]

    def test_a_target_that_says_nothing_about_its_language_is_not_flagged(
            self, analyst):
        analyst("{}")
        assert reconnoitre(_target(), language="fr")["warning"] is None
