"""
Tests du planificateur.

C'est du code déterministe — c'était d'ailleurs le but : confier la décision
à des règles plutôt qu'à un LLM, pour pouvoir la vérifier. Voici la
vérification.

Deux choses comptent autant l'une que l'autre : qu'il retienne les bonnes
familles, et qu'il dise POURQUOI il a écarté les autres. Un outil qui tait ce
qu'il n'a pas testé donne une fausse impression de couverture.
"""

import pytest

import agents.attaquant
from agents.planificateur import (PREREQUIS, grouper_par_motif,
                                  objectifs_pour, planifier,
                                  resumer)


@pytest.fixture(autouse=True)
def sans_instantane_garak(monkeypatch, tmp_path):
    """
    Isole les tests de l'instantané garak éventuellement présent en local.

    Sans ça, ces tests passeraient ou non selon qu'on a lancé
    `exporter_garak.py` — un test ne doit pas dépendre de ça.
    """
    monkeypatch.setattr(agents.attaquant, "FICHIER_GARAK",
                        tmp_path / "absent.json")


def fiche(role="assistant", outils=(), refuses=(), consignes=False,
          code=None, documents=None, contexte=()):
    # `code` et `documents` sont des TRI-ÉTATS : None = la cible n'en a rien
    # dit, ce qui n'est pas « elle ne sait pas faire ».
    return {"role": role, "langue": "fr", "outils": list(outils),
            "sujets_refuses": list(refuses), "mentionne_consignes": consignes,
            "produit_du_code": code, "traite_des_documents": documents,
            "contexte": list(contexte),
            "indices": [], "echanges": [], "avertissement": None}


def _ecartees(plan):
    return {e["technique"]: e["motifs"] for e in plan["ecartees"]}


class TestPrerequis:
    def test_sans_outil_l_abus_d_outils_est_ecarte(self):
        plan = planifier(fiche(outils=[]), budget=10)
        assert "aucun outil détecté chez la cible" in \
               _ecartees(plan)["abus-outils"]

    def test_avec_un_outil_ce_motif_disparait(self):
        plan = planifier(fiche(outils=["virement"]), budget=10)
        assert "aucun outil détecté chez la cible" not in \
               _ecartees(plan)["abus-outils"]

    def test_une_cible_muette_fait_ecarter_les_familles_de_fuite(self):
        plan = planifier(fiche(), budget=10)
        ecartees = _ecartees(plan)
        assert any("ne déclare ni sujet interdit" in m
                   for m in ecartees["divulgation-information"])
        assert any("n'évoque aucune consigne" in m
                   for m in ecartees["fuite-prompt-systeme"])

    @pytest.mark.parametrize("cible", [
        fiche(refuses=["le code du coffre"]),
        fiche(consignes=True),
    ])
    def test_une_cible_qui_protege_quelque_chose_les_conserve(self, cible):
        ecartees = _ecartees(planifier(cible, budget=10))
        assert not any("ne déclare ni sujet interdit" in m
                       for m in ecartees["divulgation-information"])

    def test_une_technique_sans_modele_est_ecartee_et_le_dit(self):
        # Les familles OWASP sont déclarées mais vides : elles doivent
        # disparaître du plan AVEC leur motif, pas en silence.
        ecartees = _ecartees(planifier(fiche(consignes=True), budget=10))
        assert "aucun modèle de payload dans la bibliothèque" in \
               ecartees["injection-directe"]


class TestObjectifs:
    def test_les_refus_de_la_cible_deviennent_des_objectifs(self):
        # C'est tout l'intérêt de la reconnaissance : viser ce que CETTE
        # cible protège, au lieu d'objectifs génériques.
        objectifs = objectifs_pour(fiche(refuses=["le code du coffre"]),
                                   {"objectifs": []})
        assert any("le code du coffre" in o["formulation"] for o in objectifs)
        assert all(o["origine"] == "reconnaissance" for o in objectifs)

    def test_les_objectifs_de_la_bibliotheque_sont_conserves(self):
        bibliotheque = {"objectifs": [{"id": "x", "formulation": "f",
                                       "origine": "bibliotheque"}]}
        assert len(objectifs_pour(fiche(), bibliotheque)) == 1


