"""
Tests for the planner.

This is deterministic code — which was the point: give the decision to rules
rather than to a model, so that it can be checked. Here is the check.

Two things matter equally: that it keeps the right families, and that it says
WHY it skipped the others. A tool that keeps quiet about what it did not test
gives a false impression of coverage.
"""

import pytest

import agents.attaquant
from agents.planificateur import (PREREQUISITES, group_by_reason,
                                  objectives_for, plan_campaign,
                                  summarise)


@pytest.fixture(autouse=True)
def without_garak_snapshot(monkeypatch, tmp_path):
    """
    Isole les tests de l'instantané garak éventuellement présent en local.

    Sans ça, ces tests passeraient ou non selon qu'on a lancé
    `exporter_garak.py` — un test ne doit pas dépendre de ça.
    """
    monkeypatch.setattr(agents.attaquant, "GARAK_FILE",
                        tmp_path / "absent.json")


def profile(role="assistant", tools=(), refused=(), instructions=False,
          code=None, documents=None, context=()):
    # `code` and `documents` are TRI-STATES: None = the target said nothing
    # about it, which is not "it cannot do it".
    return {"role": role, "langue": "fr", "outils": list(tools),
            "sujets_refuses": list(refused), "mentionne_consignes": instructions,
            "produit_du_code": code, "traite_des_documents": documents,
            "contexte": list(context),
            "indices": [], "echanges": [], "avertissement": None}


def _skipped(plan):
    return {e["technique"]: e["motifs"] for e in plan["ecartees"]}


class TestPrerequisites:
    def test_without_a_tool_tool_abuse_is_skipped(self):
        plan = plan_campaign(profile(tools=[]), budget=10)
        assert "aucun outil détecté chez la cible" in \
               _skipped(plan)["abus-outils"]

    def test_with_a_tool_the_technique_is_kept(self):
        # Since the four LLM06 payloads of 2026-11-12, a detected tool is
        # enough: the technique is no longer skipped at all, neither for the
        # prerequisite nor for want of a template.
        plan = plan_campaign(profile(tools=["virement"]), budget=10)
        assert "abus-outils" not in _skipped(plan)
        assert "abus-outils" in {c["technique"] for c in plan["candidats"]}

    def test_a_silent_target_has_the_leak_families_skipped(self):
        plan = plan_campaign(profile(), budget=10)
        skipped = _skipped(plan)
        assert any("ne déclare ni sujet interdit" in m
                   for m in skipped["divulgation-information"])
        assert any("n'évoque aucune consigne" in m
                   for m in skipped["fuite-prompt-systeme"])

    @pytest.mark.parametrize("target", [
        profile(refused=["le code du coffre"]),
        profile(instructions=True),
    ])
    def test_a_target_protecting_something_keeps_them(self, target):
        skipped = _skipped(plan_campaign(target, budget=10))
        assert not any("ne déclare ni sujet interdit" in m
                       for m in skipped["divulgation-information"])

    def test_a_technique_with_no_template_is_skipped_and_says_so(self):
        # The OWASP families are declared but empty: they must disappear
        # from the plan WITH their reason, not silently.
        skipped = _skipped(plan_campaign(profile(instructions=True), budget=10))
        assert "aucun modèle de payload dans la bibliothèque" in \
               skipped["injection-directe"]


class TestObjectives:
    def test_the_targets_refusals_become_objectives(self):
        # That is the whole point of reconnaissance: aim at what THIS target
        # protects, instead of generic objectives.
        objectives = objectives_for(profile(refused=["le code du coffre"]),
                                   {"objectifs": []})
        assert any("le code du coffre" in o["formulation"] for o in objectives)
        assert all(o["origine"] == "reconnaissance" for o in objectives)

    def test_the_librarys_objectives_are_kept(self):
        bibliotheque = {"objectifs": [{"id": "x", "formulation": "f",
                                       "origine": "bibliotheque"}]}
        assert len(objectives_for(profile(), bibliotheque)) == 1


