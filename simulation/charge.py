"""Charge réaliste et multi-pays : 30 utilisateurs sur la pile livrable.

Comptes jetables (``SIM_COMPTES``) : managers CI et TG (dont un cloisonné
par équipe), DM, DF, admin, super admin. Chaque fil joue un utilisateur
réel avec un temps de réflexion entre deux actions ; le cloisonnement est
vérifié à chaque lecture (un manager ne doit voir que son pays et, s'il
est rattaché, ses équipes).

Usage : SIM_COMPTES=comptes.json python3 simulation/charge.py BASE DUREE_SECONDES REFLEXION_SECONDES
"""

import json
import random
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import defaultdict

from commun import COMPOSE, RACINE, code_totp, comptes, multipart, pdf

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DUREE = int(sys.argv[2]) if len(sys.argv) > 2 else 60
REFLEXION = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
ANNEE = time.gmtime().tm_year

mesures = []
premiers_refus = {}
erreurs_reseau = defaultdict(int)
violations = []
verrou = threading.Lock()
stats_docker = []
connexions_pg = []


def requete(method, chemin, token=None, data=None, label=None, corps=None, content_type=None, brut=False):
    headers = {"Accept": "application/json", "Accept-Language": "fr"}
    if token:
        headers["Authorization"] = f"Token {token}"
    body = None
    if corps is not None:
        body, headers["Content-Type"] = corps, content_type
    elif data is not None:
        body, headers["Content-Type"] = json.dumps(data).encode(), "application/json"
    req = urllib.request.Request(BASE + chemin, data=body, method=method, headers=headers)
    debut = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as rep:
            statut, contenu = rep.status, rep.read()
    except urllib.error.HTTPError as e:
        statut, contenu = e.code, e.read()
    except Exception as e:  # noqa: BLE001
        statut, contenu = 0, b""
        with verrou:
            erreurs_reseau[type(e).__name__ + ": " + str(e)[:60]] += 1
    ms = (time.perf_counter() - debut) * 1000
    with verrou:
        mesures.append((label or f"{method} {chemin.split('?')[0]}", statut, ms))
        if statut >= 400 and label and label not in premiers_refus:
            premiers_refus[label] = (statut, contenu[:200])
    if brut:
        return statut, contenu
    try:
        return statut, json.loads(contenu) if contenu else None
    except Exception:  # noqa: BLE001
        return statut, contenu


def connexion(username, compte):
    for _ in range(4):
        statut, rep = requete("POST", "/api/token-auth/", data={
            "username": username, "password": compte["password"], "code": code_totp(compte["totp_secret"])},
            label="POST token-auth (login + TOTP)")
        if statut == 200:
            return rep["token"]
        print("login", username, statut, rep)
        time.sleep(31 if statut == 400 else 7)
    raise SystemExit(f"connexion impossible pour {username}")


def pause():
    if REFLEXION:
        time.sleep(random.uniform(0.5 * REFLEXION, 1.5 * REFLEXION))


def verifier_cloisonnement(nom, resultats, pays_id, equipe_id):
    for r in resultats:
        if r.get("country") not in (None, pays_id):
            violations.append(f"{nom} voit le pays {r.get('country')} (dossier {r.get('id')})")
        if equipe_id and r.get("team") not in (None, equipe_id):
            violations.append(f"{nom} voit l'équipe {r.get('team')} (dossier {r.get('id')})")


def manager(nom, token, ctx, fin):
    pays, equipe, proprietaire = ctx["pays"], ctx["equipe"], ctx["proprietaire"]
    n = 0
    while time.monotonic() < fin:
        n += 1
        s, page = requete("GET", "/api/dossiers/?page_size=20", token, label="GET dossiers (liste)")
        if s == 200:
            verifier_cloisonnement(nom, page["results"], pays, ctx.get("equipe_restreinte"))
        pause()
        requete("GET", "/api/expenses/register/?page_size=25&search=Ligne", token, label="GET registre (recherche)")
        pause()
        requete("GET", f"/api/countries/{pays}/", token, label="GET pays (référentiel)")
        numero = f"LOAD-{nom}-{n}-{uuid.uuid4().hex[:4]}"
        s, dossier = requete("POST", "/api/dossiers/", token, {
            "number": numero, "label": f"Mission {numero}", "country": pays,
            "team": equipe, "owner": proprietaire, "date": f"{ANNEE}-03-15"}, label="POST dossier")
        if s != 201:
            pause(); continue
        lignes = []
        for k in range(3):
            s, ligne = requete("POST", "/api/expenses/", token, {
                "dossier": dossier["id"], "country": pays, "team": equipe, "owner": proprietaire,
                "date": f"{ANNEE}-03-15T10:00:00Z", "title": f"Ligne {k}", "amount": "1500.00",
                "payment_method": "cash"}, label="POST ligne")
            if s == 201:
                lignes.append(ligne["id"])
        if lignes:
            requete("PATCH", f"/api/expenses/{lignes[0]}/", token, {"amount": "1750.00"}, label="PATCH ligne (brouillon)")
        pause()
        corps, ct = multipart({"dossier": dossier["id"], "kind": "invoice"}, ("facture.pdf", pdf(uuid.uuid4().hex)))
        s, piece = requete("POST", "/api/proofs/", token, corps=corps, content_type=ct, label="POST pièce (upload)")
        if s == 201:
            requete("GET", f"/api/proofs/{piece['id']}/download/", token, label="GET pièce (téléchargement)", brut=True)
        pause()
        requete("POST", f"/api/dossiers/{dossier['id']}/submit/", token, label="POST soumettre")
        requete("GET", f"/api/dossiers/{dossier['id']}/", token, label="GET dossier (détail)")
        requete("GET", "/api/notifications/unread_count/", token, label="GET notifications (compteur)")
        s, _ = requete("GET", f"/api/dossiers/{ctx['dossier_etranger']}/", token, label="GET dossier étranger (IDOR)")
        if s not in (404, 0):
            violations.append(f"{nom} obtient {s} sur un dossier de l'autre pays")
        pause()


