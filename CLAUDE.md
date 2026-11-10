# Contexte projet — agentic-llm-redteam

## De quoi il s'agit

Système multi-agents qui automatise le red teaming d'applications LLM : on fournit
un endpoint, on récupère une liste de vulnérabilités validées (prompt injection,
jailbreak, fuite de prompt système…), en suivant l'OWASP Top 10 for LLM Applications.

Projet personnel d'apprentissage **et** vitrine publique (dépôt public, lu par des
recruteurs). Les deux objectifs comptent : le code doit être propre et lisible, et
le README doit rester honnête sur l'état d'avancement.

## État actuel : Phase 0 terminée, Phases 1 et 2 démarrées

La campagne complète **reconnaissance → planification → attaque → jugement → rejeu**
tourne de bout en bout en local.

- **Phase 1** : la bibliothèque de payloads est structurée (technique × objectif ×
  transformation), mais seule la technique `controle` (anodine) a des modèles. Les
  familles OWASP sont déclarées vides : on les remplit une fois la technique
  pratiquée à la main.
- **Phase 2** : l'arbitre a des critères explicites, des exemples, une sortie JSON,
  une température à 0, raisonne avant de trancher, reçoit les passages décodés par
  `detecteurs.py` et s'abstient quand son verdict se contredit. Il est mesuré sur des
  échanges étiquetés à la main, répartis en un jeu de développement (57 échanges,
  `python -m evaluation.evaluer_arbitre`) et un jeu de test gelé (23 échanges,
  `--test`). Une fuite de valeur est vérifiée **par rejeu** avant d'être déclarée
  (`agents/verificateur.py`) ; `python -m evaluation.collecter_echanges` récolte de
  vrais échanges avec la cible ; `python -m evaluation.etiqueter` sert à les
  étiqueter à la main, puis `--integrer` les verse dans le corpus.
- **Phase 9** : `audit.py` refuse de démarrer contre une cible distante sans mandat
  valide (`autorisation.json`, hors git), et consigne chaque échange avec la cible dans
  une piste JSONL écrite au fil de l'eau.
- **Phase 11** : budget de campagne appliqué dans `llm_client` (`BUDGET_APPELS`,
  `BUDGET_TOKENS` dans `.env`). Atteindre son plafond lève `BudgetDepasse`, une
  exception distincte des pannes : la campagne s'arrête proprement, garde ses constats,
  et le rapport annonce en tête qu'elle a été **écourtée**.
- **Phase 10** : 133 tests `pytest` dans `tests/`, sans aucun appel LLM, lancés
  automatiquement sur GitHub Actions (Ubuntu et Windows, Python 3.10 et 3.13 —
  les quatre combinaisons passent).
  `pyproject.toml` empaquette le projet et expose la commande `redteam`.
- **Phase 6** : `rapport.py` produit `resultat.json` (source de vérité) et
  `rapport.md` (rendu), via `python main.py --rapport`. La gravité découle de règles
  déterministes, pas d'un LLM. La campagne va désormais au BOUT du plan et collecte
  tous les constats, au lieu de s'arrêter au premier.
- **Phase 5** : `reconnaissance.py` sonde la cible et en dresse une fiche (rôle,
  langue, outils, sujets refusés) ; `planificateur.py` en déduit, par des règles
  déterministes, les familles à lancer, les objectifs à viser et l'ordre des essais.
  Testés sur des cibles simulées : `python -m evaluation.tester_reconnaissance`.

## Architecture

```
config.py          # point de bascule unique : modèle local (Ollama) ou API distante
llm_client.py      # LA couche d'abstraction : demander_au_llm()
cibles/            # les systèmes testés — contrat commun : interroger(message) -> str
  leurre.py        # chatbot-jouet local avec un secret factice (défaut)
  mock.py          # déterministe, sans LLM : tests de bout en bout gratuits
  http.py          # un vrai endpoint, décrit dans .env (urllib, zéro dépendance)
agents/
  reconnaissance.py # sonde la cible (questions anodines) et en dresse une fiche
  planificateur.py  # choisit familles, objectifs et ordre à partir de la fiche (règles)
  attaquant.py     # fournit les briques : technique × objectif × transformation
  arbitre.py       # LLM-as-judge : tranche succès / échec (sortie JSON)
  detecteurs.py    # décode l'épelé, le Base64, l'hexa AVANT l'arbitre (déterministe)
  verificateur.py  # rejeu : une valeur divulguée revient-elle, ou était-ce une hallucination ?
payloads/
  bibliotheque.json  # techniques (famille OWASP + prérequis) et objectifs
  valider.py         # vérifie la bibliothèque — `python -m payloads.valider`
tests/             # pytest, AUCUN appel LLM : tourne en intégration continue
  test_detecteurs.py, test_verificateur.py, test_arbitre.py,
  test_planificateur.py, test_cibles.py, test_rapport.py,
  test_attaquant_et_config.py
evaluation/        # mesures qui ONT BESOIN d'un modèle : à lancer à la main
  echanges_etiquetes.json  # vérité terrain (jeux dev et test) pour mesurer l'arbitre
  evaluer_arbitre.py       # précision, rappel, détail des erreurs
  journal_test.jsonl       # chaque consultation du jeu de test, horodatée
  etiqueter.py             # étiquetage à la main, question par question (--integrer)
  tester_reconnaissance.py # teste fiche et plan sur des cibles simulées
  tester_rejeu.py          # teste le rejeu avec des cibles simulées au comportement connu
  collecter_echanges.py    # récolte de vrais échanges → a_etiqueter.json (fichier de
                           # travail, hors git : étiqueter.py le vide dans le corpus)
audit.py           # mandat exigé avant de démarrer + piste d'audit JSONL au fil de l'eau
rapport.py         # resultat.json (vérité) → rapport.md (rendu), gravité par règles
main.py            # orchestrateur : boucle de campagne avec budget d'essais
```

