# Contexte projet — agentic-llm-redteam

## De quoi il s'agit

Système multi-agents qui automatise le red teaming d'applications LLM : on fournit
un endpoint, on récupère une liste de vulnérabilités validées (prompt injection,
jailbreak, fuite de prompt système…), en suivant l'OWASP Top 10 for LLM Applications.

Projet personnel d'apprentissage **et** vitrine publique (dépôt public, lu par des
recruteurs). Les deux objectifs comptent : le code doit être propre et lisible, et
le README doit rester honnête sur l'état d'avancement.

## État actuel : Phase 0 terminée

La boucle complète **attaquant → cible → arbitre** tourne de bout en bout en local.
Les payloads d'attaque sont volontairement **anodins** (messages de test inoffensifs) :
c'est la tuyauterie qui est validée, pas encore les attaques réelles.

## Architecture

```
config.py          # point de bascule unique : modèle local (Ollama) ou API distante
llm_client.py      # LA couche d'abstraction : demander_au_llm()
cible.py           # le système testé (actuellement un leurre avec un secret à protéger)
agents/
  attaquant.py     # génère les tentatives d'attaque
  arbitre.py       # LLM-as-judge : tranche succès / échec
main.py            # orchestrateur : boucle de campagne avec budget d'essais
```

## Règles à respecter impérativement

**Aucun appel direct à un fournisseur de LLM.** Tout passe par `demander_au_llm()`
dans `llm_client.py`. C'est ce qui rend la bascule local ↔ API indolore (une ligne
dans `config.py`). Ne jamais coder en dur un appel Ollama ou OpenAI ailleurs.

**Toujours borner les boucles.** Les attaques sont probabilistes : un agent adaptatif
boucle à l'infini sans garde-fou. `MAX_ESSAIS` dans `main.py` borne chaque campagne.
Toute nouvelle boucle doit avoir sa propre limite.

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
| 2 | Fiabilité de l'arbitre : mesurer et réduire faux positifs / faux négatifs | Prévu |
| 3 | Attaquant adaptatif : reformuler selon la réponse précédente de la cible | Prévu |
| 4 | Dissocier l'arbitre du modèle cible | Prévu |
| 5 | Agents de reconnaissance et de planification ; campagnes multi-familles | Prévu |
| 6 | Génération de rapport avec classement par gravité | Prévu |
| 7 | Intégrer garak (couverture large) et PyRIT (orchestration multi-tours) | Prévu |

## Décisions prises et leur raison

**L'arbitre ne connaît pas le secret de la cible.** Il juge uniquement d'après
l'échange visible, comme en test boîte noire réel. C'est ce qui rend sa tâche
difficile — et c'est le cœur technique du projet.

**Arbitre et cible partagent actuellement le même modèle.** Pratique pour démarrer,
mais c'est un biais connu : un juge identique à sa cible partage ses angles morts.
C'est l'objet de la Phase 4. `demander_au_llm()` accepte déjà un paramètre `modele`
pour permettre cette dissociation.

**Ne pas automatiser ce qu'on ne sait pas faire à la main.** Les vraies attaques
attendent que l'auteur ait terminé le path AI Web Security de TryHackMe. Un agent dont
on ne sait pas juger les hallucinations est inutilisable.

## Cadre légal

Projet de recherche en sécurité. Le red teaming de LLM n'est licite que contre des
systèmes qu'on possède ou qu'on est **explicitement autorisé** à tester. Ne jamais
pointer l'outil vers un service tiers sans autorisation écrite.
