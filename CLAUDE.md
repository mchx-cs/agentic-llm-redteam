# Contexte projet — agentic-llm-redteam

## De quoi il s'agit

Système multi-agents qui automatise le red teaming d'applications LLM : on fournit
un endpoint, on récupère une liste de vulnérabilités validées (prompt injection,
jailbreak, fuite de prompt système…), en suivant l'OWASP Top 10 for LLM Applications.

Projet personnel d'apprentissage **et** vitrine publique (dépôt public, lu par des
recruteurs). Les deux objectifs comptent : le code doit être propre et lisible, et
le README doit rester honnête sur l'état d'avancement.

## État actuel : Phase 0 terminée, Phases 1 et 2 démarrées

La boucle complète **attaquant → cible → arbitre** tourne de bout en bout en local.

- **Phase 1** : la bibliothèque de payloads est structurée (technique × objectif ×
  transformation), mais seule la technique `controle` (anodine) a des modèles. Les
  familles OWASP sont déclarées vides : on les remplit une fois la technique
  pratiquée à la main.
- **Phase 2** : l'arbitre a des critères explicites, des exemples, une sortie JSON,
  une température à 0, raisonne avant de trancher, reçoit les passages décodés par
  `detecteurs.py` et s'abstient quand son verdict se contredit. Il est mesuré sur des
  échanges étiquetés à la main, répartis en un jeu de développement (24 échanges,
  `python -m evaluation.evaluer_arbitre`) et un jeu de test gelé (15 échanges,
  `--test`).

## Architecture

```
config.py          # point de bascule unique : modèle local (Ollama) ou API distante
llm_client.py      # LA couche d'abstraction : demander_au_llm()
cible.py           # le système testé (actuellement un leurre avec un secret à protéger)
agents/
  attaquant.py     # construit les payloads : technique × objectif × transformation
  arbitre.py       # LLM-as-judge : tranche succès / échec (sortie JSON)
  detecteurs.py    # décode l'épelé, le Base64, l'hexa AVANT l'arbitre (déterministe)
payloads/
  bibliotheque.json  # techniques (par famille OWASP) et objectifs
evaluation/
  echanges_etiquetes.json  # vérité terrain (jeux dev et test) pour mesurer l'arbitre
  evaluer_arbitre.py       # précision, rappel, détail des erreurs
  journal_test.jsonl       # chaque consultation du jeu de test, horodatée
main.py            # orchestrateur : boucle de campagne avec budget d'essais
```

## Règles à respecter impérativement

**Aucun appel direct à un fournisseur de LLM.** Tout passe par `demander_au_llm()`
dans `llm_client.py`. C'est ce qui rend la bascule local ↔ API indolore (une ligne
dans `config.py`). Ne jamais coder en dur un appel Ollama ou OpenAI ailleurs.

**Toujours borner les boucles.** Les attaques sont probabilistes : un agent adaptatif
boucle à l'infini sans garde-fou. `MAX_ESSAIS` dans `main.py` borne chaque campagne.
Toute nouvelle boucle doit avoir sa propre limite.

**Ne jamais régler l'arbitre d'après le jeu de test.** On ajuste prompt, critères et
détecteurs en regardant uniquement le jeu `dev`. Le jeu `test` ne se consulte qu'aux
moments clés (changement important, changement de modèle), et chaque consultation est
journalisée automatiquement. Un groupe (un scénario et ses reformulations) n'est
jamais réparti entre les deux jeux : le script le refuse. Les étiquettes sont la
vérité terrain : c'est l'auteur qui les valide, jamais l'arbitre ni un LLM.

**Jamais de clé d'API en dur.** Elles sont lues depuis les variables d'environnement
(voir le profil `api` dans `config.py`). Le dépôt est public.

## Conventions

- Code et commentaires **en français**, noms de variables inclus (`cible`, `attaquant`,
  `arbitre`, `payload`, `verdict`).