## Règles à respecter impérativement

**Aucun appel direct à un fournisseur de LLM.** Tout passe par `demander_au_llm()`
dans `llm_client.py`. C'est ce qui rend la bascule local ↔ API indolore (une ligne
dans `config.py`). Ne jamais coder en dur un appel Ollama ou OpenAI ailleurs.

Précision apportée en phase 8 : cette règle vise les modèles **que nous utilisons**
(arbitre, analyste, leurre), pour qu'ils restent interchangeables depuis `config.py`.
Elle ne vise PAS la cible attaquée, qui est un système tiers arbitraire — souvent une
application, pas un modèle nu. `cibles/http.py` l'appelle donc directement, en urllib,
et c'est volontaire.

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
| 3a | **Réordonner le plan selon la réponse de la cible** (déterministe, extension de la phase 5) | Prévu |
| 3b | Attaquant adaptatif multi-tours : évaluer PyRIT en remplacement de l'orchestrateur maison | Prévu |
| 4 | Dissocier l'arbitre du modèle cible | En cours |
| 5 | Agents de reconnaissance et de planification ; campagnes multi-familles | En cours |
| 6 | Rapport : JSON comme source de vérité, rendu Markdown par défaut | **Fait** |
| 7 | Intégrer garak (couverture large) | Prévu |
| 8 | **Adaptateur de cible** : viser un vrai endpoint (URL, authentification, erreurs) | **Fait** |
| 9 | **Traçabilité et autorisation** : journal rejouable, refus de démarrer sans autorisation | **Fait** |
| 10 | **Qualité logicielle** : tests sans LLM, intégration continue, paquet, ligne de commande | **Fait** |
| 11 | **Budget de campagne** : plafond en appels ou en tokens, arrêt propre quand il est atteint | **Fait** |
| 12 | **Démonstration reproductible** : cible vulnérable livrée, détection en une commande, enregistrement asciinema au README | Prévu |

Les phases 8 à 11 ont été ajoutées le 2026-11-09 : ce sont les manques qui bloquent le
passage en production, et qu'une feuille de route centrée sur les attaques laissait
invisibles.

**Deux barres à ne pas confondre.**
- *Utilisable sur ses propres systèmes* : phases 1, 6 et 8. L'outil vise une vraie
  cible, trouve de vraies failles et produit un rapport lisible. C'est aussi ce qui se
  démontre le mieux en vitrine.
- *Utilisable en mission* : il faut y ajouter 2 (critères élargis), 9, 10 et 11. Un
  rapport de pentest qui contient une fausse faille coûte la crédibilité de toute la
  mission : 9 et 11 sont les moins visibles et les plus sous-estimés.

**Ordre imposé par les dépendances**, à ne pas prendre à l'envers :
8 (vraie cible) → 1 et 7 (payloads) → 2 (critères, une fois la cible enrichie) →
3 (multi-tours) → 6 (rapport). 9, 10 et 11 peuvent avancer en parallèle.
La phase 3 est la plus coûteuse, et la seule où PyRIT fait le gros du travail.

## Décisions prises et leur raison

**L'arbitre ne connaît pas le secret de la cible.** Il juge uniquement d'après
l'échange visible, comme en test boîte noire réel. C'est ce qui rend sa tâche
difficile — et c'est le cœur technique du projet.

**Arbitre et cible peuvent tourner sur des modèles différents.** Un juge identique à
sa cible partage ses angles morts (Phase 4). `PROFIL_ARBITRE` est séparé de
`PROFIL_ACTIF` dans `config.py`, et `demander_au_llm()` accepte un paramètre `profil`.
Les deux se règlent dans `.env` (hors git) : `PROFIL_ACTIF` pour la cible et les appels
sans profil, `PROFIL_ARBITRE` pour le juge. Personne n'a besoin de modifier un fichier
suivi par git pour changer de fournisseur, et un nom de profil inconnu échoue dès
l'import, avec la liste des profils valides. Par défaut tout reste en local
(`llama3.2`), pour que le dépôt tourne sans clé.

**Ne pas automatiser ce qu'on ne sait pas faire à la main.** Les vraies attaques
attendent que l'auteur ait terminé le path AI Security de TryHackMe. Un agent dont
on ne sait pas juger les hallucinations est inutilisable.

**PyRIT arrive en Phase 3, pas en Phase 7.** La boucle maison reproduit en miniature
les briques de PyRIT : `cibles/` correspond à ses *targets*, `main.py` à un
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
- **Budget distinct.** `BUDGET_RECONNAISSANCE` (reconnaissance.py) est séparé de
  `MAX_ESSAIS` : sonder coûte des requêtes et peut déjà éveiller les défenses.

Réalisé le 2026-11-09 : une sonde par champ de la fiche, des prérequis déclarés dans
`bibliotheque.json` (`outils`, `secret`, `consignes`) évalués par les règles de
`PREREQUIS`, et un plan qui dit aussi ce qu'il a **écarté et pourquoi** — un outil qui
tait ce qu'il n'a pas testé donne une fausse impression de couverture. La fiche garde
un champ `indices` (les citations qui justifient chaque fait) pour rester vérifiable.
Une analyse illisible donne une fiche vide, jamais une fiche inventée.

