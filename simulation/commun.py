"""Ce que les deux scripts partagent : comptes, TOTP, multipart, Compose."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE = ["docker", "compose"] + sum(
    (["-f", f] for f in os.environ.get("SIM_COMPOSE", "docker-compose.yml docker-compose.ci.yml").split()), []
)


def comptes():
    chemin = os.environ.get("SIM_COMPTES")
    if not chemin:
        raise SystemExit("SIM_COMPTES doit désigner le fichier JSON des comptes jetables (voir simulation/README.md).")
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def code_totp(secret):
    """Code TOTP courant, calculé par pyotp dans le conteneur backend."""
    return subprocess.run(
        COMPOSE + ["exec", "-T", "backend", "python", "-c",
                   "import pyotp,sys;print(pyotp.TOTP(sys.argv[1]).now())", secret],
        cwd=RACINE, capture_output=True, text=True,
    ).stdout.strip()


def multipart(champs, fichier, mime="application/pdf"):
    frontiere = "----JustiSimulation" + uuid.uuid4().hex
    parts = [f"--{frontiere}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n".encode()
             for n, v in champs.items()]
    nom, contenu = fichier
    parts.append(f"--{frontiere}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nom}\"\r\n"
                 f"Content-Type: {mime}\r\n\r\n".encode() + contenu + b"\r\n")
    parts.append(f"--{frontiere}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={frontiere}"


def pdf(marque):
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n% " + marque.encode()
            + b"\nxref\n0 1\ntrailer<</Size 1/Root 1 0 R>>\nstartxref\n0\n%%EOF\n")
