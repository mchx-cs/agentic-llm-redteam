"""
Tests du rapport.

La gravité vient de règles, pas d'un modèle : elle est donc entièrement
testable. C'était l'argument pour choisir des règles — le voici vérifié.

Ce qui est surveillé de près : que le rapport ne puisse jamais laisser croire
à une couverture qu'il n'a pas.
"""

import pytest

from rapport import construire, evaluer_gravite, rendre_markdown


def _payload(technique="t", famille="LLM02"):
    return {"technique": technique, "famille_owasp": famille,
            "objectif": "secret", "transformation": "identite",
            "texte": "payload"}


def _verdict(critere="divulgation", valeur="V"):
    return {"reussi": True, "critere": critere, "valeur": valeur,
            "analyse": "analyse du juge", "votes": [True, True, True]}


def _constat(critere="divulgation", rejeu=None, tronquee=False):
    verification = ({"statut": rejeu, "explication": "explication"}
                    if rejeu else None)
    return {"essai": 1, "payload": _payload(), "reponse": "réponse",
            "verdict": _verdict(critere), "verification": verification,
            "tronquee": tronquee}


def _resultat(constats=(), ecartees=(), essais=(), fiche=None):
    return {"statut": "constats" if constats else "aucun_constat",
            "fiche": fiche,
            "plan": {"essais": list(essais), "ecartees": list(ecartees)},
            "constats": list(constats),
            "journal": {"appels": 3, "tokens": 100, "tronquees": []}}


class TestGravite:
    @pytest.mark.parametrize("critere, rejeu, attendu", [
        ("divulgation", "confirmee", "elevee"),
        ("divulgation", "contradictoire", "a_verifier"),
        ("divulgation", "inconcluant", "a_verifier"),
        ("divulgation", "non_verifiable", "moyenne"),
        ("obeissance", None, "moyenne"),
    ])
    def test_les_regles_sont_respectees(self, critere, rejeu, attendu):
        verification = {"statut": rejeu, "explication": ""} if rejeu else None
        gravite, _ = evaluer_gravite(_verdict(critere), verification, False)
        assert gravite == attendu

    def test_un_cas_imprevu_ne_disparait_pas(self):
        # Il doit remonter comme « à vérifier », jamais être minimisé.
        gravite, _ = evaluer_gravite(_verdict("critere_inconnu"), None, False)
        assert gravite == "a_verifier"

    def test_une_reponse_tronquee_est_signalee_sans_changer_la_gravite(self):
        gravite, pourquoi = evaluer_gravite(
            _verdict("obeissance"), None, tronquee=True)
        assert gravite == "moyenne"
        assert "tronquée" in pourquoi

    def test_la_gravite_ne_varie_pas_d_un_appel_a_l_autre(self):
        # Un rapport dont les gravités bougent est indéfendable.
        appels = [evaluer_gravite(_verdict("divulgation"),
                                  {"statut": "confirmee", "explication": ""},
                                  False) for _ in range(5)]
        assert len(set(appels)) == 1


class TestStructure:
    def test_les_constats_sont_tries_du_plus_grave_au_moins_grave(self):
        rapport = construire(_resultat(constats=[
            _constat("obeissance"),                      # moyenne
            _constat("divulgation", "inconcluant"),      # à vérifier
            _constat("divulgation", "confirmee"),        # élevée
        ]))
        assert [c["gravite"] for c in rapport["constats"]] == \
               ["elevee", "moyenne", "a_verifier"]

    def test_chaque_constat_recoit_un_identifiant(self):
        rapport = construire(_resultat(constats=[_constat(), _constat()]))
        assert [c["id"] for c in rapport["constats"]] == ["C01", "C02"]

    def test_les_familles_ecartees_sont_conservees(self):
        rapport = construire(_resultat(ecartees=[
            {"technique": "abus-outils", "famille_owasp": "LLM06",
             "motifs": ["aucun outil"]}]))
        assert rapport["couverture"]["familles_ecartees"][0]["technique"] == \
               "abus-outils"


class TestRendu:
    def test_sans_constat_le_rapport_renvoie_a_la_couverture(self):
        # Le point le plus important : ne jamais laisser croire à une
        # couverture qu'on n'a pas.
        texte = rendre_markdown(construire(_resultat()))
        assert "avant d'en conclure que la cible est sûre" in texte

    def test_deux_techniques_d_une_meme_famille_restent_distinctes(self):
        # Afficher la seule famille donnerait deux lignes identiques.
        texte = rendre_markdown(construire(_resultat(ecartees=[
            {"technique": "injection-directe", "famille_owasp": "LLM01",
             "motifs": ["aucun modèle"]},
            {"technique": "jailbreak", "famille_owasp": "LLM01",
             "motifs": ["aucun modèle"]}])))
        assert "injection-directe" in texte and "jailbreak" in texte

    @pytest.mark.parametrize("attendu", [
        "# Rapport de campagne", "## Constats", "## Couverture", "Élevée", "C01",
    ])
    def test_le_rendu_contient_ses_sections(self, attendu):
        texte = rendre_markdown(construire(_resultat(
            constats=[_constat("divulgation", "confirmee")])))
        assert attendu in texte

    def test_les_reponses_tronquees_sont_annoncees_en_tete(self):
        resultat = _resultat(constats=[_constat()])
        resultat["journal"]["tronquees"] = [{"profil": "local"}]
        assert "tronquée(s)" in rendre_markdown(construire(resultat))

    def test_la_fiche_cible_est_reprise_quand_elle_existe(self):
        texte = rendre_markdown(construire(_resultat(fiche={
            "role": "assistant bancaire", "langue": "fr",
            "outils": ["solde"], "sujets_refuses": []})))
        assert "assistant bancaire" in texte and "solde" in texte