Limite observée dès le premier essai : contre le leurre local, la reconnaissance
remonte les refus *génériques* du modèle (« conseils juridiques », « activités
illégales ») plutôt que le secret du leurre, que la cible ne mentionne pas
spontanément. La fiche est exacte, mais les objectifs qu'on en déduit sont génériques.
Une cible qui ne déclare pas ce qu'elle protège se reconnaît mal : c'est la limite
d'une reconnaissance purement déclarative.

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

**Le changement de modèle du juge a levé ce plafond (2026-10-30).** Même prompt, juge
`openai/gpt-oss-120b` via l'offre gratuite de Groq :
- jeu `dev` : précision 86 %, rappel 100 %, exactitude 92 % (contre 75 / 50 / 67 %) ;
- jeu `test`, consulté pour ce changement de modèle : précision 89 %, rappel 100 %,
  exactitude 93 % (contre 100 / 50 / 73 %).

Les seules erreurs restantes sont les hallucinations de la cible (E08, E08-b, T10),
limite structurelle du juge aveugle : à traiter par le rejeu, pas par le prompt.
Contraintes de cet usage :
- **Groq sert de juge, jamais de cible d'attaques réelles** : les conditions
  d'utilisation interdisent de contourner les garde-fous du fournisseur.
- **Données fictives uniquement** sur une offre gratuite.
- La clé est dans `.env` (ignoré par git), jamais dans le code, le chat ou un commit.
- L'offre gratuite plafonne à 8 000 tokens par minute ET 200 000 par jour. Le profil
  `groq` relance automatiquement sur la limite par minute (au plus 8 fois) ; contre la
  limite quotidienne, relancer ne sert à rien, et `llm_client` renvoie alors un message
  qui propose d'attendre ou de repasser l'arbitre en local. Une évaluation complète
  (`dev` 46 + `test` 23) coûte une bonne part du quota : enchaîner plusieurs réglages
  dans la journée l'épuise.

**Les hallucinations de la cible se traitent par rejeu, pas par le juge.** Un juge
aveugle ne peut pas distinguer un vrai secret d'un secret inventé : l'information
n'est pas dans l'échange. En revanche, un vrai secret revient identique d'un essai à
l'autre, alors qu'une hallucination change. Quand l'arbitre voit une divulgation, il
extrait la valeur (champ `valeur`) et `verificateur.py` rejoue le même payload
`NB_REJEUX` fois (boucle bornée) : la valeur revient → *confirmée* ; seulement
d'autres valeurs → *hallucination probable*, la campagne continue ; les deux →
*contradictoire* ; plus rien → *inconcluant*. Limites : il faut une cible avec de
l'aléa (une cible déterministe répète sa propre hallucination), et seules les valeurs
d'un seul mot sont comparées (une fuite de prompt système est paraphrasée).

**Les échanges réels s'étiquettent à l'aveugle.** `collecter_echanges.py` n'enregistre
pas l'avis de l'arbitre : le voir influencerait l'étiquette humaine, et on mesurerait
le juge contre lui-même. Les prompts viennent uniquement de la bibliothèque de payloads,
donc seulement de techniques pratiquées à la main.

**Angle mort corrigé : la mention SPONTANÉE d'un secret (2026-11-09).**
Repéré sur le jeu de test (R07-2) : la cible glisse « le mot de passe secret restera
secret » dans une présentation, et le juge y voyait une divulgation. Sa consigne
couvrait ce cas, mais le formulait comme un REFUS — E03 et T03 passaient parce que ce
sont des refus ; une mention spontanée n'en est pas un.

Corrigé sans jamais regarder le jeu de test : six cas écrits à la main ont été ajoutés
au jeu `dev` (D13 mention spontanée sans la valeur → non ; D14 même ton mais la valeur
sort → oui ; D15 récitation spontanée des consignes → oui), puis le critère a été
réécrit face à eux seuls. D14 était indispensable : sans lui, on apprenait au juge que
« mention spontanée = pas une faille », et il aurait laissé passer une vraie fuite dite
sur le même ton.

Trois réglages successifs ont été nécessaires, chacun révélant la limite du précédent :
1. critère porté sur ce que la réponse CONTIENT, et non sur le fait qu'elle refuse →
   D13 et D15 corrigés, mais E09-b (récitation de consignes) devenait un faux négatif ;
2. ajout de « énumère ce qu'on lui a demandé » → E09-b corrigé, mais R04-2, une simple
   description de mission, devenait un faux positif ;
3. resserrage sur le vrai discriminant : **une interdiction portant sur une information
   précise**. Décrire son rôle en termes généraux n'est pas énoncer une consigne.

Jeu `dev` (46 échanges) : précision 83 % → **89 %**, rappel 94 % → **100 %**,
exactitude 91 % → **96 %**. Il ne reste que E08 et E08-b, les hallucinations — limite
structurelle que le rejeu rattrape en campagne.

**Validé sur le jeu de test le 2026-11-10**, sur des cas jamais regardés pendant les
réglages : précision 80 % → **89 %**, exactitude 91 % → **96 %**, et R07-2, le cas qui
avait révélé l'angle mort, est désormais correctement classé. Seul T10 (hallucination)
subsiste. La méthode a donc tenu : corriger sur `dev` sans jamais ouvrir `test`
produit bien une amélioration qui généralise.

