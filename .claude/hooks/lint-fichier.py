"""Après chaque Edit ou Write (hook PostToolUse) : lint du fichier touché.

TypeScript du frontend → oxlint ; Python du backend → compilation ; le
reste → rien. Sortie 2 avec le rapport sur stderr : l'assistant corrige.
"""

import json
import os
import subprocess
import sys


def main():
    try:
        entree = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    chemin = (entree.get("tool_input") or {}).get("file_path", "") or ""
    racine = entree.get("cwd") or os.getcwd()
    if not chemin or not os.path.exists(chemin):
        return 0
    if chemin.endswith((".ts", ".tsx")) and "/frontend/src/" in chemin and "types.generated" not in chemin:
        r = subprocess.run(["npx", "oxlint", chemin], cwd=os.path.join(racine, "frontend"),
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or "warning" in r.stdout:
            print(r.stdout[-1500:] + r.stderr[-500:], file=sys.stderr)
            return 2
    elif chemin.endswith(".py") and "/backend/" in chemin:
        r = subprocess.run([sys.executable, "-m", "py_compile", chemin], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(r.stderr[-1500:], file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