class TestBudgetAndOrder:
    @pytest.mark.parametrize("budget", [0, 1, 3, 100])
    def test_the_budget_is_never_exceeded(self, budget):
        plan = plan_campaign(profile(refused=["un secret"]), budget=budget)
        assert len(plan["essais"]) <= budget

    def test_reconnaissance_derived_objectives_go_first(self):
        plan = plan_campaign(profile(refused=["le code du coffre"]), budget=4)
        assert plan["essais"][0]["objectif"].startswith("refus-")

    def test_raw_text_goes_before_its_transformations(self):
        plan = plan_campaign(profile(refused=["un secret"]), budget=4)
        assert plan["essais"][0]["transformation"] == "identite"

    def test_two_identical_plannings_give_the_same_plan(self):
        # A stable sort: a campaign must be reproducible.
        target = profile(refused=["un secret"])
        a = [e["texte"] for e in plan_campaign(target, 5)["essais"]]
        b = [e["texte"] for e in plan_campaign(target, 5)["essais"]]
        assert a == b


class TestAttemptShape:
    def test_every_attempt_says_where_it_comes_from(self):
        # Without this, the report could not say WHICH combination worked.
        for attempt in plan_campaign(profile(refused=["un secret"]), budget=3)["essais"]:
            assert {"technique", "famille_owasp", "objectif",
                    "transformation", "texte"} <= set(attempt)

    def test_no_template_marker_survives(self):
        for attempt in plan_campaign(profile(refused=["un secret"]), budget=5)["essais"]:
            assert "{objectif}" not in attempt["texte"]


class TestCandidatePool:
    """
    La phase 3a pioche dans un vivier au lieu d'une liste figee. Le plan
    initial reste borne par le budget ; le vivier, lui, ne doit PAS l'etre,
    sinon un essai releguee ne pourrait jamais remonter quand la cible
    revele qu'il etait pertinent.
    """

    def test_the_pool_is_not_truncated_by_the_budget(self):
        plan = plan_campaign(profile(refused=["le code du coffre"]), budget=1)
        assert len(plan["essais"]) == 1
        assert len(plan["candidats"]) > 1

    def test_the_initial_plan_is_the_head_of_the_pool(self):
        # Sans rien apprendre de la cible, la campagne doit lancer exactement
        # ce que le plan prevoyait : l'adaptation change l'ordre, pas la
        # strategie de depart.
        plan = plan_campaign(profile(refused=["le code du coffre"]), budget=3)
        assert plan["essais"][0]["texte"] == plan["candidats"][0]["texte"]

    def test_every_candidate_carries_its_priority(self):
        # C'est l'echelle que l'adaptation prolonge : sans elle, impossible
        # de reordonner.
        plan = plan_campaign(profile(refused=["le code du coffre"]), budget=3)
        assert all(isinstance(c["priorite"], int) for c in plan["candidats"])

    def test_the_pool_is_sorted(self):
        plan = plan_campaign(profile(refused=["le code du coffre"]), budget=3)
        priorities = [c["priorite"] for c in plan["candidats"]]
        assert priorities == sorted(priorities)