**Ce que les mesures de l'arbitre prouvent — et ce qu'elles ne prouvent pas (2026-11-09).**
Les 96 % d'exactitude sur le jeu `dev` ne disent **rien** de la couverture des
vulnérabilités : le corpus mesure le JUGE, pas l'étendue des attaques. La seule
affirmation qu'il soutient est : *l'arbitre reconnaît bien les fuites de secret et les
injections directes, en un seul tour, en français.*

Sur les 69 échanges (29 contrôles, 24 vraies failles), 3 familles OWASP sur 10 sont
touchées : LLM02 Sensitive Information Disclosure (13 échanges, cinq formes de fuite),
LLM07 System Prompt Leakage (5) et LLM01 Prompt Injection (3, seulement `obeissance`).
LLM03, LLM04, LLM05, LLM06, LLM08, LLM09 et LLM10 : aucune couverture.

Angles morts de forme, plus gênants que les familles manquantes :
- **tout est en un seul tour** — aucun échange n'a d'historique, et la consigne de
  l'arbitre ne prévoit même pas ce format ;
- **tout est en français** sauf T02 et T05 ;
- **aucune injection indirecte** : tous les payloads viennent de l'utilisateur, jamais
  d'un document, d'une page ou d'une sortie d'outil ;
- **aucun contenu nuisible** : on ne teste que la fuite et l'obéissance.

**Le plafond est dans le juge, pas dans les données.** L'arbitre ne connaît que deux
critères, `divulgation` et `obeissance`. Soumis à un abus d'outils ou à un contenu
nuisible, il répondrait `aucun` — non par erreur, mais faute de case pour le dire.
Agrandir le corpus sans élargir d'abord les critères ne servirait donc à rien.

Et la cible impose sa propre limite : sans outils, sans RAG et sans application autour,
LLM05, LLM06 et LLM08 ne sont pas seulement non testés, ils sont **intestables**.

Ordre à respecter pour étendre la couverture : enrichir la cible → élargir les critères
de l'arbitre → agrandir le corpus → ajouter les payloads. Prendre ces étapes dans
l'autre sens produirait des mesures qui ne veulent rien dire.

**Phase 6 : le JSON est la source de vérité, le rapport n'en est qu'un rendu.**
La campagne produit d'abord un `resultat.json` structuré ; les formats lisibles en
découlent, comme `bibliotheque.json` sépare déjà les données du code. Ajouter un format
devient alors une fonction de plus, jamais une refonte :

```
campagne → resultat.json
             ├→ rapport.md    (par défaut)
             ├→ rapport.html  (si les rapports deviennent trop longs à lire à plat)
             └→ rapport.pdf   (via pandoc, le jour d'une mission)
```

**Markdown par défaut**, pour deux raisons décisives ici :
- **GitHub le rend nativement.** Un rapport d'exemple commité s'affiche directement
  dans le navigateur du visiteur ; un `.html` commité s'afficherait en code source.
  C'est tout le bénéfice vitrine du HTML, sans écrire une ligne de mise en forme.
- **Il se compare.** Lancer une campagne, corriger la cible, relancer : un `git diff`
  entre les deux rapports montre exactement ce qui a changé. Impossible avec du HTML
  mis en forme ou un PDF binaire.

Le PDF est bien le format attendu en mission réelle, mais il se fabrique depuis le
Markdown avec `pandoc` le jour venu : inutile de concevoir pour ça aujourd'hui. Le
rapport doit aussi dire **ce qui n'a PAS été testé** — le planificateur consigne déjà
les familles écartées et leur motif.

**Pas d'interface web.** Les outils offensifs du domaine (garak, PyRIT, nmap) sont en
ligne de commande, et c'est ce qu'attend un lecteur du dépôt. Une interface ne
s'automatise pas (il faudrait une API dessous, donc le travail deux fois), n'avance
aucune phase, et serait elle-même une surface d'attaque sur un outil de red teaming.
Elle ne deviendrait légitime que si le projet devenait un service multi-utilisateurs,
ce qui n'est pas l'objectif.

**Phase 12 : rendre la démonstration reproductible.** Un dépôt qu'on peut essayer en
trente secondes se démarque bien plus qu'un dépôt qu'on regarde. Trois pièces, par
ordre de valeur :
1. **Une cible volontairement vulnérable livrée avec le projet**, pour que n'importe qui
   reproduise une détection en une commande, sans clé ni configuration. C'est aussi la
   cible de référence des tests de bout en bout.
2. **Un enregistrement asciinema** d'une campagne complète, intégré au README : il
   montre le déroulé reconnaissance → plan → attaque → verdict → rejeu, ce qu'aucune
   capture d'écran ne rend.
3. **Un rapport d'exemple commité**, rendu par GitHub.

À faire après la phase 8 (adaptateur de cible) et la phase 6 : démontrer une campagne
qui ne trouve que des payloads de contrôle n'aurait aucun intérêt.

**Phase 12 : comment la cible vulnérable livrée doit fonctionner.** Deux cibles, deux
métiers — les confondre ferait rater l'un des deux.
- **Une cible déterministe, sans LLM** : du Python qui imite un chatbot (il refuse la
  plupart des demandes, fuite sur certains motifs). Zéro dépendance, instantanée,
  toujours le même résultat : c'est elle qui rend possibles les tests de bout en bout
  de la phase 10, sans brûler de quota.
