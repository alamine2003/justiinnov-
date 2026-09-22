#!/bin/sh
# Chronomètre de bascule : ce qu'un utilisateur voit, seconde par seconde.
#
#   ./chronometrer_bascule.sh https://justi-innov.innovpharma.net
#   ./chronometrer_bascule.sh https://justi-innov.innovpharma.net --duree 600
#
# À LANCER D'AILLEURS — d'un poste, pas d'une des deux machines — avant de
# couper la primaire, et à laisser tourner jusqu'à la fin de la répétition.
# Il interroge /api/health/ chaque seconde et n'écrit une ligne que quand
# quelque chose change : le code, ou la machine qui répond. À la fin, il
# donne les durées qui comptent.
#
# CE QU'IL MESURE, ET CE QUE LE BANC A DONNÉ (docs/audit-resilience.md §9)
#
#   1. la perte : première erreur après la coupure     — immédiate
#   2. la reprise : premier 200 après la promotion     — 4,8 s
#   3. LE RETOUR DE L'ANCIENNE PRIMAIRE, si on la rallume telle quelle :
#      le trafic y est revenu 5,1 s après, sur une base périmée. Si vous
#      voyez la colonne « machine » revenir à « 1 » après la promotion de
#      « 2 », vous venez de voir la seule panne que rien n'empêche.
#
# La colonne « machine » vient de SERVEUR_NOM (.env de chaque machine) ;
# sans lui, elle reste vide et seul le code d'état renseigne.

set -u

URL="${1:?URL attendue, ex. https://justi-innov.innovpharma.net}"
shift
DUREE=900
while [ $# -gt 0 ]; do
  case "$1" in
    --duree) DUREE="${2:?secondes attendues}"; shift 2 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "option inconnue : $1" >&2; exit 1 ;;
  esac
done

SONDE="${URL%/}/api/health/"
debut=$(date +%s)
etat=""
premier_defaut=""
dernier_defaut=""
indispo_total=0
depuis_defaut=""
machines=""

echo "chronomètre sur $SONDE — $DUREE s, une ligne par changement (Ctrl-C pour arrêter)"
printf '%-10s %-6s %-8s %s\n' "t (s)" "code" "machine" "corps"

while [ $(( $(date +%s) - debut )) -lt "$DUREE" ]; do
  maintenant=$(date +%s)
  corps=$(curl -sS -o - -w '\n%{http_code}' --max-time 4 "$SONDE" 2>/dev/null) || corps="
000"
  code=$(printf '%s' "$corps" | tail -n 1)
  json=$(printf '%s' "$corps" | sed '$d')
  machine=$(printf '%s' "$json" | sed -n 's/.*"machine":"\([^"]*\)".*/\1/p')
  cle="$code/$machine"

  if [ "$cle" != "$etat" ]; then
    t=$(( maintenant - debut ))
    printf '%-10s %-6s %-8s %s\n' "+$t" "$code" "${machine:--}" "$(printf '%s' "$json" | cut -c1-70)"
    etat="$cle"
    # La SUITE des machines, pas l'ensemble : « 1 2 1 » est précisément ce
    # qu'il faut voir — l'ancienne primaire qui reprend après la seconde.
    if [ -n "$machine" ]; then
      case "$machines" in *" $machine") ;; *) machines="$machines $machine" ;; esac
    fi
    if [ "$code" != "200" ] && [ -z "$depuis_defaut" ]; then
      depuis_defaut=$maintenant
      [ -n "$premier_defaut" ] || premier_defaut=$t
    elif [ "$code" = "200" ] && [ -n "$depuis_defaut" ]; then
      indispo_total=$(( indispo_total + maintenant - depuis_defaut ))
      dernier_defaut=$t
      depuis_defaut=""
    fi
  fi
  sleep 1
done
[ -n "$depuis_defaut" ] && indispo_total=$(( indispo_total + $(date +%s) - depuis_defaut ))

echo
echo "── bilan ──────────────────────────────────────────────"
echo "  machines, dans l'ordre :${machines:- aucune (SERVEUR_NOM non réglé ?)}"
if [ -n "$premier_defaut" ]; then echo "  première erreur        : +$premier_defaut s"; else echo "  première erreur        : aucune"; fi
if [ -n "$dernier_defaut" ]; then echo "  service rétabli        : +$dernier_defaut s"; else echo "  service rétabli        : —"; fi
echo "  indisponibilité        : $indispo_total s cumulées"
# Une machine qui revient APRÈS qu'une autre a servi : « … 2 1 », « … 1 2 ».
precedentes=""
for m in $machines; do
  case " $precedentes " in
    *" $m "*)
      echo
      echo "  ⚠ LA MACHINE « $m » A REPRIS LE TRAFIC APRÈS EN AVOIR ÉTÉ ÉCARTÉE."
      echo "    Si c'est l'ancienne primaire rallumée telle quelle, elle sert une"
      echo "    base périmée : coupez-la (docker compose down) et refaites-la en"
      echo "    réplique (preparer_replique.sh). Voir promouvoir_replique.sh."
      break ;;
  esac
  precedentes="$precedentes $m"
done