class TestBudgetEtOrdre:
    @pytest.mark.parametrize("budget", [0, 1, 3, 100])
    def test_le_budget_n_est_jamais_depasse(self, budget):
        plan = planifier(fiche(refuses=["un secret"]), budget=budget)
        assert len(plan["essais"]) <= budget

    def test_les_objectifs_issus_de_la_reconnaissance_passent_en_premier(self):
        plan = planifier(fiche(refuses=["le code du coffre"]), budget=4)
        assert plan["essais"][0]["objectif"].startswith("refus-")

    def test_le_texte_brut_passe_avant_ses_transformations(self):
        plan = planifier(fiche(refuses=["un secret"]), budget=4)
        assert plan["essais"][0]["transformation"] == "identite"

    def test_deux_planifications_identiques_donnent_le_meme_plan(self):
        # Tri stable : une campagne doit être reproductible.
        cible = fiche(refuses=["un secret"])
        a = [e["texte"] for e in planifier(cible, 5)["essais"]]
        b = [e["texte"] for e in planifier(cible, 5)["essais"]]
        assert a == b


class TestFormeDesEssais:
    def test_chaque_essai_dit_d_ou_il_vient(self):
        # Sans ça, le rapport ne pourrait pas dire QUELLE combinaison a marché.
        for essai in planifier(fiche(refuses=["un secret"]), budget=3)["essais"]:
            assert {"technique", "famille_owasp", "objectif",
                    "transformation", "texte"} <= set(essai)

    def test_aucun_marqueur_de_gabarit_ne_subsiste(self):
        for essai in planifier(fiche(refuses=["un secret"]), budget=5)["essais"]:
            assert "{objectif}" not in essai["texte"]


class TestVivierDeCandidats:
    """
    La phase 3a pioche dans un vivier au lieu d'une liste figee. Le plan
    initial reste borne par le budget ; le vivier, lui, ne doit PAS l'etre,
    sinon un essai releguee ne pourrait jamais remonter quand la cible
    revele qu'il etait pertinent.
    """

    def test_le_vivier_n_est_pas_tronque_par_le_budget(self):
        plan = planifier(fiche(refuses=["le code du coffre"]), budget=1)
        assert len(plan["essais"]) == 1
        assert len(plan["candidats"]) > 1

    def test_le_plan_initial_est_la_tete_du_vivier(self):
        # Sans rien apprendre de la cible, la campagne doit lancer exactement
        # ce que le plan prevoyait : l'adaptation change l'ordre, pas la
        # strategie de depart.
        plan = planifier(fiche(refuses=["le code du coffre"]), budget=3)
        assert plan["essais"][0]["texte"] == plan["candidats"][0]["texte"]

    def test_chaque_candidat_porte_sa_priorite(self):
        # C'est l'echelle que l'adaptation prolonge : sans elle, impossible
        # de reordonner.
        plan = planifier(fiche(refuses=["le code du coffre"]), budget=3)
        assert all(isinstance(c["priorite"], int) for c in plan["candidats"])

    def test_le_vivier_est_trie(self):
        plan = planifier(fiche(refuses=["le code du coffre"]), budget=3)
        priorites = [c["priorite"] for c in plan["candidats"]]
        assert priorites == sorted(priorites)