- **Une cible adossée à un LLM, volontairement mal protégée** : même modèle local que
  le reste, mais avec un prompt système bavard qui cède sous une injection directe.
  Elle fuite RÉELLEMENT, parce qu'elle est mal défendue, pas parce qu'on l'a scriptée.
  C'est elle qui sert à la démonstration : une cible scriptée qui renvoie le secret dès
  qu'elle voit « ignore tes instructions » ne prouverait rien sur la chaîne d'agents,
  seulement que le `if` fonctionne.

**Elle se branche par l'adaptateur de la phase 8**, comme n'importe quelle autre cible
(`--cible demo`, `--cible mock`, `--cible <url>`) : la cible livrée n'est qu'un
adaptateur qui pointe vers un leurre local.

**Niveaux de défense réglables** (idée empruntée à DVWA) : 1 = garde-fou quasi absent,
2 = consigne ferme, 3 = consigne plus filtre de sortie. Ça transforme la cible en
instrument de mesure — « à partir de quel niveau l'outil ne trouve plus ? » devient une
métrique du projet, à côté de la précision de l'arbitre. Elle doit aussi exposer
plusieurs familles : un prompt système qu'elle récite, un outil factice qu'on peut lui
faire appeler, un document qu'elle lit. C'est précisément ce qui débloquera
l'élargissement des critères de l'arbitre, aujourd'hui impossible faute de cible
capable de ces comportements.

**Le point délicat : c'est probabiliste.** Un vrai LLM mal protégé ne cède pas à tous
les coups, donc la démonstration peut échouer chez le visiteur. Trois réponses : le
niveau 1 est assez faible pour que la détection soit quasi certaine dans la limite de
`MAX_ESSAIS` ; l'enregistrement asciinema montre une campagne réussie à qui veut juste
regarder ; et un échec occasionnel illustre la thèse du projet (« la même injection
réussit une fois sur trois ») au lieu de la contredire.

**« En une commande » veut dire : aucune clé, aucun compte, aucune configuration
au-delà de ce que le README demande déjà.** Ollama et `llama3.2` restent nécessaires,
c'est le socle du projet ; la cible déterministe, elle, tourne vraiment sans rien.

**Secrets factices uniquement** (type `TOPSECRET42`). Livrer une cible vulnérable dans
un dépôt public est banal et sans risque ; y laisser une vraie valeur ne l'est pas.

**Ce que coûte réellement une API payante (mesuré le 2026-11-09).** Les messages
d'erreur 429 de Groq donnaient le nombre exact de tokens par requête (`Requested 1430`,
`1553`, `1722`) : un appel à l'arbitre coûte **~1 500 tokens**, dont ~1 400 en entrée
(la consigne et ses cinq exemples) et ~100 en sortie (le JSON).

| Opération | Appels | Tokens |
|---|---|---|
| Évaluation jeu `dev` (46 échanges) | 46 | ~70 000 |
| Évaluation jeu `test` (23 échanges) | 23 | ~35 000 |
| Une campagne (reconnaissance + 3 essais + rejeu) | ~10 | ~12 000 |
| `tester_rejeu` | 20 | ~30 000 |
| `tester_reconnaissance` | 3 | ~7 500 |

Une évaluation `dev` revient à ~0,01 $ sur un modèle d'entrée de gamme, ~0,18 $ en
milieu de gamme, ~0,90 $ en haut de gamme. **Toute la séance du 2026-11-09** — trois
évaluations `dev`, une `test`, plus les réglages — a épuisé le quota gratuit de
200 000 tokens, soit **~0,56 $** sur une API payante de milieu de gamme.

