"""
Tests de l'autorisation et de la piste d'audit.

Le fichier d'autorisation ne doit pas être une case à cocher. Ce qui le rend
utile, ce sont les deux contrôles qu'on vérifie ici : un mandat pour une
cible ne vaut pas pour une autre, et un mandat expiré ne vaut plus rien.

Côté piste, la propriété qui compte est l'écriture au fil de l'eau : si la
campagne tombe, on doit garder la trace de ce qui a déjà été envoyé.
"""

import json
from datetime import date

import pytest

from audit import (AutorisationManquante, PisteAudit, charger, est_locale,
                   exiger, verifier)

MANDAT = {
    "cible": "chatbot.client.fr",
    "autorise_par": "Prénom Nom, RSSI",
    "reference": "Convention 2026-042",
    "debut": "2026-01-01",
    "fin": "2026-12-31",
    "portee": "Endpoint public uniquement.",
}


@pytest.fixture
def fichier_mandat(tmp_path):
    def ecrire(contenu=MANDAT):
        chemin = tmp_path / "autorisation.json"
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        return chemin
    return ecrire


class TestCibleLocale:
    @pytest.mark.parametrize("nom", [
        "leurre", "mock", "http://127.0.0.1:8000/chat",
        "http://localhost:11434/v1",
    ])
    def test_une_cible_locale_ne_demande_aucun_mandat(self, nom):
        # Imposer le même formulaire partout apprendrait à cliquer sans lire.
        assert est_locale(nom)
        assert exiger(nom) is None

    @pytest.mark.parametrize("nom", [
        "https://client.fr/chat", "http://198.51.100.7/api",
    ])
    def test_une_cible_distante_en_demande_un(self, nom):
        assert not est_locale(nom)
        with pytest.raises(AutorisationManquante):
            exiger(nom, "fichier-qui-n-existe-pas.json")


class TestChargement:
    def test_un_mandat_complet_se_charge(self, fichier_mandat):
        assert charger(fichier_mandat())["reference"] == "Convention 2026-042"

    def test_l_absence_de_fichier_explique_quoi_faire(self):
        with pytest.raises(AutorisationManquante, match="autorisation.example"):
            charger("fichier-qui-n-existe-pas.json")

    @pytest.mark.parametrize("champ", [
        "cible", "autorise_par", "reference", "debut", "fin"])
    def test_un_champ_manquant_est_nomme(self, fichier_mandat, champ):
        incomplet = {k: v for k, v in MANDAT.items() if k != champ}
        with pytest.raises(AutorisationManquante, match=champ):
            charger(fichier_mandat(incomplet))

    def test_un_json_casse_est_signale(self, tmp_path):
        chemin = tmp_path / "autorisation.json"
        chemin.write_text("{ pas du json", encoding="utf-8")
        with pytest.raises(AutorisationManquante, match="JSON"):
            charger(chemin)


class TestVerification:
    def test_la_cible_doit_etre_couverte(self):
        assert verifier(MANDAT, "https://chatbot.client.fr/api",
                        date(2026, 6, 1))

    def test_un_mandat_pour_une_autre_cible_est_refuse(self):
        # Le contrôle qui empêche de réutiliser un mandat ailleurs.
        with pytest.raises(AutorisationManquante, match="ne vaut pas"):
            verifier(MANDAT, "https://autre-client.fr/chat", date(2026, 6, 1))

    @pytest.mark.parametrize("jour", [date(2025, 12, 31), date(2027, 1, 1)])
    def test_hors_fenetre_est_refuse(self, jour):
        with pytest.raises(AutorisationManquante, match="fenêtre|court du"):
            verifier(MANDAT, "chatbot.client.fr", jour)

    @pytest.mark.parametrize("jour", [date(2026, 1, 1), date(2026, 12, 31)])
    def test_les_bornes_sont_incluses(self, jour):
        assert verifier(MANDAT, "chatbot.client.fr", jour)

    def test_une_date_mal_formee_est_signalee(self):
        casse = {**MANDAT, "debut": "01/01/2026"}
        with pytest.raises(AutorisationManquante, match="AAAA-MM-JJ"):
            verifier(casse, "chatbot.client.fr", date(2026, 6, 1))