def dm(nom, token, ctx, fin):
    while time.monotonic() < fin:
        requete("GET", f"/api/dashboard/?year={ANNEE}", token, label="GET tableau de bord")
        pause()
        s, page = requete("GET", "/api/dossiers/?status=submitted&page_size=10", token, label="GET dossiers soumis")
        if s == 200 and page["results"]:
            d = random.choice(page["results"])
            requete("POST", f"/api/dossiers/{d['id']}/review/", token, label="POST mise en contrôle")
        pause()
        requete("GET", "/api/history/?page_size=20", token, label="GET historique")
        requete("GET", "/api/notifications/?page_size=10", token, label="GET notifications (liste)")
        pause()


def df(nom, token, ctx, fin):
    while time.monotonic() < fin:
        requete("GET", "/api/expenses/register/?page_size=25&status=in_review", token, label="GET registre (filtre)")
        pause()
        s, page = requete("GET", "/api/dossiers/?status=in_review&page_size=10", token, label="GET dossiers en contrôle")
        if s == 200 and page["results"]:
            d = random.choice(page["results"])
            s, detail = requete("GET", f"/api/dossiers/{d['id']}/", token, label="GET dossier (détail)")
            if s == 200:
                for piece in detail.get("proofs", [])[:1]:
                    if "validated" in piece.get("allowed_reviews", []):
                        requete("POST", f"/api/proofs/{piece['id']}/review/", token, {"status": "validated"}, label="POST contrôle de pièce")
                for i, ligne in enumerate(detail.get("expenses", [])):
                    if "justify" not in ligne.get("allowed_actions", []):
                        continue
                    if i == 2:
                        requete("POST", f"/api/expenses/{ligne['id']}/reject/", token, {"note": "Sans reçu"}, label="POST refuser ligne")
                    else:
                        requete("POST", f"/api/expenses/{ligne['id']}/justify/", token, label="POST justifier ligne")
                pause()
                s2, apres = requete("GET", f"/api/dossiers/{d['id']}/", token, label="GET dossier (détail)")
                if s2 == 200:
                    if "justify" in apres["allowed_actions"]:
                        requete("POST", f"/api/dossiers/{d['id']}/justify/", token, label="POST justifier dossier")
                        requete("POST", f"/api/dossiers/{d['id']}/close/", token, label="POST clôturer")
                    elif "reject" in apres["allowed_actions"]:
                        requete("POST", f"/api/dossiers/{d['id']}/reject/", token, {"note": "Pièces insuffisantes"}, label="POST refuser dossier")
        pause()
        requete("GET", f"/api/budgets/?year={ANNEE}", token, label="GET enveloppes")
        pause()


def admin(nom, token, ctx, fin):
    tour = 0
    while time.monotonic() < fin:
        tour += 1
        requete("GET", "/api/audit/?page_size=25", token, label="GET journal d'audit")
        pause()
        requete("GET", f"/api/exports/expenses.csv?year={ANNEE}", token, label="GET export CSV", brut=True)
        pause()
        if tour % 3 == 0:
            requete("GET", f"/api/exports/report.pdf?year={ANNEE}&country={ctx['pays_tg']}", token, label="GET export PDF", brut=True)
        requete("GET", f"/api/dashboard/breakdown/?year={ANNEE}&country={ctx['pays_tg']}", token, label="GET ventilation")
        requete("GET", "/api/users/?page_size=50", token, label="GET comptes")
        pause()


def sonde(fin):
    while time.monotonic() < fin:
        try:
            out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}",
                                  "justi_backend", "justi_db", "justi_frontend", "justi_caddy", "justi_minio"],
                                 capture_output=True, text=True, timeout=20).stdout
            pg = subprocess.run(COMPOSE + ["exec", "-T", "db", "sh", "-c",
                                'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*), count(*) filter (where state=\'active\'), count(*) filter (where wait_event_type=\'Lock\') from pg_stat_activity where datname=current_database()"'],
                                cwd=RACINE, capture_output=True, text=True, timeout=20).stdout.strip()
            stats_docker.append(out.strip()); connexions_pg.append(pg)
        except Exception as e:  # noqa: BLE001
            stats_docker.append(f"sonde: {e}")
        time.sleep(5)