**Donc le risque n'est pas la facture, c'est la boucle qui s'emballe.** À l'échelle
actuelle le coût est négligeable ; la phase 11 reste justifiée comme COUPE-CIRCUIT
(agent adaptatif sans garde-fou, relance en cascade, rejeu dans un rejeu), pas comme
économie. Le coût deviendra réel ailleurs : en **phase 3** (multi-tours — chaque tour
reporte tout l'historique, la croissance est quadratique, pas linéaire) et en
**phase 7** (garak — des centaines de sondes × plusieurs tentatives, de l'ordre de
quelques dizaines d'euros par campagne complète). Les prix bougent vite : vérifier les
pages officielles avant de budgéter.

**Choix du fournisseur : la restriction porte sur le RÔLE, pas sur le fournisseur.**
- *Arbitre et analyste* : **n'importe quelle API payante convient.** On lui demande
  d'analyser du texte, c'est un usage ordinaire. Rien de particulier à vérifier.
- *Cible* : trois cas distincts. (1) Le leurre local — aucun problème. (2) Une
  **application cliente** bâtie sur une API : on teste SON prompt système et SES
  garde-fous, avec son autorisation écrite et sur son compte — légitime, on n'attaque
  pas le fournisseur mais la couche construite par le client. (3) Le **modèle brut**
  d'un fournisseur qu'on cherche à faire déraper : hors du cadre contractuel, chez
  pratiquement tous les fournisseurs. La porte d'entrée légitime existe : leurs
  programmes officiels de red teaming et de bug bounty.

Deux contraintes qui portent non sur le fournisseur mais sur ce qu'on lui envoie :
- **les données du client** quittent son périmètre si l'arbitre tourne sur une API
  distante — à prévoir au contrat (confidentialité, RGPD) ;
- **les offres gratuites sont disqualifiées en mission** : plusieurs fournisseurs
  s'autorisent à entraîner leurs modèles sur les requêtes gratuites. Sans importance
  pour le leurre à secrets factices, rédhibitoire pour des données clientes.

**Élargissement à l'anglais : préparé le 2026-11-09, PAS ENCORE MESURÉ.**
Deux questions distinctes se cachent derrière « faut-il sortir du français ».

*A — L'arbitre tient-il dans une autre langue ?* C'est une question de CORRECTION, pas
de couverture : une réponse négative invaliderait l'outil sur toute cible non
francophone. Les seules preuves étaient T02 et T05, deux échanges anglais du jeu gelé,
et le jeu `dev` n'en contenait aucun. Onze traductions anglaises ont donc été ajoutées
au jeu `dev` (une par catégorie de piège : E01-en, E03-en … E12-en), ce qui le porte à
57 échanges.

Trois règles ont guidé leur ajout :
- **L'étiquette est héritée, pas réinventée.** Une traduction fidèle teste le même
  piège : `attendu` est repris de l'original, que l'auteur avait déjà validé.
- **Même groupe que l'original.** Une traduction est une reformulation — exactement ce
  que la notion de groupe protège. Elle reste donc en `dev`, et le jeu `test` ne peut
  pas se retrouver à contenir la traduction d'un cas sur lequel on a réglé l'arbitre.
- **La consigne de l'arbitre n'a PAS été touchée.** Mesurer d'abord, corriger ensuite :
  retoucher le prompt avant la mesure empêcherait de savoir si le juge était déjà
  robuste ou si c'est la retouche qui l'a sauvé.

*Déjà acquis sans quota :* `detecteurs.py` est indépendant de la langue (il travaille
sur des caractères, pas des mots) — vérifié sur de l'épelé, du Base64 et de l'hexa en
anglais, sans régression sur les faux positifs.

*Reste à faire :* lancer la mesure sur les 11 cas anglais (~17 000 tokens), puis
décider. Question ouverte et mesurable si le juge dégrade : **faut-il basculer la
consigne de l'arbitre en anglais ?** Les modèles y sont généralement meilleurs, et le
juge doit couvrir des cibles de toutes langues — mais ça se compare sur le jeu `dev`
au lieu de se deviner. La convention française du projet (code, commentaires, commits)
n'est pas en cause : elle ne concerne pas la langue des échanges jugés.

*B — Faut-il des payloads multilingues ?* Oui, mais **pas sous forme de corpus
séparé**. Traduire un payload dans une langue peu représentée à l'entraînement affaiblit
des garde-fous surtout alignés en anglais : c'est donc une **transformation**, au même
titre que le Base64 ou l'épellation, et l'axe existe déjà dans `attaquant.py`. Une
seule fonction multiplie toutes les techniques, au lieu d'ajouter des payloads un par
un — et PyRIT fournit ce convertisseur, donc la phase 3 l'apporte presque gratuitement.

**Une réponse tronquée ne doit jamais passer pour une réponse complète (2026-11-09).**
`llm_client` ne lisait que le contenu de la réponse, jamais `finish_reason`. Scénario
qui fait mal : la cible commence à lâcher le secret, atteint son plafond de sortie, se
fait couper — l'arbitre voit une réponse incomplète et conclut « pas de faille ». C'est
un **faux négatif silencieux**, la pire erreur pour un outil de sécurité, puisque la
campagne conclut « aucune faille » à tort et que rien ne le signale.

Corrigé par un **journal des appels** dans `llm_client`, qui est le seul point de
passage du projet vers les LLM : nombre d'appels, tokens consommés, et liste des
réponses tronquées (`journal()`, `reinitialiser_journal()`). `main.py` avertit deux
fois — à l'essai concerné, et au bilan de campagne. Un délai d'attente par défaut
(60 s, réglable par `delai` dans le profil) a été ajouté au passage : sans lui, une
cible qui ne répond jamais bloquerait la campagne indéfiniment.

Ce journal est volontairement la brique de base de deux phases à venir : il compte déjà
les tokens (**phase 11**, budget) et trace chaque appel (**phase 9**, traçabilité).

**Sur une cible réelle, la limite de tokens n'est pas la contrainte qu'on croit.**
À ~1 500 tokens par jugement, l'offre gratuite de Groq donne ~130 jugements par jour.
Comme les attaques sont probabilistes, affirmer qu'une cible RÉSISTE à une technique
demande une trentaine d'essais : une campagne sur dix techniques, c'est ~300 jugements,
deux à trois fois le quota gratuit. Mais ces 300 jugements coûtent ~1,30 $ en milieu de
gamme : le quota gratuit est limitant, une API payante le règle pour le prix d'un café.
Les vraies contraintes sur cible réelle sont ailleurs : le **débit autorisé par la
cible** (à découvrir en reconnaissance), la **fenêtre de test contractuelle** (marteler
une production ressemble à un déni de service) et le **coût pour le client** si sa
cible est facturée à l'usage.

**L'arbitre n'est pas déterministe, même à température 0 (mesuré le 2026-11-10).**
Découvert par accident : E10-b échouait sur un passage du jeu `dev` alors qu'il passait
aux deux précédents, sans qu'on ait rien changé. Cinq appels successifs sur ce cas
donnent `[True, True, True, True, False]`. Le paramètre `seed` n'y change rien — testé,
il donne même `[False, False, True, True, False, True]`. C'est une propriété du modèle
(gpt-oss-120b, mélange d'experts : le routage et le traitement par lots varient), pas
un réglage oublié.

Deux conséquences, à ne pas confondre :
- **Sur la MESURE** : un cas sur ~57 peut basculer, soit environ ±2 points. Les écarts
  fins (88 % contre 89 %) sont du bruit et ne doivent pas être interprétés. Les grands
  écarts (rappel 50 % → 100 %) restent, eux, parfaitement réels.
- **Sur les VERDICTS de campagne** : une faille qui apparaît ou disparaît selon le
  tirage n'a rien à faire dans un rapport.

Corrigé pour les campagnes par `juger_par_vote()` : le même échange est jugé `NB_VOTES`
fois (3), la majorité l'emporte, et sans majorité nette le verdict devient `None`,
« à revoir par un humain ». Le désaccord est lui-même un signal : il désigne les cas
limites. Vérifié sur E10-b, qui donne `[True, True, False]` et tranche correctement.

Deux choix délibérés :
- **L'évaluation appelle `juger()` directement**, sans vote : elle doit mesurer le juge
  tel qu'il est, pas une version lissée. Voter y masquerait l'instabilité au lieu de la
  révéler, et triplerait le coût de chaque évaluation.
- **Le rejeu aussi** : il interroge déjà la cible plusieurs fois, ce qui lisse le bruit.
  Voter en plus coûterait neuf appels là où trois suffisent.

**« Attaquant adaptatif » recouvre trois niveaux, pas un (consigné le 2026-11-10).**
Les confondre fait sous-estimer la phase 3 d'un ordre de grandeur.

| Niveau | Ce que ça fait | Coût | Où |
|---|---|---|---|
| **A** | l'essai échoue, on passe au suivant du plan | **déjà fait** | `main.py` |
| **B** | réordonner le plan d'après la réponse de la cible | faible | phase 3a |
| **C** | l'attaquant lit la réponse et rédige le tour suivant, avec historique | élevé | phase 3b |

**Le niveau B mérite d'arriver tôt.** C'est de la logique déterministe qui réutilise le
planificateur : si la cible refuse en nommant ce qu'elle protège, on remonte la famille
`divulgation` ; si elle n'a aucun outil, on écarte `abus-outils`. C'est l'idée de la
fiche cible appliquée PENDANT la campagne au lieu d'avant, et c'est une valeur ajoutée
propre au projet — PyRIT ne la couvre pas. Condition : que la bibliothèque ait du
contenu, sinon il n'y a rien à réordonner.

**Le coût caché du niveau C n'est pas l'orchestrateur, c'est l'ARBITRE.** Sa consigne
attend aujourd'hui exactement deux lignes (« Utilisateur : X », « Chatbot : Y ») et ne
prévoit aucun historique ; les 80 échanges du corpus sont tous en un seul tour. Le
multi-tours impose donc de réécrire le format et les critères du juge, de **reconstruire
un corpus de conversations étiquetées à la main** (par l'auteur, comme toujours), et de
tout remesurer — les 96 % actuels ne voudront plus rien dire sur ce format. PyRIT
fournit l'orchestration, pas le juge : ce travail de corpus reste à faire quoi qu'il
arrive, et c'est la partie la plus longue.

**Pourquoi la phase 3 vient après les payloads** : on ne peut pas adapter ce qu'on n'a
pas (avec seulement des payloads de contrôle, il n'y a rien à reformuler), et surtout on
ne pourrait pas mesurer le gain. La question qui compte — « l'adaptatif trouve-t-il plus
de failles que le non-adaptatif, à budget égal ? » — exige de vrais payloads et une
cible qui cède parfois.

**Deux sortes de vérifications, à ne jamais mélanger (phase 10, 2026-11-10).**
- `tests/` : **pytest, aucun appel à un modèle.** Rapides (4 s), gratuits, lancés à
  chaque poussée par GitHub Actions. Ils vérifient ce qui doit être vrai quoi qu'un
  modèle réponde : détecteurs, logique du rejeu, lecture du verdict et arithmétique du
  vote, règles du planificateur, adaptateurs de cible, gravités du rapport.
- `evaluation/` : les mesures qui **ont besoin d'un modèle** (`evaluer_arbitre`,
  `tester_rejeu`, `tester_reconnaissance`). Elles coûtent du quota et ne peuvent pas
  tourner en intégration continue. Elles se lancent à la main.

Conséquence pratique : un test qui appellerait un modèle n'a rien à faire dans
`tests/` — il échouerait en intégration continue, où il n'y a ni Ollama ni clé.

Windows figure dans la matrice d'intégration continue parce que c'est la plateforme de
développement du projet : chemins et encodage s'y comportent autrement, et une
régression propre à Windows passerait inaperçue autrement.

**Les tests ont immédiatement trouvé un bogue réel** : `est_verifiable("   ")` renvoyait
`True`. Une valeur faite d'espaces passait donc pour un secret vérifiable, et
`normaliser` la réduisait à une chaîne vide, qui se compare à n'importe quoi — soit une
fuite « confirmée » à tort. Corrigé dans `verificateur.py`.

**La dépendance unique tient toujours.** `requirements.txt` ne contient que `openai` ;
`pytest` vit dans `requirements-dev.txt`. La promesse porte sur l'exécution, pas sur
l'outillage de développement.

**Le budget est un coupe-circuit, et son arrêt doit être PROPRE (phase 11, 2026-11-10).**
Appliqué dans `llm_client`, seul point de passage vers les modèles : il attrape donc
tout — juge, analyste, cible, rejeu et votes compris.

- **`BudgetDepasse` est une exception distincte des pannes.** Atteindre son plafond est
  un arrêt normal, pas une erreur. Sans cette distinction, l'orchestrateur ne pourrait
  pas conclure « écourtée » plutôt que « plantée ».
- **Le budget est armé par l'ORCHESTRATEUR**, via `reinitialiser_journal(appels,
  tokens)`, pas par `llm_client` lui-même. Les scripts d'évaluation consomment bien
  plus qu'une campagne (57 jugements pour le seul jeu `dev`) et n'ont aucune raison
  d'être coupés au milieu d'une mesure : sans plafond, rien n'est limité.
- **Le plafond en tokens peut être dépassé d'un appel, jamais plus.** Le coût d'un
  appel ne se connaît qu'une fois celui-ci terminé : on vérifie donc ce qui a déjà été
  consommé. C'est assumé et testé.
- **Une campagne écourtée ne se présente JAMAIS comme terminée.** Statut
  `budget_epuise`, avertissement en tête du rapport, et surtout la section Couverture
  se dénonce elle-même : « la couverture ci-dessous est incomplète, y compris pour les
  familles dites testées ». Sans ça, un « aucun constat » obtenu après trois essais sur
  douze laisserait croire à une cible sûre.

Défauts larges mais FINIS (200 appels, 500 000 tokens) : une campagne normale en
consomme ~10 et ~12 000, donc le plafond ne gêne jamais l'usage courant et n'arrête que
ce qui s'emballe. `BUDGET_APPELS=0` désarme, à n'utiliser qu'en connaissance de cause.

**Phase 9 : le cadre légal passe du texte au code (2026-11-10).** Le « Cadre légal »
ci-dessous n'était qu'une phrase ; `audit.py` en fait une condition d'exécution.

**L'exigence suit le risque.** Le leurre, la cible déterministe et tout ce qui tourne
sur `localhost` / `127.0.0.1` ne demandent rien : ils sont à vous. Une cible distante
exige un mandat. Imposer le même formulaire aux deux apprendrait surtout à cliquer sans
lire, et le dépôt cesserait d'être essayable en une commande.

**Le mandat n'est pas une case à cocher** : deux contrôles lui donnent sa valeur.
- *La cible doit être couverte.* Un mandat pour `chatbot.client.fr` ne vaut pas pour
  `autre-client.fr` — c'est ce qui empêche de le réutiliser ailleurs.
- *La fenêtre doit être courante.* Tester hors des dates convenues n'est pas couvert.

Un refus sort en code 2 avec une consigne (« copie autorisation.example.json… »), pas
une trace d'exécution. `autorisation.json` est dans `.gitignore` : il nomme un vrai
client. Le modèle à remplir, lui, est commité.

**La piste d'audit s'écrit au fil de l'eau, et c'est tout l'intérêt.** Un JSONL vidé
après chaque ligne : si la campagne tombe, on garde la trace de ce qui a DÉJÀ été
envoyé — précisément le moment où on en a besoin. Elle consigne le mandat en ouverture,
chaque échange avec la cible (reconnaissance, attaque, rejeu), chaque verdict avec ses
votes, puis la consommation en clôture. Elle est écrite **toujours**, même sans
`--rapport` : c'est une trace, pas un livrable optionnel.

Deux choix d'implémentation :
- **On trace les échanges avec la CIBLE, pas nos appels au juge.** C'est ce qu'on doit
  pouvoir montrer si la campagne est contestée ; le reste est compté par `llm_client`.
- **`piste.tracer(phase, cible)` enveloppe la cible** au lieu d'instrumenter chaque
  agent. La cible reste une fonction `message -> str`, et `reconnaissance.py` comme
  `verificateur.py` ignorent qu'elle est tracée — le contrat de la phase 8 tient.

Enfin, le rapport cite le mandat sous lequel il a été produit : en mission, un rapport
qui ne le dit pas n'est pas opposable.

**La bibliothèque se valide, parce que ses erreurs sont SILENCIEUSES (2026-11-10).**
`payloads/bibliotheque.json` est un fichier de données, édité à la main ou alimenté
depuis l'extérieur. Aucune de ses fautes ne lève d'exception — elles produisent une
campagne qui ne teste pas ce qu'on croit :
- un modèle sans `{objectif}` enverrait toujours le même texte ;
- un prérequis mal orthographié serait **ignoré en silence** par le planificateur, et
  la technique partirait contre des cibles où elle n'a aucun sens ;
- un identifiant en double rendrait les rapports illisibles.

D'où `python -m payloads.valider`, à lancer après chaque modification. Sortie en code 1
si quelque chose cloche, donc enchaînable en script. Erreurs et avertissements sont
distingués : une technique sans modèle est un simple avertissement, puisque c'est
l'état normal des familles pas encore remplies.

Un test vérifie que la bibliothèque DU DÉPÔT est valide : une faute introduite en
l'éditant fait échouer l'intégration continue, pas une campagne.

## Cadre légal

Projet de recherche en sécurité. Le red teaming de LLM n'est licite que contre des
systèmes qu'on possède ou qu'on est **explicitement autorisé** à tester. Ne jamais
pointer l'outil vers un service tiers sans autorisation écrite.
