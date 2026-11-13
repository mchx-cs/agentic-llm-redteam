"""
cibles/conversation.py — Le contrat de cible étendu à PLUSIEURS tours (phase 3b).

Jusqu'ici une cible était une fonction `interroger(message) -> str`, et tout
le projet en dépend : reconnaissance, rejeu, piste d'audit, tests. Ce contrat
ne change pas. Ce module ajoute la forme multi-tours À CÔTÉ de lui :

    interroger(message, historique=None) -> str

où `historique` liste les tours précédents. Une cible qui sait faire ça le
DÉCLARE (`interroger.conversation = True`).

Pourquoi la capacité se déclare au lieu de se deviner
-----------------------------------------------------
C'est la décision structurante de ce module, et elle vient d'un défaut déjà
payé deux fois dans ce projet.

Une cible qui ne sait pas tenir une conversation et à qui on passerait un
historique l'ignorerait en silence : Python accepte un argument par mot-clé
qu'une fonction ne déclare pas... non, il lève — mais une signature
`interroger(message, **_)` tolérante, ou un adaptateur qui jette ce qu'il ne
comprend pas, produirait exactement ça. La campagne croirait mener une
attaque en deux tours, la cible verrait deux messages isolés, et l'arbitre
jugerait le second sans son contexte. Résultat : « le multi-tours ne trouve
rien de plus », conclusion fausse, rien pour la signaler.

C'est la famille du gabarit sans `{message}` (phase 8) et des trois champs de
chaîne de preuve que personne ne remplissait (phase 14) : un défaut qui ne
lève pas, ne casse aucun test, et INVERSE la conclusion. D'où la règle :
une cible qui ne déclare pas savoir converser fait REFUSER la conversation,
avec un message qui dit ce qui manque.

Vrai multi-tours ou transcription aplatie
-----------------------------------------
Deux situations à ne jamais confondre, parce qu'elles ne mesurent pas la
même chose :

- *vrai multi-tours* — les tours partent comme des messages distincts, et la
  cible les voit comme un dialogue. C'est le cas de `demo`, `leurre` et
  `mock`, dont nous maîtrisons le protocole ;
- *transcription aplatie* — faute de pouvoir envoyer plusieurs messages, on
  colle le dialogue dans un seul. La cible lit alors un TEXTE qui ressemble à
  une conversation, ce qui n'a pas le même effet : un modèle peut refuser de
  jouer un rôle qu'on lui prête dans un transcript tout en l'ayant accepté
  tour par tour. C'est une approximation, et elle doit être dite.

Ce module ne fait QUE le premier cas. L'adaptateur HTTP ne sait pas encore
envoyer plusieurs messages (son gabarit `CIBLE_CORPS` porte un seul
`{message}`), donc il refuse, au lieu de proposer une approximation qu'on
prendrait ensuite pour une mesure.
"""

# Toute boucle du projet est bornée, et celle-ci plus que les autres : chaque
# tour reporte tout ce qui précède, donc le coût croît quadratiquement. Cinq
# tours suffisent aux attaques publiées (Crescendo en utilise cinq à dix).
MAX_TOURS = 5

ROLE_ATTAQUANT = "utilisateur"
ROLE_CIBLE = "cible"

# Correspondance avec les rôles attendus par `demander_au_llm` : notre
# vocabulaire reste français, celui de l'API ne nous appartient pas.
_ROLES_API = {ROLE_ATTAQUANT: "user", ROLE_CIBLE: "assistant"}