def main():
    c = comptes()
    jetons = {nom: connexion(nom, compte) for nom, compte in c.items()}
    siege = jetons["siege.ci"]
    statut, pays = requete("GET", "/api/countries/?page_size=50", siege, label="setup")
    if statut != 200 or not isinstance(pays, dict):
        raise SystemExit(f"setup : GET countries → {statut} {pays!r:.300}")
    par_code = {p["code"]: p for p in pays["results"]}
    contexte = {}
    for code in ("TG", "CI"):
        _, detail = requete("GET", f"/api/countries/{par_code[code]['id']}/", siege, label="setup")
        contexte[code] = {"pays": par_code[code]["id"], "equipes": detail["teams"], "proprietaire": detail["managers"][0]["id"]}
    # Enveloppes larges : le blocage budgétaire est éprouvé par les tests de course.
    _, budgets = requete("GET", f"/api/budgets/?year={ANNEE}&page_size=50", siege, label="setup")
    for b in budgets["results"]:
        if b.get("scope_kind") in (None, "country") and b["amount"] != "5000000000.00":
            requete("PATCH", f"/api/budgets/{b['id']}/", siege, {"amount": "5000000000.00"}, label="setup")
    etranger = {}
    for code, autre in (("TG", "CI"), ("CI", "TG")):
        _, page = requete("GET", f"/api/dossiers/?country={contexte[autre]['pays']}&page_size=1", siege, label="setup")
        etranger[code] = page["results"][0]["id"] if page["results"] else 1

    def ctx_manager(code, equipe_nom=None):
        cx = contexte[code]
        equipe = next((t for t in cx["equipes"] if t["name"] == equipe_nom), cx["equipes"][0]) if equipe_nom else cx["equipes"][0]
        return {"pays": cx["pays"], "equipe": equipe["id"], "proprietaire": cx["proprietaire"],
                "dossier_etranger": etranger[code], "equipe_restreinte": equipe["id"] if equipe_nom else None}

    fin = time.monotonic() + DUREE
    fils = [threading.Thread(target=sonde, args=(fin,))]
    repartition = ([("ci1.ci", "CI", None)] * 5 + [("ci2.ci", "CI", None)] * 5 + [("togo.ci", "TG", None)] * 4
                   + [("tg3.ci", "TG", None)] * 3 + [("tg2.ci", "TG", "Équipe Lomé")] * 3)
    for i, (compte, code, equipe_nom) in enumerate(repartition):
        fils.append(threading.Thread(target=manager, args=(f"{compte}#{i}", jetons[compte], ctx_manager(code, equipe_nom), fin)))
    for i in range(4):
        fils.append(threading.Thread(target=dm, args=(f"dm#{i}", jetons["dm.ci"], contexte, fin)))
    for i in range(4):
        fils.append(threading.Thread(target=df, args=(f"df#{i}", jetons["df.ci"], contexte, fin)))
    for i in range(2):
        fils.append(threading.Thread(target=admin, args=(f"admin#{i}", jetons["admin.ci"], {"pays_tg": contexte["TG"]["pays"]}, fin)))
    print(f"base {BASE} · {len(fils) - 1} utilisateurs · {DUREE} s · réflexion {REFLEXION} s")
    debut = time.monotonic()
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    duree = time.monotonic() - debut

    par_label = defaultdict(list)
    for label, statut, ms in mesures:
        if label != "setup":
            par_label[label].append((statut, ms))
    total = sum(len(v) for v in par_label.values())
    reussies = sum(1 for v in par_label.values() for s, _ in v if 200 <= s < 300)
    print(f"\n{total} requêtes en {duree:.0f} s ({total / duree:.1f} req/s), {reussies} réussies")
    entete = "point d'entrée"
    print(f"{entete:34} {'n':>5} {'ok':>5} {'p50':>6} {'p95':>6} {'p99':>6} {'max':>6}  codes")

    def quantile(v, p):
        lat = sorted(x[1] for x in v)
        return lat[min(len(lat) - 1, max(0, int(len(lat) * p) - 1))]

    for label, v in sorted(par_label.items(), key=lambda kv: -quantile(kv[1], 0.95)):
        lat = sorted(x[1] for x in v)
        ok = sum(1 for s, _ in v if 200 <= s < 300)
        codes = defaultdict(int)
        for s, _ in v:
            codes[s] += 1
        print(f"{label:34} {len(v):5} {ok:5} {statistics.median(lat):6.0f} {quantile(v, 0.95):6.0f} {quantile(v, 0.99):6.0f} {lat[-1]:6.0f}  {dict(codes)}")
    print("\npremiers refus par route :")
    for label, (statut, corps) in premiers_refus.items():
        print(f"  {label}: {statut} {corps!r}")
    print("\nerreurs réseau :", dict(erreurs_reseau) or "aucune")
    print("violations de cloisonnement :", len(violations), violations[:5])
    print("\nsondes docker (cpu, mémoire) :")
    for s in stats_docker[:: max(1, len(stats_docker) // 4)]:
        print("  " + s.replace("\n", " | "))
    print("connexions PostgreSQL (total, actives, en attente de verrou) :", connexions_pg)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
