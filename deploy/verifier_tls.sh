#!/bin/sh
# Ce qu'il faut vérifier AVANT de demander un certificat à Let's Encrypt.
#
#   ./verifier_tls.sh                 # sur le serveur, avec le .env à côté
#   ./verifier_tls.sh --domaine X     # pour un autre nom que celui du .env
#
# POURQUOI CE SCRIPT EXISTE
#
# L'émission d'un certificat ne se répète pas à volonté : Let's Encrypt
# compte les échecs de validation (cinq par heure, par compte et par nom) et
# les certificats délivrés (cinq identiques par semaine). Une adresse DNS qui
# pointe ailleurs, un enregistrement CAA oublié, un pare-feu qui ferme le
# port 80 — et l'on brûle ses essais avant d'avoir compris. Ce script pose
# les questions dans l'ordre, sur la machine où la réponse se trouve.
#
# CE QU'IL NE PEUT PAS FAIRE, ET IL FAUT LE SAVOIR
#
# Personne, depuis la machine, ne peut vérifier qu'Internet l'atteint : c'est
# Let's Encrypt qui ouvre la connexion, depuis l'extérieur. Le script vérifie
# tout ce qui est vérifiable d'ici — le nom, l'adresse, le CAA, l'écoute
# locale, la sortie vers l'ACME, le certificat en place — puis donne la
# répétition à jouer sur l'environnement d'essai, qui ne compte pas dans les
# quotas.

set -eu

DOMAINE="${APP_DOMAIN:-}"
STAGING="https://acme-staging-v02.api.letsencrypt.org/directory"
PRODUCTION="https://acme-v02.api.letsencrypt.org/directory"
DEFAUTS=0
ALERTES=0

ok()     { echo "  ✔ $*"; }
alerte() { echo "  ⚠ $*"; ALERTES=$((ALERTES + 1)); }
defaut() { echo "  ✘ $*"; DEFAUTS=$((DEFAUTS + 1)); }
titre()  { echo; echo "── $* ────────────────────────────────────────────"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --domaine) DOMAINE="${2:?nom attendu}"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "option inconnue : $1 (voir --help)" >&2; exit 1 ;;
  esac
done

# Le .env du répertoire, si on ne nous a rien dit.
if [ -z "$DOMAINE" ] && [ -f "$(dirname "$0")/.env" ]; then
  DOMAINE=$(sed -n 's/^APP_DOMAIN=//p' "$(dirname "$0")/.env" | tail -1)
fi
[ -n "$DOMAINE" ] || { echo "Aucun domaine : --domaine <nom>, ou APP_DOMAIN dans .env" >&2; exit 1; }

# `http://:80` est le mode « derrière un aiguillage » : pas de TLS ici.
case "$DOMAINE" in
  http://*|https://*)
    echo "APP_DOMAIN vaut « $DOMAINE » : cette machine ne termine pas TLS."
    echo "C'est l'aiguillage qui porte le certificat — lancez ce script là-bas."
    exit 0 ;;
esac

echo "Domaine examiné : $DOMAINE"

titre "1. Le nom pointe-t-il ici ?"
adresses_dns=$(getent ahostsv4 "$DOMAINE" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')
if [ -z "$adresses_dns" ]; then
  defaut "$DOMAINE ne résout pas. Let's Encrypt ne trouvera pas la machine."
else
  ok "résout vers : $adresses_dns"
  locales=$(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | tr '\n' ' ')
  trouve=0
  for a in $adresses_dns; do
    case " $locales " in *" $a "*) trouve=1 ;; esac
  done
  if [ "$trouve" -eq 1 ]; then
    ok "l'une de ces adresses est portée par cette machine"
  else
    alerte "aucune de ces adresses n'est locale (ici : $locales).
      Normal derrière un aiguillage, une IP flottante ou un NAT — le port 80
      doit alors être redirigé vers cette machine. Anormal sinon : le défi
      HTTP-01 arrivera chez quelqu'un d'autre."
  fi
fi

titre "2. Un enregistrement CAA interdit-il Let's Encrypt ?"
lire_caa() {
  if command -v dig >/dev/null 2>&1; then
    dig +short CAA "$1" 2>/dev/null | grep -v '^$' || true
  else
    # `host` est présent là où `dig` manque ; il dit « has no CAA record »
    # quand il n'y en a pas, d'où le filtre.
    host -t CAA "$1" 2>/dev/null | grep -i 'issue' || true
  fi
}

if command -v dig >/dev/null 2>&1 || command -v host >/dev/null 2>&1; then
  nom="$DOMAINE"
  caa=""
  while [ -n "$nom" ] && [ -z "$caa" ]; do
    caa=$(lire_caa "$nom")
    [ -n "$caa" ] && break
    nom=$(echo "$nom" | cut -s -d. -f2-)
  done
  if [ -z "$caa" ]; then
    ok "aucun CAA : toute autorité peut délivrer (défaut du DNS)"
  elif echo "$caa" | grep -q 'letsencrypt\.org'; then
    ok "CAA sur $nom autorise letsencrypt.org"
  else
    defaut "CAA sur $nom n'autorise PAS letsencrypt.org :
      $(echo "$caa" | tr '\n' ' ')
      L'émission échouera, quoi que fasse le serveur."
  fi
else
  alerte "ni dig ni host : le CAA n'a pas pu être vérifié (apt install dnsutils).
      Un CAA qui n'autorise pas letsencrypt.org fait échouer l'émission sans
      que rien, sur le serveur, ne l'explique."
fi

