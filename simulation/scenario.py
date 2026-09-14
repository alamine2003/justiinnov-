"""Mise en service d'une filiale, jouée par l'API, étape par étape.

Chaque étape attend un code précis ; le rapport liste OK/KO avec le détail.
Usage : SIM_COMPTES=comptes.json python3 simulation/scenario.py http://127.0.0.1:8000
"""

import io
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

import openpyxl

from commun import COMPOSE, RACINE, code_totp, comptes, multipart, pdf

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
rapport = []


def api(method, chemin, token=None, data=None, corps=None, content_type=None, lang="fr", brut=False):
    headers = {"Accept": "application/json", "Accept-Language": lang}
    if token:
        headers["Authorization"] = f"Token {token}"
    body = None
    if corps is not None:
        body, headers["Content-Type"] = corps, content_type
    elif data is not None:
        body, headers["Content-Type"] = json.dumps(data).encode(), "application/json"
    req = urllib.request.Request(BASE + chemin, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as rep:
            statut, contenu, entetes = rep.status, rep.read(), dict(rep.headers)
    except urllib.error.HTTPError as e:
        statut, contenu, entetes = e.code, e.read(), dict(e.headers)
    if brut:
        return statut, contenu, entetes
    try:
        return statut, (json.loads(contenu) if contenu else None), entetes
    except Exception:  # noqa: BLE001
        return statut, contenu, entetes


def etape(nom, attendu, statut, detail=None):
    attendus = attendu if isinstance(attendu, (tuple, list, set)) else (attendu,)
    ok = statut in attendus
    rapport.append((nom, "OK" if ok else "KO", statut, attendu, "" if ok else str(detail)[:220]))
    return ok


def connexion(username, compte):
    for _ in range(3):
        s, rep, _ = api("POST", "/api/token-auth/", data={
            "username": username, "password": compte["password"], "code": code_totp(compte["totp_secret"])})
        if s == 200:
            return rep["token"]
        time.sleep(31)
    raise SystemExit(f"connexion impossible : {username} {s} {rep}")


def main():
    c = comptes()
    siege = connexion("siege.ci", c["siege.ci"])
    suffixe = uuid.uuid4().hex[:6]

    # 1. Le super administrateur crée les comptes du siège
    for role in ("dm", "df", "admin"):
        nom = f"{role}.{suffixe}"
        s, rep, _ = api("POST", "/api/users/", siege, {"username": nom, "email": f"{nom}@innovpharma.net", "role": role,
                                                       "first_name": role.upper(), "last_name": "Scénario",
                                                       "password": "Provisoire-2026-" + suffixe})
        etape(f"1. créer le compte {role}", 201, s, rep)
    s, rep, _ = api("POST", "/api/users/", siege, {"username": f"x.{suffixe}", "email": f"x.{suffixe}@gmail.com",
                                                   "role": "manager", "password": "Provisoire-2026-" + suffixe})
    etape("1. un compte hors @innovpharma.net est refusé", 400, s, rep)
    # Les comptes créés ont un mot de passe provisoire et pas de 2FA : les rôles
    # du siège se jouent avec les comptes jetables déjà enrôlés.
    dm = connexion("dm.ci", c["dm.ci"]); df = connexion("df.ci", c["df.ci"])
    admin = connexion("admin.ci", c["admin.ci"]); manager = connexion("tg3.ci", c["tg3.ci"])

    # 2. L'admin ouvre un pays et son référentiel
    s, dispo, _ = api("GET", "/api/countries/disponibles/", admin)
    etape("2. liste des filiales ouvrables", 200, s, dispo)
    pays_existants = api("GET", "/api/countries/?page_size=50", admin)[1]["results"]
    codes_pris = {p["code"] for p in pays_existants}
    liste = dispo if isinstance(dispo, list) else dispo.get("results", [])
    candidat = next((p for p in liste if p.get("code") not in codes_pris), None)
    if candidat:
        s, pays, _ = api("POST", "/api/countries/", admin, {"code": candidat["code"], "name": candidat.get("name", candidat["code"]), "currency": "XOF"})
        etape(f"2. ouvrir la filiale {candidat['code']}", 201, s, pays)
    s, rep, _ = api("POST", "/api/countries/", admin, {"code": "FR", "name": "France", "currency": "EUR"})
    etape("2. un pays hors périmètre est refusé", 400, s, rep)
    togo = next(p for p in pays_existants if p["code"] == "TG")
    ids = {}
    for ressource, charge in (("teams", {"name": f"Équipe {suffixe}"}), ("projects", {"name": f"Projet {suffixe}"}),
                              ("expense-titles", {"label": f"Intitulé {suffixe}"}),
                              ("marketing-categories", {"name": f"Catégorie {suffixe}"}),
                              ("beneficiaries", {"name": f"Pharmacie {suffixe}", "kind": "client"})):
        s, rep, _ = api("POST", f"/api/{ressource}/", admin, {"country": togo["id"], **charge})
        etape(f"2. référentiel : {ressource}", 201, s, rep)
        ids[ressource] = rep["id"] if s == 201 else None
    s, rep, _ = api("POST", "/api/teams/", manager, {"country": togo["id"], "name": "Équipe pirate"})
    etape("2. un manager ne crée pas d'équipe", 403, s, rep)
    s, mgr, _ = api("POST", "/api/users/", admin, {"username": f"mgr.{suffixe}", "email": f"mgr.{suffixe}@innovpharma.net",
                                                  "role": "manager", "countries": [togo["id"]], "teams": [ids["teams"]],
                                                  "password": "Provisoire-2026-" + suffixe})
    etape("2. compte manager rattaché à une équipe", 201, s, mgr)

    # 3. Le super administrateur attribue enveloppe, sous-enveloppe, taux
    annee = time.gmtime().tm_year
    s, enveloppes, _ = api("GET", f"/api/budgets/?year={annee}&country={togo['id']}&page_size=50", siege)
    principale = next((b for b in enveloppes["results"] if b.get("scope_kind") in (None, "country")), None)
    if principale is None:
        s, principale, _ = api("POST", "/api/budgets/", siege, {"country": togo["id"], "year": annee, "amount": "50000000.00"})
        etape("3. enveloppe annuelle du pays", 201, s, principale)
    s, sous, _ = api("POST", "/api/budgets/", siege, {"country": togo["id"], "year": annee, "team": ids["teams"],
                                                     "amount": "300000.00", "overrun_policy": "block"})
    etape("3. sous-enveloppe par équipe (bloquante)", 201, s, sous)
    s, rep, _ = api("POST", "/api/budgets/", admin, {"country": togo["id"], "year": annee, "project": ids["projects"], "amount": "1.00"})
    etape("3. la RH n'attribue pas d'enveloppe", 403, s, rep)
    s, rep, _ = api("POST", "/api/exchange-rates/", siege, {"currency": "EUR", "rate_to_xof": "655.9570", "valid_from": f"{annee}-01-01"})
    etape("3. taux de change EUR", (201, 400), s, rep)

    # 4. Le manager saisit un dossier, des lignes, des pièces, soumet
    proprietaire = api("GET", f"/api/countries/{togo['id']}/", manager)[1]["managers"][0]["id"]
    numero = f"SC-{suffixe}"
    base_ligne = {"country": togo["id"], "team": ids["teams"], "owner": proprietaire, "payment_method": "cash",
                  "date": f"{annee}-04-02T09:00:00Z"}
    s, dossier, _ = api("POST", "/api/dossiers/", manager, {"number": numero, "label": "Tournée pharmacies", "country": togo["id"],
                                                            "team": ids["teams"], "owner": proprietaire, "date": f"{annee}-04-02"})
    etape("4. créer le dossier", 201, s, dossier)
    lignes = []
    for titre, montant in (("Carburant", "120000.00"), ("Hôtel", "90000.00"), ("Échantillons", "60000.00")):
        s, l, _ = api("POST", "/api/expenses/", manager, {**base_ligne, "dossier": dossier["id"], "title": titre, "amount": montant,
                                                         "project": ids["projects"], "expense_title": ids["expense-titles"],
                                                         "beneficiary": ids["beneficiaries"]})
        etape(f"4. ligne {titre}", 201, s, l); lignes.append(l)
    s, ligne_trop, _ = api("POST", "/api/expenses/", manager, {**base_ligne, "dossier": dossier["id"], "title": "Trop", "amount": "100000.00"})
    etape("4. ligne au-delà de la sous-enveloppe : acceptée en brouillon", 201, s, ligne_trop)
    s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/submit/", manager)
    etape("4. soumettre 370 000 sur une sous-enveloppe de 300 000 qui bloque", 400, s, rep)
    s, rep, _ = api("DELETE", f"/api/expenses/{ligne_trop['id']}/", manager)
    etape("4. retirer la ligne de trop (brouillon, auteur)", 204, s, rep)
    contenu = pdf(suffixe)
    corps, ct = multipart({"dossier": dossier["id"], "kind": "invoice"}, ("facture.pdf", contenu))
    s, piece, _ = api("POST", "/api/proofs/", manager, corps=corps, content_type=ct)
    etape("4. déposer une pièce", 201, s, piece)
    corps, ct = multipart({"dossier": dossier["id"], "kind": "invoice"}, ("facture-bis.pdf", contenu))
    s, rep, _ = api("POST", "/api/proofs/", manager, corps=corps, content_type=ct)
    etape("4. la même pièce en double est refusée", 400, s, rep)
    corps, ct = multipart({"dossier": dossier["id"], "kind": "invoice"}, ("gros.pdf", b"%PDF-1.4 " + b"0" * (21 * 1024 * 1024)))
    s, rep, _ = api("POST", "/api/proofs/", manager, corps=corps, content_type=ct)
    etape("4. une pièce de 21 Mo est refusée", (400, 413), s, rep)
    corps, ct = multipart({"dossier": dossier["id"], "kind": "invoice"}, ("script.exe", b"MZ..."), "application/octet-stream")
    s, rep, _ = api("POST", "/api/proofs/", manager, corps=corps, content_type=ct)
    etape("4. un format refusé (.exe)", 400, s, rep)
    corps, ct = multipart({"dossier": dossier["id"], "kind": "invoice"}, ("page.pdf", b"<html><script>alert(1)</script></html>"))
    s, rep, _ = api("POST", "/api/proofs/", manager, corps=corps, content_type=ct)
    etape("4. un HTML déguisé en PDF est refusé", 400, s, rep)
    s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/submit/", manager)
    etape("4. soumettre le dossier (avec pièce)", 200, s, rep)
    s, d2, _ = api("POST", "/api/dossiers/", manager, {"number": numero + "-B", "label": "Sans pièce", "country": togo["id"],
                                                       "team": ids["teams"], "owner": proprietaire, "date": f"{annee}-04-03"})
    api("POST", "/api/expenses/", manager, {**base_ligne, "dossier": d2["id"], "title": "Taxi", "amount": "5000.00"})
    s, rep, _ = api("POST", f"/api/dossiers/{d2['id']}/submit/", manager)
    etape("4. soumettre sans pièce : accepté avec avertissement", 200, s, rep)
    if s == 200 and not rep.get("warning"):
        rapport.append(("4. avertissement « sans pièce » présent", "KO", "-", "warning", str(rep)[:120]))

    # 5. Le DM met en contrôle
    s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/review/", dm)
    etape("5. le DM met le dossier en contrôle", 200, s, rep)
    s, rep, _ = api("POST", f"/api/expenses/{lignes[0]['id']}/justify/", dm)
    etape("5. le DM ne justifie pas", 403, s, rep)

    # 6. Le DF contrôle les pièces, justifie, refuse, clôture
    s, rep, _ = api("POST", f"/api/proofs/{piece['id']}/review/", df, {"status": "incomplete", "reason": "Page manquante"})
    etape("6. pièce signalée incomplète", 200, s, rep)
    s, rep, _ = api("POST", f"/api/proofs/{piece['id']}/review/", df, {"status": "validated"})
    etape("6. pièce validée", 200, s, rep)
    s, rep, _ = api("POST", f"/api/expenses/{lignes[0]['id']}/justify/", df)
    etape("6. justifier la ligne 1", 200, s, rep)
    s, rep, _ = api("POST", f"/api/expenses/{lignes[1]['id']}/justify/", df, {"justified_amount": "50000.00"})
    etape("6. justifier partiellement la ligne 2", 200, s, rep)
    s, rep, _ = api("POST", f"/api/expenses/{lignes[2]['id']}/reject/", df, {})
    etape("6. refuser sans motif : refusé", 400, s, rep)
    s, rep, _ = api("POST", f"/api/expenses/{lignes[2]['id']}/reject/", df, {"note": "Reçu illisible"})
    etape("6. refuser avec motif", 200, s, rep)
    s, det, _ = api("GET", f"/api/dossiers/{dossier['id']}/", df)
    etape("6. dossier : actions possibles = " + ",".join(det.get("allowed_actions", [])), 200, s, det)
    if "reject" in det.get("allowed_actions", []):
        s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/reject/", df, {"note": "Une ligne sans preuve"})
        etape("6. constat du dossier (non justifié)", 200, s, rep)
    api("POST", f"/api/dossiers/{d2['id']}/review/", dm)
    s, rep, _ = api("POST", f"/api/dossiers/{d2['id']}/justify/", df)
    etape("6. justifier un dossier sans pièce exploitable : refusé", 400, s, rep)

    # 7. Le manager tente l'interdit
    s, rep, _ = api("POST", f"/api/expenses/{lignes[0]['id']}/justify/", manager)
    etape("7. le manager ne justifie pas sa ligne", 403, s, rep)
    s, rep, _ = api("PATCH", f"/api/expenses/{lignes[0]['id']}/", manager, {"amount": "1.00"})
    etape("7. une ligne soumise ne se modifie plus", 400, s, rep)
    s, rep, _ = api("DELETE", f"/api/dossiers/{dossier['id']}/", manager)
    etape("7. un dossier soumis ne se retire pas", 400, s, rep)
    s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/reopen/", manager, {"note": "moi-même"})
    etape("7. le manager ne rouvre pas", 403, s, rep)

    # 8. Réallocation : demande, quatre yeux, immuable
    s, realloc, _ = api("POST", "/api/reallocations/", siege, {"source": principale["id"], "target": sous["id"],
                                                               "amount": "100000.00", "reason": "Renfort équipe"})
    etape("8. demander une réallocation", 201, s, realloc)
    s, rep, _ = api("POST", f"/api/reallocations/{realloc['id']}/approve/", siege)
    etape("8. approuver sa propre demande : refusé (quatre yeux)", 403, s, rep)
    s, rep, _ = api("PATCH", f"/api/reallocations/{realloc['id']}/", siege, {"amount": "1.00"})
    etape("8. réécrire une réallocation : 405", 405, s, rep)

    # 9. La RH rouvre un dossier non justifié, puis tente un dossier constaté
    s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/reopen/", admin, {})
    etape("9. rouvrir sans motif : refusé", 400, s, rep)
    s, rep, _ = api("POST", f"/api/dossiers/{d2['id']}/reopen/", admin, {"note": "Pièce attendue"})
    etape("9. rouvrir le dossier sans pièce (déclaré, non constaté)", 200, s, rep)
    s, notifs, _ = api("GET", "/api/notifications/?page_size=5", manager)
    etape("9. le manager est notifié de la réouverture", 200, s, notifs)
    if s == 200 and not any(n.get("kind") == "dossier_reopened" for n in notifs["results"]):
        rapport.append(("9. notification dossier_reopened reçue", "KO", "-", "-", str(notifs)[:120]))
    s, rep, _ = api("POST", f"/api/dossiers/{dossier['id']}/reopen/", admin, {"note": "Trop tard"})
    etape("9. rouvrir un dossier constaté : refusé", 400, s, rep)

    # 10. Import et exports
    s, classeur, _ = api("GET", f"/api/exports/expenses.xlsx?year={annee}&country={togo['id']}", admin, brut=True)
    etape("10. export xlsx", 200, s, classeur[:80])
    entetes = [c.value for c in openpyxl.load_workbook(io.BytesIO(classeur)).active[1]]
    rapport.append(("10. colonnes de l'export : " + ", ".join(str(e) for e in entetes[:9]), "OK", 200, 200, ""))
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    corps, ct = multipart({"country": togo["id"]}, ("historique.xlsx", classeur), xlsx)
    s, sim, _ = api("POST", "/api/imports/expenses.xlsx?dry_run=true", admin, corps=corps, content_type=ct)
    etape("10. import simulé", 200, s, sim)
    s, reel, _ = api("POST", "/api/imports/expenses.xlsx", admin, corps=corps, content_type=ct)
    etape("10. import réel", 200, s, reel)
    s, bis, _ = api("POST", "/api/imports/expenses.xlsx", admin, corps=corps, content_type=ct)
    etape("10. réimport identique", 200, s, bis)
    if s == 200 and bis.get("lignes_creees"):
        rapport.append(("10. réimport idempotent", "KO", "-", "0 ligne", str(bis)[:120]))
    s, rep, _ = api("POST", "/api/imports/expenses.xlsx", manager, corps=corps, content_type=ct)
    etape("10. un manager n'importe pas", 403, s, rep)
    for fmt in ("expenses.csv", "expenses.docx", "reconciliation.xlsx", "report.pdf"):
        s, rep, entetes = api("GET", f"/api/exports/{fmt}?year={annee}&month=4&country={togo['id']}", admin, brut=True)
        etape(f"10. export {fmt} par mois", 200, s, rep[:60])
    s, rep, _ = api("GET", f"/api/exports/expenses.csv?year={annee}", dm, brut=True)
    etape("10. le DM n'exporte pas", 403, s, rep[:60])
    s, audit, _ = api("GET", "/api/audit/?action=downloaded&page_size=3", admin)
    etape("10. journal d'audit : export tracé", 200, s, audit)
    if s == 200 and audit["count"] == 0:
        rapport.append(("10. entrée downloaded présente", "KO", "-", ">0", ""))

    # 11. Lectures par rôle, dans les deux langues, alertes
    for role, jeton in (("manager", manager), ("dm", dm), ("df", df), ("admin", admin), ("super_admin", siege)):
        for chemin, attendu in ((f"/api/dashboard/?year={annee}", 200), ("/api/expenses/register/?page_size=5", 200),
                                ("/api/history/?page_size=5", 403 if role == "manager" else 200),
                                ("/api/audit/?page_size=5", 403 if role in ("manager", "dm", "df") else 200)):
            s, rep, _ = api("GET", chemin, jeton)
            etape(f"11. {role} lit {chemin.split('?')[0]}", attendu, s, rep)
    fr = api("GET", f"/api/dossiers/{dossier['id']}/", df, lang="fr")[1]
    en = api("GET", f"/api/dossiers/{dossier['id']}/", df, lang="en")[1]
    etape(f"11. libellés traduits : « {fr['status_display']} » / « {en['status_display']} »", True,
          fr["status_display"] != en["status_display"])
    s, rep, _ = api("POST", f"/api/expenses/{lignes[0]['id']}/justify/", manager, lang="en")
    etape(f"11. refus traduit en anglais : {rep}", 403, s, rep)
    alertes = subprocess.run(COMPOSE + ["exec", "-T", "backend", "python", "manage.py", "notify_alerts"],
                             cwd=RACINE, capture_output=True, text=True)
    etape("11. notify_alerts : " + (alertes.stdout.strip().splitlines() or ["(silencieux)"])[-1][:100], 0,
          alertes.returncode, alertes.stderr[-200:])

    ko = [r for r in rapport if r[1] == "KO"]
    for nom, verdict, statut, attendu, detail in rapport:
        print(f"{verdict}  {nom}" + ("" if verdict == "OK" else f"  → {statut} (attendu {attendu}) {detail}"))
    print(f"\n{len(rapport) - len(ko)} étapes OK, {len(ko)} KO")
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
