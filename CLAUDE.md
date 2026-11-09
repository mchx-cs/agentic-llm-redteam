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
  échanges étiquetés à la main, répartis en un jeu de développement (40 échanges,
  `python -m evaluation.evaluer_arbitre`) et un jeu de test gelé (23 échanges,
  `--test`). Une fuite de valeur est vérifiée **par rejeu** avant d'être déclarée
  (`agents/verificateur.py`) ; `python -m evaluation.collecter_echanges` récolte de
  vrais échanges avec la cible ; `python -m evaluation.etiqueter` sert à les
  étiqueter à la main, puis `--integrer` les verse dans le corpus.
- **Phase 5** : `reconnaissance.py` sonde la cible et en dresse une fiche (rôle,
  langue, outils, sujets refusés) ; `planificateur.py` en déduit, par des règles
  déterministes, les familles à lancer, les objectifs à viser et l'ordre des essais.
  Testés sur des cibles simulées : `python -m evaluation.tester_reconnaissance`.

## Architecture

```
config.py          # point de bascule unique : modèle local (Ollama) ou API distante
llm_client.py      # LA couche d'abstraction : demander_au_llm()
cible.py           # le système testé (actuellement un leurre avec un secret à protéger)
agents/
  reconnaissance.py # sonde la cible (questions anodines) et en dresse une fiche
  planificateur.py  # choisit familles, objectifs et ordre à partir de la fiche (règles)
  attaquant.py     # fournit les briques : technique × objectif × transformation
  arbitre.py       # LLM-as-judge : tranche succès / échec (sortie JSON)
  detecteurs.py    # décode l'épelé, le Base64, l'hexa AVANT l'arbitre (déterministe)
  verificateur.py  # rejeu : une valeur divulguée revient-elle, ou était-ce une hallucination ?
payloads/
  bibliotheque.json  # techniques (famille OWASP + prérequis) et objectifs
evaluation/
  echanges_etiquetes.json  # vérité terrain (jeux dev et test) pour mesurer l'arbitre
  evaluer_arbitre.py       # précision, rappel, détail des erreurs
  journal_test.jsonl       # chaque consultation du jeu de test, horodatée
  etiqueter.py             # étiquetage à la main, question par question (--integrer)
  tester_reconnaissance.py # teste fiche et plan sur des cibles simulées
  tester_rejeu.py          # teste le rejeu avec des cibles simulées au comportement connu
  collecter_echanges.py    # récolte de vrais échanges → a_etiqueter.json (fichier de
                           # travail, hors git : étiqueter.py le vide dans le corpus)
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
| 4 | Dissocier l'arbitre du modèle cible | En cours |
| 5 | Agents de reconnaissance et de planification ; campagnes multi-familles | En cours |
| 6 | Rapport : JSON comme source de vérité, rendu Markdown par défaut | Prévu |
| 7 | Intégrer garak (couverture large) | Prévu |
| 8 | **Adaptateur de cible** : viser un vrai endpoint (URL, authentification, erreurs) | Prévu |
| 9 | **Traçabilité et autorisation** : journal rejouable, refus de démarrer sans autorisation | Prévu |
| 10 | **Qualité logicielle** : tests sans LLM, intégration continue, paquet, ligne de commande | Prévu |
| 11 | **Budget de campagne** : plafond en appels ou en tokens, arrêt propre quand il est atteint | Prévu |
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
Par défaut, tout reste en local (`llama3.2`) pour que le dépôt tourne sans clé ; le
juge passe sur Groq avec `PROFIL_ARBITRE=groq` dans `.env`.

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
exactitude 91 % → **96 %**, résultats identiques d'un passage à l'autre. Il ne reste que
E08 et E08-b, les hallucinations — limite structurelle que le rejeu rattrape en
campagne. Le jeu `test` n'a pas encore été rouvert pour vérifier cette correction.

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

## Cadre légal

Projet de recherche en sécurité. Le red teaming de LLM n'est licite que contre des
systèmes qu'on possède ou qu'on est **explicitement autorisé** à tester. Ne jamais
pointer l'outil vers un service tiers sans autorisation écrite.