titre "3. Qui écoute sur le port 80 ?"
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':80 '; then
  ok "quelque chose écoute sur :80"
  entetes=$(curl -sS -o /dev/null -D - -w '%{http_code}' --max-time 5 \
            -H "Host: $DOMAINE" "http://127.0.0.1/.well-known/acme-challenge/essai" 2>/dev/null) || entetes=""
  reponse=$(printf '%s' "$entetes" | tail -1)
  [ -n "$reponse" ] || reponse=000
  # Hors émission, Caddy redirige ce chemin comme le reste (308) ; pendant une
  # émission, il sert le jeton. Un 404 vaut aussi : ce sont deux réponses
  # saines. Ce qui compte, c'est **qui** répond — d'où l'en-tête `Server`.
  case "$reponse" in
    000) defaut "rien ne répond en local sur :80" ;;
    308|301|302|404) ok "le port 80 répond ($reponse) — attendu hors émission" ;;
    *)   alerte "le chemin du défi répond $reponse. Inhabituel : vérifiez
      qu'aucun autre serveur n'occupe le port 80." ;;
  esac
  if printf '%s' "$entetes" | grep -qi '^server:.*caddy'; then
    ok "c'est bien Caddy qui répond sur :80"
  elif [ "$reponse" != "000" ]; then
    alerte "la réponse ne vient pas de Caddy (en-tête « Server » absent ou
      différent). Un autre serveur sur le port 80 répondrait à la place, et la
      validation échouerait sans que Caddy le sache."
  fi
else
  defaut "personne n'écoute sur :80. Let's Encrypt valide par là (HTTP-01)."
fi

titre "4. La machine joint-elle Let's Encrypt ?"
for cible in "$STAGING essai" "$PRODUCTION production"; do
  url=${cible% *}; quoi=${cible#* }
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null) || code=""
  [ -n "$code" ] || code=000
  if [ "$code" = "200" ]; then
    ok "$quoi joignable"
  else
    defaut "$quoi injoignable (code $code). Un pare-feu sortant, un mandataire
      d'entreprise ou une politique de sortie bloque l'ACME : aucun certificat
      ne sera obtenu, et le message de Caddy ne le dira pas si clairement."
  fi
done

titre "5. Quel certificat est servi aujourd'hui ?"
if command -v openssl >/dev/null 2>&1; then
  cert=$(echo | openssl s_client -connect "127.0.0.1:443" -servername "$DOMAINE" 2>/dev/null | openssl x509 -noout -issuer -enddate 2>/dev/null || true)
  if [ -z "$cert" ]; then
    alerte "aucun certificat servi en local sur :443 (pile arrêtée, ou pas encore émis)"
  else
    emetteur=$(echo "$cert" | sed -n 's/^issuer=//p')
    echeance=$(echo "$cert" | sed -n 's/^notAfter=//p')
    echo "      émetteur : $emetteur"
    echo "      expire   : $echeance"
    if echo "$emetteur" | grep -qi 'let'; then
      ok "délivré par Let's Encrypt"
    elif echo "$emetteur" | grep -qi 'staging\|fake'; then
      alerte "certificat d'ESSAI : les navigateurs le refuseront.
      Retirez le réglage d'essai (« acme_ca ») et relancez Caddy."
    else
      alerte "émetteur inattendu. Caddy se replie sur son autorité interne
      quand l'ACME échoue : le site répond en TLS, et tous les navigateurs
      refusent. C'est la panne qu'on ne voit pas depuis le serveur."
    fi
    if command -v date >/dev/null 2>&1 && date -d "$echeance" +%s >/dev/null 2>&1; then
      reste=$(( ( $(date -d "$echeance" +%s) - $(date +%s) ) / 86400 ))
      [ "$reste" -lt 30 ] && alerte "expire dans $reste jours ; Caddy renouvelle à 30 jours" || ok "expire dans $reste jours"
    fi
  fi
else
  alerte "openssl absent : le certificat en place n'a pas pu être lu"
fi

titre "Ce que le script n'a pas pu vérifier"
cat <<'TEXTE'
  Qu'Internet atteint cette machine sur le port 80. C'est Let's Encrypt qui
  ouvre la connexion, depuis l'extérieur : aucune commande lancée ici ne peut
  le prouver. Faites-le vérifier depuis un autre réseau :

      curl -sS -o /dev/null -w '%{http_code}\n' http://<le domaine>/.well-known/acme-challenge/essai
      # 404 attendu. « connection refused » ou un délai : le port est fermé.

  RÉPÉTITION AVANT LA PREMIÈRE ÉMISSION — les quotas ne pardonnent pas :
  cinq validations échouées par heure et par nom, cinq certificats identiques
  par semaine. L'environnement d'essai de Let's Encrypt n'en consomme aucun.

      # dans deploy/Caddyfile, dans le bloc global, le temps de l'essai :
      #   acme_ca https://acme-staging-v02.api.letsencrypt.org/directory
      docker compose -f docker-compose.prod.yml up -d caddy
      docker compose -f docker-compose.prod.yml logs -f caddy   # « certificate obtained »
      # puis RETIREZ la ligne, supprimez le certificat d'essai et relancez :
      docker compose -f docker-compose.prod.yml exec caddy \
          rm -rf /data/caddy/certificates/acme-staging-v02.api.letsencrypt.org-directory
      docker compose -f docker-compose.prod.yml restart caddy
TEXTE

titre "Bilan"
echo "  défauts : $DEFAUTS · alertes : $ALERTES"
[ "$DEFAUTS" -eq 0 ] || { echo "  Corrigez les défauts avant de demander un certificat."; exit 1; }
[ "$ALERTES" -eq 0 ] && echo "  Rien ne s'oppose à l'émission depuis cette machine." || echo "  Lisez les alertes : certaines sont normales derrière un aiguillage."
