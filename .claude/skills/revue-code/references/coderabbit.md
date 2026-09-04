# CodeRabbit et Claude Code

CodeRabbit relit chaque pull request sur GitHub et y dépose des remarques.
Deux façons de s'en servir ici.

## 1. Activer CodeRabbit sur le dépôt

1. Sur https://app.coderabbit.ai, connecter le compte GitHub et autoriser
   l'application sur `alamine2003/justiinnov-`.
2. Le fichier `.coderabbit.yaml` à la racine règle la langue des remarques
   (français), les chemins ignorés et les instructions de relecture, qui
   reprennent `CLAUDE.md`.
3. À partir de là, chaque pull request reçoit une revue automatique. Le
   workflow de livraison n'en dépend pas : la CI reste la garde-fou.

## 2. Lire et traiter ses remarques depuis Claude Code

`.mcp.json` déclare le serveur MCP communautaire `coderabbitai-mcp`, qui
expose les revues CodeRabbit d'une pull request comme outils (liste des
remarques, détail, marquage). Il lui faut un jeton GitHub :

```bash
export GITHUB_PAT=ghp_…    # droits repo (dépôt privé) ou public_repo
claude                      # le serveur apparaît dans /mcp
```

Le jeton n'est jamais écrit dans le dépôt : `.mcp.json` le lit dans
l'environnement. Sans jeton, le serveur ne démarre pas et Claude Code
continue de fonctionner sans lui.

Usage : « lis les remarques CodeRabbit de la PR 12 et corrige celles qui
sont fondées ». Chaque remarque se traite comme un constat de revue : on
vérifie avant de corriger, et un correctif s'accompagne de son test.
