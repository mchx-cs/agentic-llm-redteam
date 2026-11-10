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
from agents.planificateur import objectifs_pour, planifier


@pytest.fixture(autouse=True)
def sans_instantane_garak(monkeypatch, tmp_path):
    """
    Isole les tests de l'instantané garak éventuellement présent en local.

    Sans ça, ces tests passeraient ou non selon qu'on a lancé
    `exporter_garak.py` — un test ne doit pas dépendre de ça.
    """
    monkeypatch.setattr(agents.attaquant, "FICHIER_GARAK",
                        tmp_path / "absent.json")


def fiche(role="assistant", outils=(), refuses=(), consignes=False):
    return {"role": role, "langue": "fr", "outils": list(outils),
            "sujets_refuses": list(refuses), "mentionne_consignes": consignes,
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
