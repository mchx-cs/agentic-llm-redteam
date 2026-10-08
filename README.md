# Pentest LLM — Phase 0 (squelette)

Automatisation de pentest de LLM par agents.
**Phase 0 = la tuyauterie uniquement**, pas de vraies attaques : on valide que
la boucle `attaquant → cible → arbitre` tourne de bout en bout, en local.

## Structure

```
pentest-llm/
├── config.py          # LE point de bascule local <-> API (une seule ligne)
├── llm_client.py      # LA couche d'abstraction : demander_au_llm()
├── cible.py           # le LLM qu'on teste (cible-jouet avec un secret)
├── agents/
│   ├── attaquant.py   # génère les tentatives (anodines en Phase 0)
│   └── arbitre.py     # juge si une tentative a réussi (LLM-as-judge)
└── main.py            # l'orchestrateur : la boucle complète
```

Règle d'or du projet : **personne n'appelle un LLM directement**, tout passe
par `demander_au_llm()`. C'est ce qui rend la migration local → API triviale.

## Installation (100 % local, gratuit)

1. **Installer Ollama** : https://ollama.com (dispo macOS / Windows / Linux)

2. **Télécharger un petit modèle** :
   ```bash
   ollama pull llama3.2
   ```

3. **Installer la dépendance Python** (dans un environnement virtuel, idéalement) :
   ```bash
   pip install -r requirements.txt
   ```

## Lancer

Depuis le dossier `pentest-llm/` :
```bash
python main.py
```

Tu dois voir défiler les 3 essais, avec pour chacun le message envoyé, la
réponse de la cible, et le verdict de l'arbitre. En Phase 0, les messages
étant anodins, le verdict attendu est "NON" à chaque fois — et c'est normal :
ça prouve juste que la chaîne complète fonctionne.

## Basculer vers une API plus tard

1. Dans `config.py`, renseigner le profil `"api"` (URL, modèle).
2. Exporter la clé : `export OPENAI_API_KEY="sk-..."`
3. Changer **une seule ligne** : `PROFIL_ACTIF = "api"`

Rien d'autre à toucher.

## Prochaines étapes (après le path AI Security)

- `attaquant.py` → remplacer les messages anodins par de vraies familles
  d'attaques (prompt injection, jailbreak…), puis une version qui s'adapte.
- `arbitre.py` → fiabiliser le jugement (le vrai défi technique).
- `main.py` → tester plusieurs familles d'attaques, puis générer un rapport.
- Intégrer les outils de référence : **garak** (scan large) et **PyRIT**
  (orchestration multi-tours), au lieu de tout coder soi-même.