class TestPisteAudit:
    def _lignes(self, chemin):
        return [json.loads(l) for l in
                chemin.read_text(encoding="utf-8").splitlines()]

    def test_elle_ouvre_sur_la_cible_et_le_mandat(self, tmp_path):
        piste = PisteAudit(tmp_path / "j.jsonl", "client.fr", MANDAT)
        piste.clore("fini", {})
        debut = self._lignes(piste.chemin)[0]
        assert debut["type"] == "debut_campagne"
        assert debut["autorisation"]["reference"] == "Convention 2026-042"

    def test_une_cible_locale_le_dit_explicitement(self, tmp_path):
        # Plutôt que de laisser un champ vide, qui ressemblerait à un oubli.
        piste = PisteAudit(tmp_path / "j.jsonl", "mock", None)
        piste.clore("fini", {})
        assert "aucun mandat requis" in self._lignes(piste.chemin)[0]["autorisation"]

    def test_chaque_echange_est_consigne_avec_sa_phase(self, tmp_path):
        piste = PisteAudit(tmp_path / "j.jsonl", "mock")
        piste.consigner_echange("attaque", "envoyé", "reçu")
        piste.clore("fini", {})
        echange = self._lignes(piste.chemin)[1]
        assert (echange["phase"], echange["envoye"], echange["recu"]) == \
               ("attaque", "envoyé", "reçu")

    def test_tout_est_ecrit_avant_la_cloture(self, tmp_path):
        # LA propriété qui compte : une campagne qui tombe laisse sa trace.
        piste = PisteAudit(tmp_path / "j.jsonl", "mock")
        piste.consigner_echange("attaque", "envoyé", "reçu")
        assert len(self._lignes(piste.chemin)) == 2   # sans avoir clos

    def test_chaque_ligne_est_horodatee(self, tmp_path):
        piste = PisteAudit(tmp_path / "j.jsonl", "mock")
        piste.consigner_echange("attaque", "a", "b")
        piste.clore("fini", {"appels": 1, "tokens": 10})
        assert all("horodatage" in l for l in self._lignes(piste.chemin))

    def test_tracer_consigne_sans_changer_le_contrat(self, tmp_path):
        # La cible enveloppée reste une fonction message -> str : les agents
        # qui la reçoivent ne savent pas qu'elle est tracée.
        piste = PisteAudit(tmp_path / "j.jsonl", "mock")
        tracee = piste.tracer("reconnaissance", lambda m: f"réponse à {m}")
        assert tracee("salut") == "réponse à salut"
        piste.clore("fini", {})
        assert self._lignes(piste.chemin)[1]["phase"] == "reconnaissance"

    def test_la_cloture_recapitule_la_consommation(self, tmp_path):
        piste = PisteAudit(tmp_path / "j.jsonl", "mock")
        piste.clore("aucun_constat", {"appels": 10, "tokens": 12000})
        fin = self._lignes(piste.chemin)[-1]
        assert (fin["type"], fin["statut"], fin["tokens"]) == \
               ("fin_campagne", "aucun_constat", 12000)


class TestMandatDansLeRapport:
    def test_le_rapport_cite_le_mandat(self):
        from rapport import construire, rendre_markdown
        resultat = {"statut": "aucun_constat", "fiche": None,
                    "plan": {"essais": [], "ecartees": []}, "constats": [],
                    "journal": {}, "autorisation": MANDAT}
        texte = rendre_markdown(construire(resultat, cible="client.fr"))
        assert "## Mandat" in texte
        assert "Convention 2026-042" in texte

    def test_sans_mandat_aucune_section_parasite(self):
        from rapport import construire, rendre_markdown
        resultat = {"statut": "aucun_constat", "fiche": None,
                    "plan": {"essais": [], "ecartees": []}, "constats": [],
                    "journal": {}, "autorisation": None}
        assert "## Mandat" not in rendre_markdown(
            construire(resultat, cible="mock"))