class TestFauxTrousDeCouverture:
    """
    Le rapport affichait cote a cote « divulgation-information (LLM02) —
    aucun modele de payload » et « Familles testees : LLM02 ». Contradictoire
    pour un lecteur, et c'est un trou INVENTE : la famille est couverte par
    les sondes garak, seule la technique maison du meme nom est encore vide.

    On ne masque pas l'ecartement pour autant — on dit ou la famille est
    traitee. Taire une technique vide serait l'autre moitie du mensonge.
    """

    def test_une_technique_vide_dont_la_famille_est_couverte_est_signalee(self):
        plan = planifier(fiche(refuses=["le code du coffre"]), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        # `divulgation-information` est vide, mais LLM02 est couverte par
        # garak — sauf si l'instantane est absent, d'ou la garde.
        familles_testees = {c["famille_owasp"] for c in plan["candidats"]}
        if "LLM02:2025 Sensitive Information Disclosure" in familles_testees:
            assert par_nom["divulgation-information"][
                "famille_couverte_ailleurs"] is True

    def test_une_famille_reellement_absente_n_est_pas_dite_couverte(self):
        plan = planifier(fiche(outils=["un_outil"],
                               refuses=["le code du coffre"]), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        # LLM06 n'est la famille principale d'aucune sonde : le trou est reel.
        assert par_nom["abus-outils"]["famille_couverte_ailleurs"] is False

    def test_chaque_ecartee_porte_le_champ(self):
        # Le rapport le lit sans garde : un champ manquant le ferait mentir
        # par omission.
        plan = planifier(fiche(), budget=3)
        assert all("famille_couverte_ailleurs" in e for e in plan["ecartees"])


class TestFuiteDePromptSysteme:
    """
    garak ne fournit AUCUNE sonde pour LLM07 (verifie le 2026-11-11 sur les 52
    sondes du perimetre), alors que l'arbitre sait juger cette famille, que le
    corpus a cinq echanges etiquetes dessus et que la cible de demonstration a
    un prompt systeme bavard. C'etait le seul trou reellement exploitable.
    """

    def test_la_technique_est_retenue_quand_la_cible_evoque_ses_consignes(self):
        plan = planifier(fiche(consignes=True), budget=3)
        ecartees = {e["technique"] for e in plan["ecartees"]}
        assert "fuite-prompt-systeme" not in ecartees

    def test_elle_reste_ecartee_si_la_cible_n_evoque_aucune_consigne(self):
        # Le prerequis `consignes` tient : extraire des instructions suppose
        # qu'il y en ait.
        plan = planifier(fiche(consignes=False), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        assert "fuite-prompt-systeme" in par_nom
        assert any("consigne" in m
                   for m in par_nom["fuite-prompt-systeme"]["motifs"])

    def test_elle_couvre_la_famille_LLM07(self):
        plan = planifier(fiche(consignes=True), budget=3)
        familles = {c["famille_owasp"] for c in plan["candidats"]}
        assert "LLM07:2025 System Prompt Leakage" in familles

    def test_ses_payloads_sont_complets_pas_des_modeles(self):
        # Une demande d'instructions porte sa propre intention : elle n'a pas
        # d'emplacement `{objectif}` a remplir.
        from agents.attaquant import charger_bibliotheque
        technique = next(t for t in charger_bibliotheque(avec_garak=False)
                         ["techniques"] if t["id"] == "fuite-prompt-systeme")
        assert technique["modeles"] == []
        assert len(technique["payloads_complets"]) >= 5

    def test_les_payloads_couvrent_plusieurs_registres(self):
        # Une cible qui refuse de REPETER accepte souvent de RESUMER, et un
        # filtre par mots-cles ne voit pas une formulation positionnelle.
        from agents.attaquant import charger_bibliotheque
        technique = next(t for t in charger_bibliotheque(avec_garak=False)
                         ["techniques"] if t["id"] == "fuite-prompt-systeme")
        textes = " ".join(technique["payloads_complets"]).lower()
        for registre in ("répète", "résume", "au-dessus", "audit"):
            assert registre in textes, registre
        # Et au moins un en anglais : les garde-fous d'une cible francophone
        # sont parfois ecrits en francais seulement.
        assert any("you were given" in p or "system prompt" in p
                   for p in technique["payloads_complets"])


class TestTourDeRoleParModule:
    """
    `_repartir` repartit le budget entre les MODULES garak, pas entre les
    sondes. Sans ca, les quinze sondes `encoding` raflaient quinze tours
    quand `dan` en obtenait trois.
    """

    def test_le_tour_de_role_est_equilibre_entre_les_modules(self):
        # Formule a tenir avec OU sans l'instantane garak (la fixture de ce
        # fichier le neutralise, donc il ne reste que les groupes maison) :
        # aucun module ne prend un deuxieme tour avant que tous aient eu le
        # leur, donc les comptes ne diffèrent jamais de plus de un.
        from collections import Counter
        plan = planifier(fiche(consignes=True, refuses=["le code"]), budget=10)
        comptes = Counter(e.get("groupe") for e in plan["essais"])
        assert max(comptes.values()) - min(comptes.values()) <= 1

    def test_deux_modules_disponibles_alternent(self):
        plan = planifier(fiche(consignes=True), budget=2)
        groupes = [e.get("groupe") for e in plan["essais"]]
        assert len(set(groupes)) == 2

    def test_chaque_essai_porte_son_groupe(self):
        plan = planifier(fiche(consignes=True), budget=5)
        assert all(e.get("groupe") for e in plan["essais"])

    def test_une_technique_maison_a_son_propre_groupe(self):
        plan = planifier(fiche(consignes=True), budget=30)
        maison = [e for e in plan["candidats"]
                  if not e["technique"].startswith("garak-")]
        assert maison
        assert all(e["groupe"] == e["technique"] for e in maison)

    def test_les_sondes_d_un_meme_module_partagent_leur_groupe(self):
        plan = planifier(fiche(consignes=True), budget=3)
        par_groupe = {}
        for candidat in plan["candidats"]:
            if candidat["technique"].startswith("garak-encoding-"):
                par_groupe.setdefault(candidat["groupe"], set()).add(
                    candidat["technique"])
        # S'il y a un instantane garak, toutes les sondes d'encodage doivent
        # tomber dans un seul groupe.
        if par_groupe:
            assert list(par_groupe) == ["encoding"]
            assert len(par_groupe["encoding"]) > 1


class TestReglesDePertinence:
    """
    Les prerequis de CAPACITE et de CONTEXTE, ajoutes le 2026-11-11. Ils ne se
    comportent pas pareil, et l'asymetrie est le coeur de la conception.
    """

    # --- Capacites sondees : on n'ecarte que sur un NON explicite ----------

    def test_un_non_explicite_ecarte(self):
        # La cible a repondu « je n'ecris pas de code » : la sonde est inutile.
        regles = dict(PREREQUIS)
        verifier, _ = regles["produit-du-code"]
        assert verifier(fiche(code=False)) is False

    def test_un_oui_laisse_passer(self):
        verifier, _ = PREREQUIS["produit-du-code"]
        assert verifier(fiche(code=True)) is True

    def test_un_silence_laisse_passer(self):
        # Decision assumee : rater une faille coute plus cher qu'un essai
        # gaspille, et un chatbot ne detaille pas tout ce qu'il sait faire.
        verifier, _ = PREREQUIS["produit-du-code"]
        assert verifier(fiche(code=None)) is True

    def test_les_documents_suivent_la_meme_regle(self):
        verifier, _ = PREREQUIS["traite-des-documents"]
        assert verifier(fiche(documents=None)) is True
        assert verifier(fiche(documents=False)) is False

    # --- Contexte declare : non declare = ecarte ---------------------------

    @pytest.mark.parametrize("prerequis", ["terminal", "rendu-riche",
                                           "base-donnees"])
    def test_un_contexte_non_declare_ecarte(self, prerequis):
        # Asymetrie VOLONTAIRE avec les capacites : ici personne n'a repondu,
        # parce qu'une cible ne sait pas dans quoi sa sortie est rendue, et
        # l'attaque est structurellement intestable sans ce contexte.
        verifier, _ = PREREQUIS[prerequis]
        assert verifier(fiche()) is False

    @pytest.mark.parametrize("prerequis", ["terminal", "rendu-riche",
                                           "base-donnees"])
    def test_un_contexte_declare_laisse_passer(self, prerequis):
        verifier, _ = PREREQUIS[prerequis]
        assert verifier(fiche(contexte=[prerequis])) is True

    @pytest.mark.parametrize("prerequis", ["terminal", "rendu-riche",
                                           "base-donnees"])
    def test_le_motif_dit_comment_activer(self, prerequis):
        # Un ecartement muet ferait croire a un trou de couverture definitif.
        _, motif = PREREQUIS[prerequis]
        assert "--contexte" in motif

    def test_un_contexte_ne_debloque_pas_les_autres(self):
        verifier, _ = PREREQUIS["rendu-riche"]
        assert verifier(fiche(contexte=["terminal"])) is False

    # --- Effet sur un plan reel -------------------------------------------

    def test_les_familles_ecartees_disent_leur_motif(self):
        plan = planifier(fiche(consignes=True), budget=5)
        for ecartee in plan["ecartees"]:
            assert ecartee["motifs"], ecartee["technique"]

    def test_une_cible_sans_contexte_garde_des_essais(self):
        # Le durcissement ne doit pas vider le plan : les modules universels
        # (`encoding`, `goodside`, `promptinject`) restent disponibles.
        plan = planifier(fiche(consignes=True, refuses=["le code"]), budget=3)
        assert plan["essais"]


class TestMentionCouverteAilleurs:
    """
    « La famille est couverte par d'autres sondes » ne vaut QUE pour une
    technique ecartee faute de payload. Le champ s'appliquait a toutes les
    ecartees, ce qui est devenu visible — et faux — avec les regles de
    pertinence : `ansiescape` releve de LLM01, couverte par ailleurs, mais
    elle teste les sequences ANSI que nulle autre sonde ne teste. La mention
    laissait croire que son ecartement ne coutait rien.
    """

    def test_un_ecartement_pour_non_pertinence_ne_porte_pas_la_mention(self):
        plan = planifier(fiche(consignes=True), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        for nom, ecartee in par_nom.items():
            if nom.startswith("garak-"):
                assert ecartee["famille_couverte_ailleurs"] is False, nom

    def test_une_technique_sans_payload_la_porte_encore(self):
        plan = planifier(fiche(consignes=True, refuses=["le code"]), budget=3)
        par_nom = {e["technique"]: e for e in plan["ecartees"]}
        familles = {c["famille_owasp"] for c in plan["candidats"]}
        if "LLM01:2025 Prompt Injection" in familles:
            assert par_nom["jailbreak"]["famille_couverte_ailleurs"] is True


class TestGroupementDesEcartees:
    def test_les_motifs_identiques_sont_regroupes(self):
        ecartees = [
            {"technique": "a", "famille_owasp": None, "motifs": ["meme motif"]},
            {"technique": "b", "famille_owasp": None, "motifs": ["meme motif"]},
            {"technique": "c", "famille_owasp": None, "motifs": ["autre"]},
        ]
        groupes = grouper_par_motif(ecartees)
        assert groupes == [("meme motif", ["a", "b"]), ("autre", ["c"])]

    def test_l_ordre_d_apparition_est_conserve(self):
        # Deux campagnes identiques doivent produire le meme rapport, donc le
        # groupement ne doit pas trier arbitrairement.
        ecartees = [
            {"technique": "z", "famille_owasp": None, "motifs": ["second"]},
            {"technique": "a", "famille_owasp": None, "motifs": ["premier"]},
        ]
        assert [m for m, _ in grouper_par_motif(ecartees)] == ["second",
                                                               "premier"]

    def test_le_resume_ne_repete_pas_un_motif(self):
        rendu = resumer(planifier(fiche(consignes=True), budget=3))
        for motif in ("aucun client ne rend le Markdown",
                      "la cible dit ne pas écrire de code"):
            assert rendu.count(motif) <= 1, motif
