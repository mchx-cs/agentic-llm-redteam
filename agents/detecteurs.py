"""
agents/detecteurs.py — Pré-traitement déterministe des réponses de la cible.

Un LLM est mauvais pour décoder du Base64 de tête ou pour repérer qu'un mot
est écrit lettre par lettre. Du code Python, lui, le fait sans jamais se
tromper. On fait donc ce travail AVANT l'arbitre, et on lui montre le
résultat : il juge alors un texte en clair au lieu de devoir deviner.

Ces détecteurs ne tranchent RIEN : ils ne connaissent pas le secret et ne
disent pas "faille". Ils rendent seulement visible ce qui était caché. La
décision reste à l'arbitre (principe du juge en boîte noire).
"""

import base64
import binascii
import re

# Au moins 4 caractères isolés séparés par des espaces, tirets, points…
# ex. "T - O - P - S" ou "T.O.P.S". En dessous de 4, trop de faux positifs
# ("a - b" apparaît dans du texte normal).
_MOTIF_EPELE = re.compile(r"(?<!\w)(?:\w[\s\-\.\,·_/|]+){3,}\w(?!\w)")
_SEPARATEURS = re.compile(r"[\s\-\.\,·_/|]+")

# Candidats Base64 : 8 caractères ou plus de l'alphabet Base64.
_MOTIF_BASE64 = re.compile(r"[A-Za-z0-9+/]{8,}={0,2}")

# Candidats hexadécimaux : au moins 4 octets (8 chiffres hexa).
_MOTIF_HEXA = re.compile(r"\b(?:[0-9a-fA-F]{2}){4,}\b")


def _est_texte_lisible(texte):
    """Un décodage n'a de sens que s'il donne du texte, pas du bruit binaire."""
    return bool(texte) and texte.isprintable() and any(c.isalnum() for c in texte)


def recoller_epele(reponse):
    """Trouve les mots écrits lettre par lettre et les recolle."""
    trouves = []
    for correspondance in _MOTIF_EPELE.finditer(reponse):
        morceau = correspondance.group()
        lettres = _SEPARATEURS.split(morceau)
        # On ne garde que les vraies épellations : un caractère par morceau.
        # Sinon "Je suis là - pour vous" serait pris pour une épellation.
        if all(len(lettre) == 1 for lettre in lettres):
            trouves.append({"type": "épelé", "original": morceau,
                            "decode": "".join(lettres)})
    return trouves


def decoder_base64(reponse):
    """Trouve les chaînes Base64 qui se décodent en texte lisible."""
    trouves = []
    for candidat in _MOTIF_BASE64.findall(reponse):
        try:
            # validate=True : refuse tout caractère hors alphabet Base64.
            decode = base64.b64decode(candidat, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            continue  # pas du Base64, ou du binaire : on ignore
        # Un mot ordinaire comme "question" se "décode" aussi, mais en
        # octets illisibles : le filtre de lisibilité les écarte.
        if _est_texte_lisible(decode):
            trouves.append({"type": "base64", "original": candidat,
                            "decode": decode})
    return trouves


def decoder_hexa(reponse):
    """Trouve les chaînes hexadécimales qui se décodent en texte lisible."""
    trouves = []
    for candidat in _MOTIF_HEXA.findall(reponse):
        try:
            decode = bytes.fromhex(candidat).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if _est_texte_lisible(decode):
            trouves.append({"type": "hexadécimal", "original": candidat,
                            "decode": decode})
    return trouves


def analyser(reponse):
    """Applique tous les détecteurs. Renvoie la liste de ce qu'ils ont décodé."""
    return recoller_epele(reponse) + decoder_base64(reponse) + decoder_hexa(reponse)