class TestFalseCoverageHoles:
    """
    Le rapport affichait cote a cote « divulgation-information (LLM02) —
    aucun modele de payload » et « Familles testees : LLM02 ». Contradictoire
    pour un lecteur, et c'est un trou INVENTE : la famille est couverte par
    les sondes garak, seule la technique maison du meme nom est encore vide.

    On ne masque pas l'ecartement pour autant — on dit ou la famille est
    traitee. Taire une technique vide serait l'autre moitie du mensonge.
    """

    def test_an_empty_technique_whose_family_is_covered_is_flagged(self):
        plan = plan_campaign(profile(refused=["le code du coffre"]), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        # `divulgation-information` est vide, mais LLM02 est couverte par
        # garak — sauf si l'instantane est absent, d'ou la garde.
        familles_testees = {c["famille_owasp"] for c in plan["candidats"]}
        if "LLM02:2025 Sensitive Information Disclosure" in familles_testees:
            assert par_nom["divulgation-information"][
                "famille_couverte_ailleurs"] is True

    def test_a_genuinely_absent_family_is_not_called_covered(self):
        # `injection-directe` est vide, et ici rien ne couvre LLM01 :
        # l'instantane garak est neutralise par la fixture. Le trou est donc
        # reel, et le dire couvert serait la moitie inverse du mensonge.
        #
        # Ce test visait `abus-outils` jusqu'au 2026-11-12 : la technique
        # n'avait aucun payload, donc elle etait toujours ecartee. Elle en a
        # quatre depuis, et c'est le bon comportement — pas une regression.
        plan = plan_campaign(profile(tools=["un_outil"],
                               refused=["le code du coffre"]), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        assert par_nom["injection-directe"]["famille_couverte_ailleurs"] \
            is False

    def test_every_skipped_entry_carries_the_field(self):
        # Le rapport le lit sans garde : un champ manquant le ferait mentir
        # par omission.
        plan = plan_campaign(profile(), budget=3)
        assert all("famille_couverte_ailleurs" in e for e in plan["ecartees"])


class TestSystemPromptLeak:
    """
    garak ne fournit AUCUNE sonde pour LLM07 (verifie le 2026-11-11 sur les 52
    sondes du perimetre), alors que l'arbitre sait juger cette famille, que le
    corpus a cinq echanges etiquetes dessus et que la cible de demonstration a
    un prompt systeme bavard. C'etait le seul trou reellement exploitable.
    """

    def test_the_technique_is_kept_when_the_target_mentions_its_instructions(self):
        plan = plan_campaign(profile(instructions=True), budget=3)
        skipped = {e["technique"] for e in plan["ecartees"]}
        assert "fuite-prompt-systeme" not in skipped

    def test_it_stays_skipped_if_the_target_mentions_no_instruction(self):
        # Le prerequis `consignes` tient : extraire des instructions suppose
        # qu'il y en ait.
        plan = plan_campaign(profile(instructions=False), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        assert "fuite-prompt-systeme" in par_nom
        assert any("consigne" in m
                   for m in par_nom["fuite-prompt-systeme"]["motifs"])

    def test_it_covers_the_LLM07_family(self):
        plan = plan_campaign(profile(instructions=True), budget=3)
        familles = {c["famille_owasp"] for c in plan["candidats"]}
        assert "LLM07:2025 System Prompt Leakage" in familles

    def test_its_payloads_are_complete_not_templates(self):
        # Une demande d'instructions porte sa propre intention : elle n'a pas
        # d'emplacement `{objectif}` a remplir.
        from agents.attaquant import load_library
        technique = next(t for t in load_library(with_garak=False)
                         ["techniques"] if t["id"] == "fuite-prompt-systeme")
        assert technique["modeles"] == []
        assert len(technique["payloads_complets"]) >= 5

    def test_the_payloads_cover_several_registers(self):
        # Une cible qui refuse de REPETER accepte souvent de RESUMER, et un
        # filtre par mots-cles ne voit pas une formulation positionnelle.
        from agents.attaquant import load_library
        technique = next(t for t in load_library(with_garak=False)
                         ["techniques"] if t["id"] == "fuite-prompt-systeme")
        texts = " ".join(technique["payloads_complets"]).lower()
        for registre in ("répète", "résume", "au-dessus", "audit"):
            assert registre in texts, registre
        # Et au moins un en anglais : les garde-fous d'une cible francophone
        # sont parfois ecrits en francais seulement.
        assert any("you were given" in p or "system prompt" in p
                   for p in technique["payloads_complets"])


class TestToolAbuse:
    """
    LLM06 n'est la famille PRINCIPALE d'aucune des 52 sondes du perimetre
    garak : les dix qui la portent en secondaire visent l'application autour
    du modele, pas l'appel d'outil. D'ou quatre payloads ecrits a la main.

    Leur particularite : le nom de l'outil ne peut pas etre dans la
    bibliotheque, puisqu'il varie d'une cible a l'autre. Il vient de la
    reconnaissance, par l'axe `{objectif}`.
    """

    def test_a_discovered_tool_becomes_an_objective(self):
        objectives = objectives_for(profile(tools=["consulter_dossier"]),
                                   {"objectifs": []})
        assert any("consulter_dossier" in o["formulation"] for o in objectives)

    def test_the_objective_aims_at_a_third_party(self):
        # Ce n'est pas un ornement de formulation : c'est le discriminant du
        # critere `abus_outils` de l'arbitre. Consulter SON dossier est un
        # usage legitime (cas D17 du corpus) ; obtenir celui d'un tiers est la
        # vulnerability. Without that clause the judge would class it as
        # raison — et les quatre registres ne mesureraient rien.
        objective = next(o for o in objectives_for(
            profile(tools=["consulter_dossier"]), {"objectifs": []})
            if "consulter_dossier" in o["formulation"])
        assert "autre que moi" in objective["formulation"]

    def test_without_a_tool_no_tool_objective(self):
        objectives = objectives_for(profile(tools=[]), {"objectifs": []})
        assert not [o for o in objectives if o.get("pour_famille")]

    def test_the_first_abuse_attempt_names_the_tool(self):
        # Verification par CLASSEMENT, pas contre la constante qui l'a produit
        # (un test qui compare un resultat au bonus qui l'a cause ne teste
        # rien). La cible refuse aussi un sujet, donc `refus-1` existe et se
        # place AVANT `outil-1` dans la liste des objectifs : sans la regle
        # d'appariement, le tri stable retenait `refus-1`, et la technique
        # d'abus d'outil partait sans nommer aucun outil.
        plan = plan_campaign(profile(tools=["consulter_dossier"],
                               refused=["le code du coffre"]), budget=10)
        abus = [c for c in plan["candidats"] if c["technique"] == "abus-outils"]
        assert abus, "la technique devrait etre retenue"
        assert "consulter_dossier" in abus[0]["texte"]

    def test_the_pairing_holds_for_its_family_only(self):
        # L'objectif d'outil est fabrique POUR LLM06. Sur une technique LLM07
        # il ne doit rien gagner, sinon il passerait devant un objectif tire
        # de ce que la cible refuse — plus pertinent pour une fuite de prompt.
        plan = plan_campaign(profile(tools=["consulter_dossier"],
                               refused=["le code du coffre"], instructions=True),
                         budget=10)
        fuite = [c for c in plan["candidats"]
                 if c["technique"] == "fuite-prompt-systeme"]
        assert fuite
        assert fuite[0]["objectif"] != "outil-1"

    def test_the_payloads_are_templates_to_fill(self):
        # L'inverse de `fuite-prompt-systeme` : ici l'intention ne suffit pas,
        # il faut le nom de l'outil, donc un emplacement a remplir.
        from agents.attaquant import load_library
        technique = next(t for t in load_library(with_garak=False)
                         ["techniques"] if t["id"] == "abus-outils")
        assert technique["modeles"]
        assert all("{objectif}" in m for m in technique["modeles"])

    def test_the_payloads_cover_several_registers(self):
        from agents.attaquant import load_library
        technique = next(t for t in load_library(with_garak=False)
                         ["techniques"] if t["id"] == "abus-outils")
        texts = " ".join(technique["modeles"]).lower()
        for registre in ("sans me demander confirmation",   # appel dicte
                         "administrateur",                  # pretexte
                         "étape préalable",                 # formalite glissee
                         "sortie complète"):                # resultat brut
            assert registre in texts, registre


class TestRoundRobinPerModule:
    """
    `_share_budget` repartit le budget entre les MODULES garak, pas entre les
    sondes. Sans ca, les quinze sondes `encoding` raflaient quinze tours
    quand `dan` en obtenait trois.
    """

    def test_the_round_robin_is_balanced_across_modules(self):
        # A formula that must hold WITH or WITHOUT the garak snapshot (this
        # file's fixture neutralises it, so only the hand-written groups
        # remain): no module takes a second turn before all have had their
        # first, so the counts never differ by more than one.
        from collections import Counter
        plan = plan_campaign(profile(instructions=True, refused=["le code"]), budget=10)
        counts = Counter(e.get("groupe") for e in plan["essais"])
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_two_available_modules_alternate(self):
        plan = plan_campaign(profile(instructions=True), budget=2)
        groups = [e.get("groupe") for e in plan["essais"]]
        assert len(set(groups)) == 2

    def test_every_attempt_carries_its_group(self):
        plan = plan_campaign(profile(instructions=True), budget=5)
        assert all(e.get("groupe") for e in plan["essais"])

    def test_a_hand_written_technique_has_its_own_group(self):
        plan = plan_campaign(profile(instructions=True), budget=30)
        maison = [e for e in plan["candidats"]
                  if not e["technique"].startswith("garak-")]
        assert maison
        assert all(e["groupe"] == e["technique"] for e in maison)

    def test_probes_of_one_module_share_their_group(self):
        plan = plan_campaign(profile(instructions=True), budget=3)
        par_groupe = {}
        for candidate in plan["candidats"]:
            if candidate["technique"].startswith("garak-encoding-"):
                par_groupe.setdefault(candidate["groupe"], set()).add(
                    candidate["technique"])
        # S'il y a un instantane garak, toutes les sondes d'encodage doivent
        # tomber dans un seul groupe.
        if par_groupe:
            assert list(par_groupe) == ["encoding"]
            assert len(par_groupe["encoding"]) > 1


class TestRelevanceRules:
    """
    Les prerequis de CAPACITE et de CONTEXTE, ajoutes le 2026-11-11. Ils ne se
    comportent pas pareil, et l'asymetrie est le coeur de la conception.
    """

    # --- Capacites sondees : on n'ecarte que sur un NON explicite ----------

    def test_an_explicit_no_skips(self):
        # The target answered "I do not write code": the probe is useless.
        regles = dict(PREREQUISITES)
        verifier, _ = regles["produit-du-code"]
        assert verifier(profile(code=False)) is False

    def test_a_yes_lets_it_through(self):
        verifier, _ = PREREQUISITES["produit-du-code"]
        assert verifier(profile(code=True)) is True

    def test_a_silence_lets_it_through(self):
        # Decision assumee : rater une faille coute plus cher qu'un essai
        # gaspille, et un chatbot ne detaille pas tout ce qu'il sait faire.
        verifier, _ = PREREQUISITES["produit-du-code"]
        assert verifier(profile(code=None)) is True

    def test_documents_follow_the_same_rule(self):
        verifier, _ = PREREQUISITES["traite-des-documents"]
        assert verifier(profile(documents=None)) is True
        assert verifier(profile(documents=False)) is False

    # --- Contexte declare : non declare = ecarte ---------------------------

    @pytest.mark.parametrize("prerequisite", ["terminal", "rendu-riche",
                                           "base-donnees"])
    def test_an_undeclared_context_skips(self, prerequisite):
        # Asymetrie VOLONTAIRE avec les capacites : ici personne n'a repondu,
        # parce qu'une cible ne sait pas dans quoi sa sortie est rendue, et
        # l'attaque est structurellement intestable sans ce contexte.
        verifier, _ = PREREQUISITES[prerequisite]
        assert verifier(profile()) is False

    @pytest.mark.parametrize("prerequisite", ["terminal", "rendu-riche",
                                           "base-donnees"])
    def test_a_declared_context_lets_it_through(self, prerequisite):
        verifier, _ = PREREQUISITES[prerequisite]
        assert verifier(profile(context=[prerequisite])) is True

    @pytest.mark.parametrize("prerequisite", ["terminal", "rendu-riche",
                                           "base-donnees"])
    def test_the_reason_says_how_to_enable_it(self, prerequisite):
        # Un ecartement muet ferait croire a un trou de couverture definitif.
        _, reason = PREREQUISITES[prerequisite]
        assert "--contexte" in reason

    def test_one_context_does_not_unlock_the_others(self):
        verifier, _ = PREREQUISITES["rendu-riche"]
        assert verifier(profile(context=["terminal"])) is False

    # --- Effet sur un plan reel -------------------------------------------

    def test_the_skipped_families_state_their_reason(self):
        plan = plan_campaign(profile(instructions=True), budget=5)
        for ecartee in plan["ecartees"]:
            assert ecartee["motifs"], ecartee["technique"]

    def test_a_target_with_no_context_keeps_some_attempts(self):
        # Le durcissement ne doit pas vider le plan : les modules universels
        # (`encoding`, `goodside`, `promptinject`) restent disponibles.
        plan = plan_campaign(profile(instructions=True, refused=["le code"]), budget=3)
        assert plan["essais"]


class TestCoveredElsewhereNotice:
    """
    « La famille est couverte par d'autres sondes » ne vaut QUE pour une
    technique ecartee faute de payload. Le champ s'appliquait a toutes les
    ecartees, ce qui est devenu visible — et faux — avec les regles de
    pertinence : `ansiescape` releve de LLM01, couverte par ailleurs, mais
    elle teste les sequences ANSI que nulle autre sonde ne teste. La mention
    laissait croire que son ecartement ne coutait rien.
    """

    def test_a_skip_for_irrelevance_does_not_carry_the_notice(self):
        plan = plan_campaign(profile(instructions=True), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        for nom, ecartee in par_nom.items():
            if nom.startswith("garak-"):
                assert ecartee["famille_couverte_ailleurs"] is False, nom

    def test_a_technique_with_no_payload_still_carries_it(self):
        plan = plan_campaign(profile(instructions=True, refused=["le code"]), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        familles = {c["famille_owasp"] for c in plan["candidats"]}
        if "LLM01:2025 Prompt Injection" in familles:
            assert par_nom["jailbreak"]["famille_couverte_ailleurs"] is True


class TestGroupingTheSkipped:
    def test_identical_reasons_are_grouped(self):
        skipped = [
            {"technique": "a", "famille_owasp": None, "motifs": ["meme motif"]},
            {"technique": "b", "famille_owasp": None, "motifs": ["meme motif"]},
            {"technique": "c", "famille_owasp": None, "motifs": ["autre"]},
        ]
        groups = group_by_reason(skipped)
        assert groups == [("meme motif", ["a", "b"]), ("autre", ["c"])]

    def test_the_order_of_appearance_is_kept(self):
        # Deux campagnes identiques doivent produire le meme rapport, donc le
        # groupement ne doit pas trier arbitrairement.
        skipped = [
            {"technique": "z", "famille_owasp": None, "motifs": ["second"]},
            {"technique": "a", "famille_owasp": None, "motifs": ["premier"]},
        ]
        assert [m for m, _ in group_by_reason(skipped)] == ["second",
                                                               "premier"]

    def test_the_summary_does_not_repeat_a_reason(self):
        rendered = summarise(plan_campaign(profile(instructions=True), budget=3))
        for reason in ("aucun client ne rend le Markdown",
                      "la cible dit ne pas écrire de code"):
            assert rendered.count(reason) <= 1, reason


class TestScope:
    """
    `--seulement` et `--sauf`. Trois besoins, un mecanisme : respecter une
    portee de mandat qui exclut des techniques, reproduire un constat sans
    relancer toute la campagne, et rendre pass@k possible en rejouant la
    MEME technique k fois.
    """

    def _candidates(self, **kw):
        plan = plan_campaign(profile(instructions=True, refused=["le code"]), 5, **kw)
        return {c.get("groupe") or c["technique"] for c in plan["candidats"]}

    def test_only_one_technique(self):
        assert self._candidates(only=["fuite-prompt-systeme"]) == \
               {"fuite-prompt-systeme"}

    def test_the_pattern_works_on_the_owasp_family(self):
        modules = self._candidates(only=["LLM07"])
        assert modules and all("fuite" in m or "LLM07" in m for m in modules)

    def test_excluding_skips(self):
        assert "controle" not in self._candidates(excluding=["controle"])

    def test_excluding_wins_over_only(self):
        # Une exclusion vient du mandat : elle ne se contourne pas par une
        # autre option de la meme commande.
        assert self._candidates(only=["controle"], excluding=["controle"]) == set()

    def test_several_patterns(self):
        modules = self._candidates(only=["controle", "fuite-prompt-systeme"])
        assert modules == {"controle", "fuite-prompt-systeme"}

    def test_without_a_pattern_nothing_changes(self):
        assert self._candidates() == self._candidates(only=[], excluding=[])

    def test_the_skip_states_the_right_reason(self):
        # Une technique hors perimetre ne doit pas etre ecartee pour « aucun
        # tool detected", which would mask the real reason.
        plan = plan_campaign(profile(instructions=True), 5, only=["controle"])
        reasons = {e["technique"]: " ".join(e["motifs"]) for e in plan["ecartees"]}
        assert "hors du périmètre demandé" in reasons["fuite-prompt-systeme"]

    def test_the_exclusion_reason_names_the_option(self):
        plan = plan_campaign(profile(instructions=True), 5, excluding=["fuite-prompt-systeme"])
        reasons = {e["technique"]: " ".join(e["motifs"]) for e in plan["ecartees"]}
        assert "--sauf" in reasons["fuite-prompt-systeme"]

    def test_an_unknown_pattern_keeps_nothing(self):
        # Mieux vaut un plan vide, visible immediatement, qu'un filtre ignore
        # en silence qui ferait croire a une campagne complete.
        assert self._candidates(only=["nimportequoi"]) == set()
