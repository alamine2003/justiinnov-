"""À l'arrêt de l'assistant (hook Stop) : relance la boucle /feature.

Tant que ``.claude/feature-state.json`` dit ``status != done`` et ``cycle <
8``, l'assistant est renvoyé au cycle suivant. Le compteur ``nudges`` borne
les relances à huit : jamais de boucle sans fin.
"""

import json
import os
import sys


def main():
    try:
        entree = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    racine = entree.get("cwd") or os.getcwd()
    chemin = os.path.join(racine, ".claude", "feature-state.json")
    try:
        with open(chemin, encoding="utf-8") as f:
            etat = json.load(f)
    except Exception:  # noqa: BLE001
        return 0
    if etat.get("status") in (None, "done", "blocked"):
        return 0
    if int(etat.get("cycle", 0)) >= 8 or int(etat.get("nudges", 0)) >= 8:
        return 0
    etat["nudges"] = int(etat.get("nudges", 0)) + 1
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "decision": "block",
        "reason": (f"Continue la boucle /feature « {etat.get('feature')} », cycle suivant "
                   f"(cycle {etat.get('cycle')} sur 8). Rends d'abord le rapport de cycle au propriétaire."),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
