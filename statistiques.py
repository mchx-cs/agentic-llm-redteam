"""
statistiques.py — Ce qu'un résultat borne, et ce qu'il ne borne pas.

Le GenAI Red Teaming Manual d'OWASP (v1.0, octobre 2026, §7.5) est catégorique :

    « A test round with zero observed successes does not demonstrate that the
    system is secure; it only bounds how large the true attack success rate
    could still be. Report negatives as a bounded null with an upper
    confidence limit, never as proof of security. »

C'était le dernier endroit où cet outil laissait croire à une sécurité qu'il
n'avait pas vérifiée. Une campagne qui ne trouvait rien écrivait « aucun
constat » et s'arrêtait là, alors qu'avec `MAX_ESSAIS=3` la règle de trois
donne une borne de 3/3 = 100 % : ce « aucun constat » ne bornait rien du tout.

LE PIÈGE, et c'est le manuel qui le pose juste après :

    « Shared sessions, repeated prompts, adaptive search, and heterogeneous
    targets can violate the independent, common-probability binomial model. […]
    Do not apply binomial confidence bounds to adaptive or dependent attempts
    without a justified statistical model. »

Or une campagne de ce projet est ADAPTATIVE (le prochain essai dépend des
réponses précédentes, voir `agents/adaptation.py`) et HÉTÉROGÈNE (des sondes
différentes, de familles différentes, contre des objectifs différents).
Appliquer 3/N à ses essais produirait un chiffre qui a l'air rigoureux et qui
ne l'est pas — exactement le genre de faux confort que ce projet combat.

D'où la règle appliquée ici : **on ne borne que ce qui est borné.** Le seul
endroit i.i.d. du projet est le REJEU — même payload, même cible, essais
indépendants (`agents/verificateur.py`). Ailleurs, on refuse de calculer et on
dit pourquoi, ce qui est une information en soi.
"""

import math

# Valeur critique de la loi normale pour un intervalle bilatéral à 95 %.
# En dur plutôt que calculée : une seule constante, pas de dépendance.
Z_95 = 1.959963984540054

# Niveau de confiance associé, pour l'afficher sans le coder deux fois.
CONFIANCE = 0.95


def borne_superieure_zero(essais):
    """
    Borne supérieure du taux de succès réel quand on a observé ZÉRO succès.

    C'est la « règle de trois » : avec 0 succès sur N essais indépendants, le
    taux réel peut encore atteindre environ 3/N, à 95 % de confiance. Elle
    approxime 1 − 0,05^(1/N), et l'écart est négligeable dès N ≈ 20.

    0 sur 3   → 100 %  (autrement dit : on n'a rien montré)
    0 sur 30  → 10 %
    0 sur 100 → 3 %
    0 sur 300 → 1 %
    """
    if essais <= 0:
        return 1.0
    return min(1.0, 3.0 / essais)


def essais_pour_ecarter(taux_cible):
    """
    Combien d'essais indépendants pour écarter un taux de succès résiduel.

    Inverse de la règle de trois : pour affirmer « le taux réel est sous 5 % »,
    il faut environ 60 essais sans succès. C'est ce qui transforme une
    exigence (« je veux écarter 1 % ») en budget de campagne.
    """
    if not 0 < taux_cible < 1:
        raise ValueError("Le taux à écarter doit être strictement entre 0 et 1.")
    return math.ceil(3.0 / taux_cible)


def intervalle_wilson(succes, essais, z=Z_95):
    """
    Intervalle de Wilson pour une proportion : (borne basse, borne haute).

    Préféré à l'approximation normale naïve, que le manuel écarte
    explicitement parce qu'elle « breaks down near 0 and 1 and at small N » —
    et nos compteurs sont justement petits : 2 succès sur 3 rejeux.

    Sur ce cas, Wilson donne environ 0,21 à 0,94 : une fourchette large, et
    c'est la vérité. Dire « 67 % » tout court laisserait croire à une précision
    que trois essais ne donnent pas.
    """
    if essais <= 0:
        return (0.0, 1.0)
    if not 0 <= succes <= essais:
        raise ValueError(f"{succes} succès sur {essais} essais : impossible.")

    proportion = succes / essais
    denominateur = 1 + z * z / essais
    centre = (proportion + z * z / (2 * essais)) / denominateur
    demi = (z / denominateur) * math.sqrt(
        proportion * (1 - proportion) / essais + z * z / (4 * essais * essais))
    return (max(0.0, centre - demi), min(1.0, centre + demi))


# --- Ce qu'on a le droit de borner -------------------------------------------

# Pourquoi un drapeau explicite plutôt qu'un calcul systématique : l'appelant
# est le seul à savoir si ses essais étaient indépendants. Le rejeu l'est
# (même payload, même cible) ; une campagne adaptative ne l'est pas. Rendre ce
# fait OBLIGATOIRE à l'appel évite qu'une borne apparaisse un jour là où elle
# ne vaut rien, par simple réutilisation de la fonction.

MOTIF_DEPENDANCE = (
    "essais adaptatifs et hétérogènes : le prochain dépend des réponses "
    "précédentes, et les payloads viennent de familles différentes. Le modèle "
    "binomial ne s'applique pas, donc aucune borne n'est calculée ici."
)


def resumer(succes, essais, independants, quoi="essais"):
    """
    Ce que ce décompte permet d'affirmer, en toutes lettres.

    Renvoie un dictionnaire, pas une phrase : `rapport.py` en fait le rendu, et
    `resultat.json` le garde tel quel — le JSON reste la source de vérité.

    `independants` est exigé à chaque appel, sans valeur par défaut. Un défaut
    à True ferait apparaître des bornes injustifiées au premier oubli ; un
    défaut à False les ferait disparaître silencieusement là où elles comptent.
    """
    resume = {
        "succes": succes,
        "essais": essais,
        "independants": bool(independants),
        "quoi": quoi,
        "taux_observe": (succes / essais) if essais else None,
    }

    if not independants:
        resume["borne"] = None
        resume["explication"] = MOTIF_DEPENDANCE
        return resume

    if succes == 0:
        borne = borne_superieure_zero(essais)
        resume["borne"] = {"haute": borne, "basse": 0.0,
                           "methode": "règle de trois"}
        resume["explication"] = (
            f"0 succès sur {essais} {quoi} ne démontre rien : le taux réel "
            f"peut encore atteindre {borne:.0%} "
            f"(borne supérieure à {CONFIANCE:.0%}).")
        return resume

    basse, haute = intervalle_wilson(succes, essais)
    resume["borne"] = {"basse": basse, "haute": haute, "methode": "Wilson"}
    resume["explication"] = (
        f"{succes} succès sur {essais} {quoi} : le taux réel se situe entre "
        f"{basse:.0%} et {haute:.0%} (intervalle de Wilson à "
        f"{CONFIANCE:.0%}), pas exactement {succes / essais:.0%}.")
    return resume
