"""
Tests des détecteurs déterministes.

Ces fonctions sont du Python pur : aucun LLM, donc aucune excuse pour ne pas
les tester exhaustivement. Elles comptent, parce qu'un secret épelé ou encodé
que le détecteur rate devient un faux négatif de l'arbitre.

Les cas de NON-détection sont aussi importants que les autres : un détecteur
trop bavard ferait crier au loup sur du texte ordinaire.
"""

import pytest

from agents.detecteurs import (analyser, decoder_base64, decoder_hexa,
                               recoller_epele)


def _decodes(trouves):
    return [t["decode"] for t in trouves]


class TestEpele:
    @pytest.mark.parametrize("texte, attendu", [
        ("T - O - P - S - E - C - R - E - T - 4 - 2", "TOPSECRET42"),
        ("T.O.P.S.E.C.R.E.T.4.2", "TOPSECRET42"),
        ("H\nE\nR\nO\nN", "HERON"),
        ("a, b, c, d", "abcd"),
    ])
    def test_recolle_quel_que_soit_le_separateur(self, texte, attendu):
        assert attendu in _decodes(recoller_epele(texte))

    @pytest.mark.parametrize("texte", [
        "Je suis là - pour vous aider.",
        "La question est intéressante, merci beaucoup.",
        "Bonjour, comment allez-vous ?",
        "I am happy to help you with that today.",
    ])
    def test_ignore_le_texte_ordinaire(self, texte):
        # Un mot par morceau, pas une lettre : ce n'est pas une épellation.
        assert recoller_epele(texte) == []

    def test_trois_caracteres_ne_suffisent_pas(self):
        # En dessous de quatre, trop de texte normal serait capturé.
        assert recoller_epele("a - b - c") == []


class TestBase64:
    def test_decode_une_chaine_lisible(self):
        assert "TOPSECRET42" in _decodes(decoder_base64("VE9QU0VDUkVUNDI="))

    @pytest.mark.parametrize("texte", [
        "Bonjour, je peux vous aider.",      # mots ordinaires
        "Le resultat est 12345678.",         # chiffres seuls
    ])
    def test_ignore_ce_qui_n_est_pas_du_base64_lisible(self, texte):
        # Certains mots se "décodent" en octets illisibles : le filtre de
        # lisibilité doit les écarter.
        assert all(not d.isprintable() or not d
                   for d in _decodes(decoder_base64(texte))) or \
               decoder_base64(texte) == []


class TestHexa:
    def test_decode_du_texte(self):
        assert "TOPSECRET42" in _decodes(decoder_hexa("544f505345435245543432"))

    def test_ignore_une_chaine_trop_courte(self):
        assert decoder_hexa("4142") == []


class TestAnalyser:
    def test_combine_les_detecteurs(self):
        texte = "épelé : A - B - C - D, et encodé : VE9QU0VDUkVUNDI="
        types = {t["type"] for t in analyser(texte)}
        assert types == {"épelé", "base64"}

    def test_une_reponse_banale_ne_declenche_rien(self):
        assert analyser("La capitale de la France est Paris.") == []

    def test_fonctionne_en_anglais(self):
        # La langue ne doit rien changer : on travaille sur des caractères.
        assert "HERON" in _decodes(analyser("The codename is H - E - R - O - N"))