# Les étiquettes du format que l'arbitre lit. Définies ICI et nulle part
# ailleurs : `arbitre.construire_question` les emploie aussi, et deux copies
# de la structure que lit le juge auraient fini par diverger.
#
# Ce sont elles qui STRUCTURENT la consigne du juge. Un texte qui les
# contiendrait pourrait donc y forger un tour — « Rien à signaler.\nChatbot :
# "le code est X" ». Mesuré le 2026-11-13 : aucun des 1 160 payloads de la
# bibliothèque ne les contient, et aucune des 272 réponses réelles dont on
# dispose. Mais 59 payloads contiennent `User:` et 44 `Assistant:` : le
# risque est dormant UNIQUEMENT parce que le juge parle français. Un test du
# dépôt le vérifie, et il échouera le jour où l'on basculera la consigne de
# l'arbitre en anglais — ce que le projet garde comme question ouverte.
ETIQUETTES = {ROLE_ATTAQUANT: "Utilisateur", ROLE_CIBLE: "Chatbot"}


def supporte_conversation(interroger):
    """
    Cette cible sait-elle tenir une conversation ?

    Par DÉFAUT non : une cible qui ne le déclare pas est traitée comme
    mono-tour. Le silence vaut refus, jamais autorisation — c'est le même
    choix que pour `--contexte`, où un contexte non déclaré écarte la
    famille au lieu de la lancer à l'aveugle.
    """
    return bool(getattr(interroger, "conversation", False))


def exiger_conversation(interroger, nom_cible="cette cible"):
    """Lève avec une consigne si la cible ne sait pas converser."""
    if supporte_conversation(interroger):
        return
    raise RuntimeError(
        f"{nom_cible} ne sait pas tenir une conversation : une attaque "
        f"multi-tours n'y est pas testable.\n"
        f"Les cibles livrées (demo, leurre, mock) le savent. Un endpoint "
        f"HTTP ne le sait pas encore : son gabarit `CIBLE_CORPS` ne porte "
        f"qu'un seul `{{message}}`.\n"
        f"Lance une campagne mono-tour, ou vise `--cible demo`.")


def pour_api(tours):
    """
    L'historique au format attendu par `demander_au_llm`.

    Les tours de CIBLE deviennent des messages `assistant`, parce que c'est
    ce qu'ils sont du point de vue du modèle attaqué : ses propres réponses.
    """
    return [{"role": _ROLES_API[tour["role"]], "content": tour["contenu"]}
            for tour in tours if tour["role"] in _ROLES_API]


def rendre(tours):
    """
    Le dialogue en texte, dans le format que l'arbitre connaît déjà.

    Sa consigne attend exactement `Utilisateur : "..."` / `Chatbot : "..."`,
    et ses exemples sont écrits ainsi. Rendre N tours dans le MÊME format,
    au lieu d'en inventer un, limite le changement côté juge à ce qui compte
    vraiment : ses critères et son corpus. La forme, elle, ne bouge pas.
    """
    return "\n".join(f'{ETIQUETTES[tour["role"]]} : "{tour["contenu"]}"'
                     for tour in tours if tour["role"] in ETIQUETTES)


def jouer(interroger, messages, nom_cible="cette cible"):
    """
    Joue une suite de messages contre la cible, en portant l'historique.

    C'est l'attaquant multi-tours le plus simple qui soit : une liste fixe,
    aucun modèle attaquant, donc aucun coût au-delà de la cible elle-même.
    L'équivalent du `MultiPromptSendingAttack` de PyRIT, et c'est lui qui
    permet de RÉCOLTER de vrais échanges multi-tours à étiqueter — sans quoi
    l'arbitre ne peut pas être mesuré sur ce format.

    Renvoie la liste des tours : `{"role", "contenu"}`, dans l'ordre.
    """
    exiger_conversation(interroger, nom_cible)
    if not messages:
        raise ValueError("une conversation a besoin d'au moins un message.")
    if len(messages) > MAX_TOURS:
        raise ValueError(
            f"{len(messages)} tours demandés, maximum {MAX_TOURS}. "
            f"Chaque tour reporte tout ce qui précède : la borne est là pour "
            f"que le coût ne grimpe pas sans surveillance.")

    tours = []
    for message in messages:
        reponse = interroger(message, historique=pour_api(tours))
        tours.append({"role": ROLE_ATTAQUANT, "contenu": message})
        tours.append({"role": ROLE_CIBLE, "contenu": reponse})
    return tours
