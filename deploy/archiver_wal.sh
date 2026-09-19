#!/bin/sh
# Archivage d'un segment de journal de transaction (WAL).
#
#   archiver_wal.sh <chemin_du_segment> <nom_du_segment>
#
# Appelé par Postgres lui-même, une fois par segment rempli, via
# `archive_command` (deploy/docker-compose.prod.yml). C'est ce qui permet la
# reprise à un instant donné : le dump quotidien dit où l'on était à 02:00,
# les segments disent tout ce qui s'est passé depuis.
#
# CE QUE CE SCRIPT DOIT GARANTIR, et pourquoi chaque règle compte :
#
#   1. Ne jamais rendre 0 sans avoir écrit le segment en entier. Postgres
#      considère un segment archivé comme recyclable : mentir ici, c'est
#      perdre le segment, et avec lui la continuité de la reprise.
#   2. Ne jamais écraser un segment déjà archivé par un contenu différent.
#      La documentation de Postgres en fait une obligation : deux segments
#      de même nom et de contenu différent signalent un désordre grave
#      (deux grappes qui archivent au même endroit, une restauration mal
#      menée) qu'il vaut mieux refuser que résoudre en silence.
#   3. Écrire ailleurs puis renommer. Un segment à moitié écrit qu'une
#      restauration croirait complet est pire que pas de segment du tout.
#   4. Échouer bruyamment. Postgres réessaie indéfiniment ; le compteur
#      d'échecs de `pg_stat_archiver` est relevé par
#      `manage.py verifier_sauvegardes`, qui prévient les administrateurs.
#
# LE DANGER À CONNAÎTRE. Tant que l'archivage échoue, Postgres **conserve**
# ses segments dans `pg_wal` : ils s'accumulent, et un archivage cassé
# pendant assez longtemps remplit le disque de la base — donc l'arrête.
# C'est le prix de la garantie 1 : Postgres préfère s'arrêter que perdre.
# D'où la surveillance, qui n'est pas un ornement : voir
# `manage.py verifier_sauvegardes` et deploy/README.md, « Reprise à un
# instant donné ».
#
# CHIFFREMENT. Un segment contient les mêmes données qu'un dump : lignes,
# jetons, secrets TOTP. Si SAUVEGARDE_CLE_PUBLIQUE est renseignée, le
# segment est chiffré au vol (openssl smime, AES-256) comme les dumps, et
# ne touche jamais le disque en clair. Sinon il est écrit tel quel, comme
# les dumps le sont alors — voir l'en-tête de sauvegarder.sh, « ce qui est
# chiffré, et ce qui ne l'est pas ».

set -u

SEGMENT_SOURCE="${1:-}"
SEGMENT_NOM="${2:-}"
DESTINATION="${SAUVEGARDE_DESTINATION:-/sauvegardes}/base/wal"
CLE_PUBLIQUE="${SAUVEGARDE_CLE_PUBLIQUE:-}"
SUFFIXE_CHIFFRE=".enc"

journal() { echo "$(date -u +%FT%TZ) archivage-wal $*"; }
echec() { journal "✘ $*" >&2; exit 1; }

[ -n "$SEGMENT_SOURCE" ] && [ -n "$SEGMENT_NOM" ] \
  || echec "usage : archiver_wal.sh <chemin> <nom>"
[ -f "$SEGMENT_SOURCE" ] || echec "segment introuvable : $SEGMENT_SOURCE"

# Un nom de segment est fait de caractères hexadécimaux, ou porte un suffixe
# connu (.backup, .history, .partial). Tout le reste vient d'ailleurs que de
# Postgres et n'a rien à faire ici — un nom qui contiendrait « / » ou « .. »
# écrirait hors de la destination.
case "$SEGMENT_NOM" in
  *[!0-9A-Za-z._-]*) echec "nom de segment refusé : $SEGMENT_NOM" ;;
  ..*|"") echec "nom de segment refusé : $SEGMENT_NOM" ;;
esac

mkdir -p "$DESTINATION" || echec "destination inaccessible : $DESTINATION"

cible="$DESTINATION/$SEGMENT_NOM"
[ -n "$CLE_PUBLIQUE" ] && cible="$cible$SUFFIXE_CHIFFRE"

# Règle 2 : déjà archivé, on ne touche à rien. Postgres rappellera le même
# segment après une restauration ou un redémarrage ; c'est normal, et le
# refuser en erreur ferait boucler l'archivage sur un segment déjà en
# sûreté. On rend donc 0 — mais seulement si le contenu concorde.
if [ -e "$cible" ]; then
  if [ -z "$CLE_PUBLIQUE" ]; then
    if cmp -s "$SEGMENT_SOURCE" "$cible"; then
      journal "déjà archivé, identique : $SEGMENT_NOM"
      exit 0
    fi
    echec "$SEGMENT_NOM existe déjà avec un contenu différent : archivage refusé. Deux grappes archivent-elles au même endroit ?"
  fi
  # Chiffré, on ne peut pas comparer : deux chiffrements du même segment
  # donnent deux fichiers différents. On accepte donc le nom comme preuve.
  # C'est le seul endroit où ce script fait confiance sans vérifier, et le
  # risque est borné : deux segments de même nom dans la même lignée
  # temporelle ont le même contenu, sauf si deux grappes archivent au même
  # endroit — une erreur de configuration que la surveillance verra à la
  # divergence des compteurs, pas ici.
  journal "déjà archivé (chiffré), conservé : $SEGMENT_NOM"
  exit 0
fi

partiel="$cible.partiel"
rm -f "$partiel"

if [ -n "$CLE_PUBLIQUE" ]; then
  [ -s "$CLE_PUBLIQUE" ] \
    || echec "SAUVEGARDE_CLE_PUBLIQUE=$CLE_PUBLIQUE introuvable ou vide : segment non archivé"
  if ! openssl smime -encrypt -binary -aes-256-cbc -outform DER \
        -in "$SEGMENT_SOURCE" -out "$partiel" "$CLE_PUBLIQUE"; then
    rm -f "$partiel"
    echec "chiffrement impossible : $SEGMENT_NOM non archivé"
  fi
else
  if ! cp "$SEGMENT_SOURCE" "$partiel"; then
    rm -f "$partiel"
    echec "copie impossible : $SEGMENT_NOM non archivé"
  fi
fi

# Le renommage est atomique sur un même système de fichiers : le segment
# apparaît d'un coup, complet, ou pas du tout.
if ! mv "$partiel" "$cible"; then
  rm -f "$partiel"
  echec "renommage impossible : $SEGMENT_NOM non archivé"
fi

# Une demande de copie hors machine, comme pour les dumps : le service
# `sauvegarde-distante` la consomme dans la minute. Son échec n'invalide
# pas l'archivage, qui est fait — on rend 0 pour que Postgres puisse
# recycler le segment.
demandes="${SAUVEGARDE_DESTINATION:-/sauvegardes}/.distant"
mkdir -p "$demandes" 2>/dev/null && : > "$demandes/demande-wal" 2>/dev/null

exit 0
