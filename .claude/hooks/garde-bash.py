"""Porte de sécurité sur les commandes shell (hook PreToolUse, matcher Bash).

Bloque : ``git push`` ailleurs que sur une branche ``feat/*``, ``--force``,
``DROP``/``TRUNCATE``, un tag ``v*`` (production), ``rm -rf`` hors des
dossiers temporaires — sauf si ``.claude/feature-state.json`` porte
``"go": true``, que seul le propriétaire pose. Sortie 2 = refus, le motif
sur stderr est lu par l'assistant.
"""

import json
import os
import re
import sys


def main():
    try:
        entree = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    cmd = (entree.get("tool_input") or {}).get("command", "") or ""
    racine = entree.get("cwd") or os.getcwd()
    # Les motifs se cherchent dans les commandes, pas dans ce qu'elles citent :
    # un message de commit ou un heredoc qui parle de « rm -r » ou d'une
    # poussée sur main n'est pas un ordre.
    cmd = re.sub(r"<<-?\s*'?(\w+)'?\n.*?\n\1(?=\n|$)", "<<HEREDOC", cmd, flags=re.S)
    cmd = re.sub(r'"(?:[^"\\]|\\.)*"', '""', cmd)
    cmd = re.sub(r"'(?:[^'\\]|\\.)*'", "''", cmd)
    try:
        with open(os.path.join(racine, ".claude", "feature-state.json"), encoding="utf-8") as f:
            if json.load(f).get("go") is True:
                return 0
    except Exception:  # noqa: BLE001
        pass
    motifs = [
        (r"git\s+push\b(?!.*\bfeat/)", "git push ailleurs que sur une branche feat/* : porte GO du propriétaire"),
        (r"(^|\s)--force(\s|$)", "--force interdit ; --force-with-lease seulement sur décision explicite"),
        (r"(?i)\bdrop\s+(table|database|schema)\b", "DROP : migration destructive, porte GO du propriétaire"),
        (r"(?i)\btruncate\s+table\b", "TRUNCATE : porte GO du propriétaire"),
        (r"git\s+tag\b.*\bv\d", "tag v* : livraison en production, porte GO du propriétaire"),
    ]
    for motif, raison in motifs:
        if re.search(motif, cmd):
            print(f"Commande bloquée par .claude/hooks/garde-bash.py — {raison}. "
                  "Le propriétaire peut poser \"go\": true dans .claude/feature-state.json.", file=sys.stderr)
            return 2
    for cible in re.findall(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+((?:\S+\s*)+)", cmd):
        for chemin in cible.split():
            if chemin.startswith("-"):
                continue
            tolere = chemin.startswith(("/tmp", "/private/tmp")) or any(
                m in chemin for m in ("scratchpad", "node_modules", "/dist", "/build", "captures")
            )
            if not tolere:
                print(f"rm -r hors des dossiers temporaires bloqué par .claude/hooks/garde-bash.py ({chemin}).", file=sys.stderr)
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