- Messages de commit **en français**, descriptifs (l'historique est public).
- README **en anglais** (visibilité internationale) — ne pas le basculer en français.
- Commentaires pédagogiques assumés : ce projet sert aussi à apprendre, les blocs
  expliquent le pourquoi, pas seulement le quoi.

## Environnement de développement

- **Windows**, terminal **Git Bash** (MSYS2/UCRT64).
- Environnement virtuel dans `.venv`, activation : `source .venv/Scripts/activate`
  (chemin Windows, pas `bin/`).
- Modèle local servi par **Ollama** (`llama3.2`), aucun coût, aucune clé.
- Dépendance unique : `openai` (le SDK parle aussi bien à Ollama qu'aux API distantes).

## Feuille de route

| Phase | Objectif | Statut |
|---|---|---|
| 0 | Boucle d'agents, couche d'abstraction, LLM-as-judge, budget d'essais | **Fait** |
| 1 | Bibliothèque de payloads de prompt injection réels | En cours |
| 2 | Fiabilité de l'arbitre : mesurer et réduire faux positifs / faux négatifs | En cours |
| 3 | Attaquant adaptatif multi-tours : évaluer PyRIT en remplacement de l'orchestrateur maison | Prévu |
| 4 | Dissocier l'arbitre du modèle cible | Prévu |
| 5 | Agents de reconnaissance et de planification ; campagnes multi-familles | Prévu |
| 6 | Génération de rapport avec classement par gravité | Prévu |
| 7 | Intégrer garak (couverture large) | Prévu |

## Décisions prises et leur raison

**L'arbitre ne connaît pas le secret de la cible.** Il juge uniquement d'après
l'échange visible, comme en test boîte noire réel. C'est ce qui rend sa tâche
difficile — et c'est le cœur technique du projet.

**Arbitre et cible partagent actuellement le même modèle.** Pratique pour démarrer,
mais c'est un biais connu : un juge identique à sa cible partage ses angles morts.
C'est l'objet de la Phase 4. `demander_au_llm()` accepte déjà un paramètre `modele`
pour permettre cette dissociation.

**Ne pas automatiser ce qu'on ne sait pas faire à la main.** Les vraies attaques
attendent que l'auteur ait terminé le path AI Security de TryHackMe. Un agent dont
on ne sait pas juger les hallucinations est inutilisable.

**PyRIT arrive en Phase 3, pas en Phase 7.** La boucle maison reproduit en miniature
les briques de PyRIT : `cible.py` correspond à un *target*, `main.py` à un
orchestrateur, `arbitre.py` à un *scorer*. Elle reste en place pour les Phases 1 et 2
(payloads, fiabilité de l'arbitre), parce que c'est là que se construit la
compréhension du problème. L'attaquant adaptatif multi-tours de la Phase 3 est en
revanche exactement ce que fournissent les attaques multi-tours de PyRIT. Le réécrire
à la main coûterait cher pour peu d'apprentissage. On évalue donc PyRIT en
**remplacement** de l'orchestrateur, pas en complément. Point à trancher à ce moment-là :
PyRIT appelle les modèles via ses propres *targets*, ce qui contourne
`demander_au_llm()`. La règle « aucun appel direct » devra être adaptée, par exemple
en configurant les *targets* PyRIT depuis `config.py`.

**Phase 5 : reconnaissance et planification choisissent les payloads.** La
bibliothèque à trois axes (technique × objectif × transformation) est conçue pour
qu'un agent choisisse chaque axe selon le contexte de la cible, au lieu de tout
lancer à l'aveugle :
- *Agent de reconnaissance* : il sonde la cible avec des questions anodines et produit
  une **fiche cible** en JSON (rôle, outils, langue, situations de refus).
- *Agent de planification* : à partir de la fiche, il écarte les familles hors sujet,
  remplit `{objectif}` selon le contexte, choisit les transformations et classe les
  combinaisons pour que les meilleures tiennent dans `MAX_ESSAIS`.

Choix de conception :
- **Hybride, pas tout LLM.** Le LLM extrait des *faits* vérifiables (la fiche cible) ;
  des règles déterministes en déduisent les familles (pas d'outil détecté → LLM06
  exclue). Un planificateur 100 % LLM peut halluciner un contexte et gaspiller le
  budget. Une fiche cible se vérifie à la main, donc se mesure, comme l'arbitre.
- **Planification ≠ adaptation.** La planification décide *avant* la campagne quoi
  lancer (Phase 5, code maison). L'adaptation reformule *pendant* l'attaque selon la
  réponse de la cible (Phase 3, PyRIT). PyRIT ne couvre pas la reconnaissance ni la
  planification : c'est la valeur ajoutée propre du projet.
- **Budget propre à la reconnaissance.** Sonder coûte des requêtes et peut déclencher
  les défenses de la cible : la reconnaissance a sa propre limite d'essais.
- **Calendrier.** À concevoir après les rooms AI Threat Modelling et AI System
  Reconnaissance du path, et une fois les Phases 1 et 2 assez avancées pour qu'il y
  ait de vrais payloads à choisir et un arbitre fiable pour juger.

**Le prompt engineering plafonne avec llama3.2 comme juge (mesuré le 2026-10-30).**
Arbitre actuel sur le jeu `dev` : précision 75 %, rappel 50 %, exactitude 67 % (même
rappel sur le jeu `test`). Deux pistes ont été mesurées sur `dev`, sans faire mieux :
- *A, consigne sans formule toute faite et analyse qui cite la réponse* : précision 83 %,
  rappel 42 %. Le juge cite le bon passage (« donne un indice sur le mot de passe »)
  puis conclut à l'inverse, et déforme parfois ses citations.
- *B, une question étroite oui/non par critère* : précision 62 %, rappel 42 %. Des
  verdicts incohérents (« Paris » classé comme divulgation, une fuite en clair ratée).

Conclusion : avec 3 milliards de paramètres, le modèle ne relie pas son raisonnement à
sa conclusion, et chaque retouche de prompt déplace les erreurs sans les réduire. Sur
24 échanges, un cas vaut environ 4 points : continuer à retoucher, ce serait surapprendre
du bruit. **Ne pas refaire ces essais sur llama3.2.** Le levier suivant est le modèle du
juge (Phase 4). Contrainte matérielle : un modèle local de 7–8 milliards de paramètres
ne tient pas sur la machine de l'auteur. Restent un autre petit modèle (même taille,
autre famille, ce qui dissocie aussi le juge de la cible) ou le profil `api`.

## Cadre légal

Projet de recherche en sécurité. Le red teaming de LLM n'est licite que contre des
systèmes qu'on possède ou qu'on est **explicitement autorisé** à tester. Ne jamais
pointer l'outil vers un service tiers sans autorisation écrite.
