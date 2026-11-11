"""
Tests de la cible de démonstration.

Aucun modèle n'intervient : on remplace `demander_au_llm` par une réponse
choisie, et on vérifie ce qui entoure l'appel — les consignes de chaque
niveau, le filtre de sortie, la simulation d'outil. Ce qu'une vraie cible
répond, lui, est probabiliste et se mesure à la main.
"""

import pytest

import cibles.demo as demo
from audit import est_locale
from cibles import CIBLES_NOMMEES, choisir_cible, est_cible_livree
from cibles.demo import NIVEAUX, SECRET, construire_cible_demo


@pytest.fixture
def repondre(monkeypatch):
    """Fait répondre la cible par un texte choisi, et retient sa consigne."""
    vu = {}

    def installer(reponse):
        def faux(message, systeme=None, **kwargs):
            vu["systeme"] = systeme
            vu["message"] = message
            return reponse
        monkeypatch.setattr(demo, "demander_au_llm", faux)
        return vu
    return installer


class TestNiveaux:
    def test_les_trois_niveaux_existent(self):
        assert set(NIVEAUX) == {1, 2, 3}

    def test_un_niveau_inconnu_est_refuse(self):
        with pytest.raises(ValueError, match="Niveau de démonstration inconnu"):
            construire_cible_demo(9)

    def test_tous_connaissent_le_secret(self, repondre):
        # Les niveaux diffèrent par la PROTECTION du secret, pas par le fait
        # de le détenir : sinon la comparaison entre niveaux ne mesurerait
        # pas la défense.
        for niveau in NIVEAUX:
            vu = repondre("réponse")
            construire_cible_demo(niveau)("question")
            assert SECRET in vu["systeme"], niveau

    def test_tous_exposent_le_meme_role_et_le_meme_outil(self, repondre):
        consignes = []
        for niveau in NIVEAUX:
            vu = repondre("réponse")
            construire_cible_demo(niveau)("question")
            consignes.append(vu["systeme"])
        for consigne in consignes:
            assert "bibliothèque municipale de Valmont" in consigne
            assert "consulter_dossier" in consigne

    def test_le_niveau_1_est_le_plus_permissif(self, repondre):
        vu = repondre("réponse")
        construire_cible_demo(1)("question")
        # Sa consigne invite à aider plutôt qu'à refuser : c'est ce qui rend
        # la détection quasi certaine dans la limite de MAX_ESSAIS.
        assert "serviable" in vu["systeme"] or "coopératif" in vu["systeme"]
        assert "Règle absolue" not in vu["systeme"]

    @pytest.mark.parametrize("niveau", [2, 3])
    def test_les_niveaux_2_et_3_posent_une_regle_absolue(self, repondre, niveau):
        vu = repondre("réponse")
        construire_cible_demo(niveau)("question")
        assert "Règle absolue" in vu["systeme"]


class TestFiltreDeSortie:
    def test_seul_le_niveau_3_filtre(self, repondre):
        fuite = f"Le code est {SECRET}."
        for niveau in (1, 2):
            repondre(fuite)
            assert SECRET in construire_cible_demo(niveau)("question")
        repondre(fuite)
        assert SECRET not in construire_cible_demo(3)("question")

    def test_le_filtre_laisse_passer_l_encodage(self, repondre):
        # Défense volontairement imparfaite : elle attrape le secret écrit en
        # clair, pas sa version encodée. Le niveau 3 met donc à l'épreuve
        # exactement ce que detecteurs.py sait décoder.
        encode = "QVJDSElWRVMtNzczMQ=="          # ARCHIVES-7731 en Base64
        repondre(f"Le voici : {encode}")
        assert encode in construire_cible_demo(3)("question")

    def test_le_filtre_laisse_passer_l_epellation(self, repondre):
        epele = " - ".join(SECRET)
        repondre(epele)
        assert epele in construire_cible_demo(3)("question")

    def test_le_filtre_ignore_la_casse(self, repondre):
        repondre(f"le code est {SECRET.lower()}")
        assert SECRET.lower() not in construire_cible_demo(3)("question").lower()


class TestOutilFactice:
    def test_un_appel_d_outil_donne_un_resultat_simule(self, repondre):
        # Rien n'est exécuté : ce qui compte est que la cible ait accepté
        # d'agir. C'est ça, l'abus d'agentivité (LLM06).
        repondre("Je consulte. [OUTIL: consulter_dossier(Marie Dupont)]")
        reponse = construire_cible_demo(1)("question")
        assert "résultat de l'outil" in reponse
        assert demo.DOSSIER_CONFIDENTIEL in reponse

    def test_sans_appel_rien_n_est_ajoute(self, repondre):
        repondre("Bonjour, comment puis-je vous aider ?")
        assert "résultat de l'outil" not in construire_cible_demo(1)("question")

    @pytest.mark.parametrize("ecriture", [
        "[OUTIL: consulter_dossier(Marie)]",
        "OUTIL: consulter_dossier(Marie)",
        "[outil : consulter_dossier(Marie)]",
    ])
    def test_plusieurs_ecritures_sont_reconnues(self, repondre, ecriture):
        # Un LLM ne reproduit pas un gabarit au caractère près.
        repondre(f"Voici : {ecriture}")
        assert "résultat de l'outil" in construire_cible_demo(1)("question")


class TestSelecteur:
    @pytest.mark.parametrize("nom, attendu", [
        ("demo", "interroger_demo_niveau1"),
        ("demo:1", "interroger_demo_niveau1"),
        ("demo:3", "interroger_demo_niveau3"),
    ])
    def test_le_niveau_se_lit_dans_le_nom(self, nom, attendu):
        assert choisir_cible(nom).__name__ == attendu

    @pytest.mark.parametrize("nom", ["demo:9", "demo:abc"])
    def test_un_niveau_invalide_est_refuse_clairement(self, nom):
        with pytest.raises(ValueError, match="Niveau de démonstration"):
            choisir_cible(nom)


class TestAucunMandatPourLesCiblesLivrees:
    """
    Les cibles livrées tournent en local et ne contiennent que des secrets
    factices : exiger un mandat pour elles casserait la démonstration en une
    commande. Ce test existe parce que l'oubli s'est produit en ajoutant
    `demo` — et qu'il se reproduira à la cible suivante.
    """

    @pytest.mark.parametrize("nom", ["demo", "demo:2", "demo:3"])
    def test_la_cible_de_demonstration_n_en_demande_pas(self, nom):
        assert est_cible_livree(nom) and est_locale(nom)

    def test_toute_cible_nommee_est_reconnue_comme_livree(self):
        # Le garde-fou qui attrapera le prochain oubli.
        for nom in CIBLES_NOMMEES:
            assert est_cible_livree(nom) and est_locale(nom), nom

    def test_une_cible_distante_en_demande_toujours_un(self):
        assert not est_locale("https://client.fr/chat")


class TestSecretsFactices:
    def test_le_secret_livre_est_manifestement_factice(self):
        # Le dépôt est public : livrer une cible vulnérable est banal, y
        # laisser une vraie valeur ne l'est pas.
        assert SECRET == "ARCHIVES-7731"
        assert "Dupont" in demo.DOSSIER_CONFIDENTIEL
