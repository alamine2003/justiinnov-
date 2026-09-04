#!/bin/sh
# Sauvegarde nocturne de la pile, exécutée par deux services de
# docker-compose.prod.yml qui partagent le volume `sauvegardes` :
#
#   sauvegarder.sh base     dans `sauvegarde` (image postgres) : pg_dump -Fc
#                           de la base, un fichier par nuit dans base/,
#                           rotation à SAUVEGARDE_RETENTION_JOURS (30 par
#                           défaut) ; le premier dump de chaque mois est
#                           copié dans base/mensuel/, où rien n'est jamais
#                           supprimé — la conservation est illimitée.
#   sauvegarder.sh pieces   dans `sauvegarde-pieces` (image minio/mc) :
#                           miroir du bucket des justificatifs. Sans
#                           `--remove` : un objet effacé du bucket reste
#                           dans la copie, c'est le but d'une sauvegarde.
#
# Sans autre argument, le script tourne indéfiniment et se réveille chaque
# jour à SAUVEGARDE_HEURE (UTC, 02:00 par défaut). Avec `--une-fois`, il
# sauvegarde tout de suite et sort — pour un test, ou juste avant une
# opération risquée :
#
#   docker compose -f docker-compose.prod.yml run --rm sauvegarde --une-fois
#
# (l'entrypoint du service porte déjà `base` ou `pieces`).
#
# La restauration est dans restaurer.sh. Ce script ne copie rien hors de la
# machine : voir README.md, « Sauvegardes et restauration ».
set -eu

quoi="${1:?usage : sauvegarder.sh base|pieces [--une-fois]}"
shift
une_fois=0
[ "${1:-}" = "--une-fois" ] && une_fois=1

DESTINATION="${SAUVEGARDE_DESTINATION:-/sauvegardes}"
HEURE="${SAUVEGARDE_HEURE:-02:00}"
RETENTION_JOURS="${SAUVEGARDE_RETENTION_JOURS:-30}"

horodatage() { date -u +%Y-%m-%dT%H%M%SZ; }
journal() { echo "$(date -u +%FT%TZ) $*"; }

sauvegarder_base() {
  mkdir -p "$DESTINATION/base"
  fichier="$DESTINATION/base/${PGDATABASE:-justi_innov}-$(horodatage).dump"
  # Écriture dans un fichier temporaire puis renommage : un dump interrompu
  # ne laisse pas de fichier à moitié écrit qu'on croirait complet.
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump -Fc --file "$fichier.partiel" "$DATABASE_URL"
  else
    pg_dump -Fc --file "$fichier.partiel"
  fi
  mv "$fichier.partiel" "$fichier"
  journal "base sauvegardée : $fichier ($(du -h "$fichier" | cut -f1))"

  # Copie mensuelle, conservée pour toujours : le premier dump réussi du
  # mois — le 1er en temps normal, plus tard si la sauvegarde du 1er a
  # échoué — est lié en dur dans base/mensuel/ (une copie si le lien est
  # impossible). Elle reste quand le quotidien part en rotation.
  mkdir -p "$DESTINATION/base/mensuel"
  mensuel="$DESTINATION/base/mensuel/${PGDATABASE:-justi_innov}-$(date -u +%Y-%m).dump"
  if [ ! -f "$mensuel" ]; then
    ln "$fichier" "$mensuel" 2>/dev/null || cp "$fichier" "$mensuel"
    journal "copie mensuelle conservée sans limite : $mensuel"
  fi

  # Rotation des quotidiens seulement (`-maxdepth 1` épargne mensuel/) :
  # les dumps plus vieux que la rétention partent. `-mtime +N` signifie
  # « strictement plus de N jours ».
  supprimes=$(find "$DESTINATION/base" -maxdepth 1 -name '*.dump' -mtime +"$RETENTION_JOURS" -print -delete | wc -l)
  [ "$supprimes" -gt 0 ] && journal "rotation : $supprimes dump(s) quotidien(s) de plus de $RETENTION_JOURS jours supprimé(s)"
  rm -f "$DESTINATION"/base/*.partiel
}

sauvegarder_pieces() {
  mkdir -p "$DESTINATION/pieces"
  export MC_CONFIG_DIR="${MC_CONFIG_DIR:-/tmp/mc}"
  mc --quiet alias set pile "${AWS_S3_ENDPOINT_URL:-http://minio:9000}" \
    "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" >/dev/null
  mc --quiet mirror --overwrite "pile/${AWS_STORAGE_BUCKET_NAME:-justificatifs}" \
    "$DESTINATION/pieces"
  journal "pièces mises en miroir dans $DESTINATION/pieces ($(du -sh "$DESTINATION/pieces" | cut -f1))"
}

sauvegarder() {
  case "$quoi" in
    base) sauvegarder_base ;;
    pieces) sauvegarder_pieces ;;
    *) echo "✘ argument inconnu : $quoi (attendu : base ou pieces)" >&2; exit 2 ;;
  esac
}

# Secondes jusqu'à la prochaine occurrence de HEURE, en UTC.
attente_jusqua_l_heure() {
  maintenant=$(date -u +%s)
  cible=$(date -u -d "$(date -u +%Y-%m-%d) $HEURE:00" +%s)
  [ "$cible" -le "$maintenant" ] && cible=$((cible + 86400))
  echo $((cible - maintenant))
}

if [ "$une_fois" -eq 1 ]; then
  sauvegarder
  exit 0
fi

journal "service de sauvegarde ($quoi) démarré : chaque jour à $HEURE UTC vers $DESTINATION"
while true; do
  attente=$(attente_jusqua_l_heure)
  journal "prochaine sauvegarde dans $((attente / 3600)) h $(((attente % 3600) / 60)) min"
  sleep "$attente"
  # Une sauvegarde qui échoue (base indisponible, disque plein) est
  # journalisée et n'arrête pas le service : la suivante retentera.
  sauvegarder || journal "✘ la sauvegarde ($quoi) a échoué, voir ci-dessus"
done
