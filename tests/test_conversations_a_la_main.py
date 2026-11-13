"""
Tests des conversations écrites à la main (phase 3b).

Aucun appel LLM. Ce qui se vérifie ici n'est pas un comportement de modèle
mais des propriétés du CORPUS — et ce sont elles qui font qu'une mesure veut
dire quelque chose.
"""

import pytest

from evaluation.conversations_a_la_main import CAS, SECRET, entrees


@pytest.fixture(autouse=True)
def aucun_appel_de_modele(monkeypatch):
    def refuser(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.reconnaissance", "agents.arbitre"):
        monkeypatch.setattr(f"{module}.demander_au_llm", refuser,
                            raising=False)


class TestVeriteTerrain:
    """
    Les étiquettes sont la vérité terrain, et c'est l'AUTEUR qui les valide.
    Ce fichier rédige des SCÉNARIOS, pas des verdicts — un test le garantit,
    parce que c'est la règle la plus facile à enfreindre par commodité.
    """

    def test_un_cas_d_un_seul_tour_sort_au_format_mono_tour(self):
        # Sinon `evaluer_arbitre` l'écarterait, alors que le juge sait très
        # bien le lire : un échange d'un tour déguisé en conversation serait
        # perdu pour une mesure qu'il peut nourrir.
        for entree in entrees():
            if entree["format"] == "mono-tour":
                assert "payload" in entree and "reponse" in entree
                assert "tours" not in entree
            else:
                assert "tours" in entree and len(entree["tours"]) > 2

    def test_aucun_verdict_n_est_pre_rempli(self):
        for entree in entrees():
            assert entree["attendu"] is None, entree["id"]
            assert entree["categorie"] is None, entree["id"]
            assert entree["jeu"] is None, entree["id"]

    def test_chaque_cas_dit_POURQUOI_il_existe(self):
        # Sans l'intention, l'auteur reçoit deux conversations presque
        # identiques sans savoir pourquoi on lui soumet les deux.
        for entree in entrees():
            assert len(entree["piege"]) > 60, entree["id"]


class TestLesPairesSontDesPaires:
    """
    La leçon de D13/D14 : un cas négatif seul apprend au juge une règle trop
    large. Il lui faut son jumeau positif, au texte presque identique.
    """

    def _par_groupe(self):
        groupes = {}
        for identifiant, groupe, _, tours in CAS:
            groupes.setdefault(groupe, []).append((identifiant, tours))
        return groupes

    def test_les_paires_partagent_leur_groupe(self):
        # Donc leur jeu : on ne peut pas régler l'arbitre sur l'un et le
        # mesurer sur son jumeau.
        groupes = self._par_groupe()
        assert len(groupes["A-secret-attaquant"]) == 2
        assert len(groupes["A-confirmation"]) == 2

    def test_les_jumeaux_ne_diffèrent_que_par_la_REPONSE(self):
        # Le discriminant doit être ce que la CIBLE dit, pas ce que
        # l'attaquant demande : sinon le cas mesure autre chose.
        for groupe in ("A-secret-attaquant", "A-confirmation"):
            (_, premiers), (_, seconds) = self._par_groupe()[groupe]
            demandes_1 = [t["contenu"] for t in premiers
                          if t["role"] == "utilisateur"]
            demandes_2 = [t["contenu"] for t in seconds
                          if t["role"] == "utilisateur"]
            assert demandes_1 == demandes_2, groupe
            reponses_1 = [t["contenu"] for t in premiers
                          if t["role"] == "cible"]
            reponses_2 = [t["contenu"] for t in seconds
                          if t["role"] == "cible"]
            assert reponses_1 != reponses_2, groupe


class TestLesPiegesInatteignablesSontCouverts:
    def test_le_secret_apparait_dans_un_tour_de_l_ATTAQUANT(self):
        # Le faux positif propre au multi-tours. Aucune récolte ne peut le
        # produire : nos payloads cherchent le secret, ils ne le contiennent
        # pas.
        attaquant = [t for _, _, _, tours in CAS for t in tours
                     if t["role"] == "utilisateur" and SECRET in t["contenu"]]
        assert attaquant, "aucun cas ne met le secret dans la bouche de l'attaquant"

    def test_un_cas_a_la_fuite_a_un_tour_ANTERIEUR(self):
        # 7 fuites sur 11 avaient cette forme sur la récolte réelle.
        trouve = False
        for _, _, _, tours in CAS:
            reponses = [t["contenu"] for t in tours if t["role"] == "cible"]
            if len(reponses) >= 2 and SECRET in reponses[0] \
                    and SECRET not in reponses[-1]:
                trouve = True
        assert trouve

    def test_des_conversations_depassent_deux_tours(self):
        # `sequencer()` n'en produit que deux : au-delà, c'est à la main.
        assert any(len(tours) // 2 > 2 for _, _, _, tours in CAS)

    def test_il_y_a_des_controles_entierement_anodins(self):
        # Sans eux, les faux positifs seraient nuls par construction.
        anodins = [tours for _, _, _, tours in CAS
                   if not any(SECRET in t["contenu"] for t in tours)
                   and "instructions" not in tours[0]["contenu"].lower()]
        assert anodins

    def test_les_tours_alternent_toujours(self):
        # Un corpus mal formé ferait juger un dialogue incohérent.
        for identifiant, _, _, tours in CAS:
            roles = [t["role"] for t in tours]
            assert roles == ["utilisateur", "cible"] * (len(roles) // 2), \
                identifiant


class TestVersement:
    def test_verser_n_ecrase_pas_la_recolte(self, monkeypatch, tmp_path):
        import evaluation.conversations_a_la_main as maison
        import json

        recolte = tmp_path / "recolte.json"
        recolte.write_text(json.dumps({"conversations": [
            {"id": "C-demo-01-1", "attendu": None}]}), encoding="utf-8")
        monkeypatch.setattr(maison, "FICHIER_RECOLTE", recolte)

        ajoutees, total = maison.verser()
        assert len(ajoutees) == len(CAS)
        assert total == len(CAS) + 1

    def test_verser_deux_fois_ne_duplique_rien(self, monkeypatch, tmp_path):
        import evaluation.conversations_a_la_main as maison

        monkeypatch.setattr(maison, "FICHIER_RECOLTE",
                            tmp_path / "recolte.json")
        maison.verser()
        ajoutees, total = maison.verser()
        assert ajoutees == []
        assert total == len(CAS)
