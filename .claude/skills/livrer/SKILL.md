---
name: livrer
description: Commiter par lots thématiques en français, pousser sur GitHub et déclencher la livraison de JUSTI INNOV (préproduction sur main, production sur un tag v*), avec les contrôles préalables et les secrets attendus. À utiliser quand on demande de commiter, pousser, publier ou déployer.
---

# Livrer

## Instructions

### Étape 1 : conditions

Le skill `verifier` est passé au vert. `git status` ne montre que ce qui
doit partir : jamais `.env`, `seed_users.local.json`, `seed_users.ci.json`,
`*.mo`, `.claude/settings.local.json`.

### Étape 2 : commits par lots

Un commit par sujet, jamais un fourre-tout : backend d'une app, frontend,
infrastructure, documentation. Message en français, verbe au présent en
tête (« Rend », « Corrige », « Ajoute »), corps qui explique le pourquoi,
et le pied de page :

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

### Étape 3 : pousser

Remote `origin` = `https://github.com/alamine2003/justiinnov-.git`.

```bash
git push origin main
```

Il faut un jeton d'accès personnel GitHub ou `gh auth login`. Une
réécriture d'historique se pousse avec `--force-with-lease`, jamais
`--force` nu, et seulement sur décision explicite.

### Étape 4 : livraison

- Une poussée sur `main` déclenche `ci.yml` puis, si tout est vert, la
  livraison en préproduction (`cd.yml`).
- Un tag `vX.Y.Z` livre en production après approbation dans l'environnement
  GitHub `production` :

```bash
git tag -a v1.0.0 -m "Première mise en service"
git push origin v1.0.0
```

Secrets et variables par environnement : `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `APP_DOMAIN`, `DEPLOY_PATH` ; côté
serveur, le `.env` d'après `deploy/.env.example`. Détail dans
`deploy/README.md`.

### Étape 5 : après la livraison

Vérifier `https://<domaine>/api/health/`, le tableau Grafana, et relancer
`seed_users` sur le serveur pour les comptes réels. Consigner la version
livrée dans le message de fin.
