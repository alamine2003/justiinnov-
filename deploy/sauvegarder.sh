#!/bin/sh
# Sauvegarde nocturne de la pile, exécutée par trois services de
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
#   sauvegarder.sh distant  dans `sauvegarde-distante` (image rclone) :
#                           copie hors machine, vers un stockage objet S3
#                           (SAUVEGARDE_DISTANT_*). Les deux premiers
#                           déposent une demande dans .distant/ après
#                           chaque sauvegarde réussie ; celui-ci la lit
#                           dans la minute, envoie ce qui manque au distant
#                           (rclone copy, incrémental : rien n'est jamais
#                           effacé là-bas hors rotation des quotidiens),
#                           vérifie la copie (rclone check) et journalise
#                           « ✔ copie distante » ou « ✘ ». Une demande qui
#                           échoue reste en place et est retentée un quart
#                           d'heure plus tard. Sans SAUVEGARDE_DISTANT_ENDPOINT,
#                           rien ne part et le journal le dit à chaque fois.
#
# Disposition du distant (bucket, ou bucket/sous-dossier) :
#   quotidien/<base>-<horodatage>.dump   même rotation que base/
#   mensuel/<base>-<AAAA-MM>.dump        jamais supprimé
#   pieces/…                             miroir des justificatifs
#
# Sans autre argument, le script tourne indéfiniment : `base` et `pieces` se
# réveillent chaque jour à SAUVEGARDE_HEURE (UTC, 02:00 par défaut),
# `distant` guette les demandes. Avec `--une-fois`, il sauvegarde (ou copie)
# tout de suite et sort — code 0 si tout a été écrit, non nul sinon — pour
# un test, ou juste avant une opération risquée :
#
#   docker compose -f docker-compose.prod.yml run --rm sauvegarde --une-fois
#   docker compose -f docker-compose.prod.yml run --rm sauvegarde-distante --une-fois
#
# (l'entrypoint du service porte déjà `base`, `pieces` ou `distant`).
# Le mode `distant` sait aussi `--lister` le distant et `--rapatrier <nom>`
# ou `--rapatrier-pieces` : c'est ce qu'appelle restaurer.sh.
#
# Chaque étape est enchaînée explicitement et vérifie son résultat : `set -e`
# ne protège pas une fonction appelée dans un `if` ou derrière `||`, et
# c'est ainsi qu'un pg_dump raté laissait autrefois un fichier vide
# renommé en `.dump`, puis lié comme copie mensuelle « pour toujours ».
# Désormais : un échec supprime le `.partiel`, un fichier vide est refusé,
# et rien n'est lié tant que le dump n'est pas complet et non vide.
#
# La restauration est dans restaurer.sh ; voir README.md, « Sauvegardes et
# restauration ».
set -u

quoi="${1:?usage : sauvegarder.sh base|pieces|distant [--une-fois|--lister|--rapatrier <nom>|--rapatrier-pieces]}"
shift
action="${1:-}"
[ $# -gt 0 ] && shift

DESTINATION="${SAUVEGARDE_DESTINATION:-/sauvegardes}"
HEURE="${SAUVEGARDE_HEURE:-02:00}"
RETENTION_JOURS="${SAUVEGARDE_RETENTION_JOURS:-30}"
DEMANDES="$DESTINATION/.distant"
DISTANT_ENDPOINT="${SAUVEGARDE_DISTANT_ENDPOINT:-}"
# Une copie distante qui a échoué (réseau, quota, clé révoquée) est
# retentée après ce délai, pas toutes les minutes.
REESSAI_SECONDES=900

horodatage() { date -u +%Y-%m-%dT%H%M%SZ; }
journal() { echo "$(date -u +%FT%TZ) $*"; }
echec() { journal "✘ $*" >&2; return 1; }

# --- Copie hors machine : côté demandeur -----------------------------------

distant_configure() { [ -n "$DISTANT_ENDPOINT" ]; }

avertir_si_sans_distant() {
  if ! distant_configure; then
    journal "⚠ AUCUNE COPIE HORS MACHINE : SAUVEGARDE_DISTANT_ENDPOINT est vide. Les sauvegardes restent sur ce serveur ; une machine perdue les emporte. Renseignez SAUVEGARDE_DISTANT_* dans .env (README.md, « Copie hors machine »)." >&2
  fi
}

# Après une sauvegarde réussie : un fichier vide dans .distant/, que le
# service `sauvegarde-distante` consomme. Il est écrit même sans distant
# configuré : le jour où il l'est, la demande en attente part avec tout ce
# qui manque. Un échec ici n'invalide pas la sauvegarde, qui est écrite.
demander_copie_distante() {
  if mkdir -p "$DEMANDES" && : > "$DEMANDES/demande-$1"; then
    if distant_configure; then
      journal "copie distante demandée ($1) : le service sauvegarde-distante s'en charge"
    else
      journal "✘ copie distante impossible ($1) : SAUVEGARDE_DISTANT_ENDPOINT vide — la sauvegarde reste sur cette machine seulement" >&2
    fi
  else
    journal "⚠ demande de copie distante non écrite ($DEMANDES) : lancez « sauvegarde-distante --une-fois »" >&2
  fi
}

# --- Base ---------------------------------------------------------------------

sauvegarder_base() {
  base="${PGDATABASE:-justi_innov}"
  mkdir -p "$DESTINATION/base/mensuel" || return 1
  fichier="$DESTINATION/base/$base-$(horodatage).dump"
  partiel="$fichier.partiel"

  # Écriture dans un fichier temporaire puis renommage : un dump interrompu
  # ne laisse pas de fichier à moitié écrit qu'on croirait complet.
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump -Fc --file "$partiel" "$DATABASE_URL"
  else
    pg_dump -Fc --file "$partiel"
  fi
  if [ $? -ne 0 ]; then
    rm -f "$partiel"
    echec "pg_dump a échoué : aucun dump écrit pour $base"
    return 1
  fi
  # Un dump vide n'est pas une sauvegarde : pg_dump peut créer le fichier
  # avant d'échouer, et l'on refuse de le renommer, et plus encore de le
  # lier comme copie mensuelle.
  if [ ! -s "$partiel" ]; then
    rm -f "$partiel"
    echec "dump vide refusé : $partiel (base $base injoignable ou sans droit ?)"
    return 1
  fi
  if ! mv "$partiel" "$fichier"; then
    rm -f "$partiel"
    echec "impossible de renommer $partiel en $fichier"
    return 1
  fi
  journal "base sauvegardée : $fichier ($(du -h "$fichier" | cut -f1))"

  # Copie mensuelle, conservée pour toujours : le premier dump réussi du
  # mois — le 1er en temps normal, plus tard si la sauvegarde du 1er a
  # échoué — est lié en dur dans base/mensuel/ (une copie si le lien est
  # impossible). Elle reste quand le quotidien part en rotation. Le dump
  # vient d'être vérifié non vide : c'est la condition pour arriver ici.
  mensuel="$DESTINATION/base/mensuel/$base-$(date -u +%Y-%m).dump"
  if [ ! -f "$mensuel" ]; then
    if ln "$fichier" "$mensuel" 2>/dev/null || cp "$fichier" "$mensuel"; then
      journal "copie mensuelle conservée sans limite : $mensuel"
    else
      # Le quotidien est bon ; la copie mensuelle sera tentée avec le
      # prochain dump réussi du mois. On le dit, sans invalider la nuit.
      journal "⚠ copie mensuelle non écrite ($mensuel) : sera retentée à la prochaine sauvegarde"
    fi
  fi

  # Rotation des quotidiens seulement (`-maxdepth 1` épargne mensuel/) :
  # les dumps plus vieux que la rétention partent. `-mtime +N` signifie
  # « strictement plus de N jours ».
  supprimes=$(find "$DESTINATION/base" -maxdepth 1 -name '*.dump' -mtime +"$RETENTION_JOURS" -print -delete | wc -l)
  if [ "$supprimes" -gt 0 ]; then
    journal "rotation : $supprimes dump(s) quotidien(s) de plus de $RETENTION_JOURS jours supprimé(s)"
  fi
  # Restes d'un passage interrompu brutalement (conteneur tué en plein dump).
  rm -f "$DESTINATION"/base/*.partiel

  demander_copie_distante base
  return 0
}

# --- Pièces -------------------------------------------------------------------

sauvegarder_pieces() {
  mkdir -p "$DESTINATION/pieces" || return 1
  export MC_CONFIG_DIR="${MC_CONFIG_DIR:-/tmp/mc}"
  bucket="pile/${AWS_STORAGE_BUCKET_NAME:-justificatifs}"
  if ! mc --quiet alias set pile "${AWS_S3_ENDPOINT_URL:-http://minio:9000}" \
      "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" >/dev/null; then
    echec "stockage injoignable (${AWS_S3_ENDPOINT_URL:-http://minio:9000}) : miroir non fait"
    return 1
  fi
  if ! mc --quiet mirror --overwrite "$bucket" "$DESTINATION/pieces"; then
    echec "mc mirror a échoué sur $bucket : le miroir est peut-être incomplet"
    return 1
  fi
  journal "pièces mises en miroir dans $DESTINATION/pieces ($(du -sh "$DESTINATION/pieces" | cut -f1))"

  demander_copie_distante pieces
  return 0
}

# --- Copie hors machine : côté rclone -------------------------------------------
#
# Le distant est déclaré à rclone par l'environnement (RCLONE_CONFIG_DISTANT_*),
# sans fichier de configuration : rien n'est écrit sur disque. Le secret
# vient de SAUVEGARDE_DISTANT_SECRET ou, de préférence, du secret Compose
# monté dans /run/secrets/sauvegarde_distant_secret.

distant_preparer() {
  secret="${SAUVEGARDE_DISTANT_SECRET:-}"
  if [ -z "$secret" ] && [ -s /run/secrets/sauvegarde_distant_secret ]; then
    secret="$(cat /run/secrets/sauvegarde_distant_secret)"
  fi
  if [ -z "${SAUVEGARDE_DISTANT_BUCKET:-}" ] || [ -z "${SAUVEGARDE_DISTANT_CLE:-}" ] || [ -z "$secret" ]; then
    echec "copie distante mal configurée : SAUVEGARDE_DISTANT_BUCKET, SAUVEGARDE_DISTANT_CLE et SAUVEGARDE_DISTANT_SECRET doivent être renseignés avec SAUVEGARDE_DISTANT_ENDPOINT"
    return 1
  fi
  export RCLONE_CONFIG_DISTANT_TYPE=s3
  export RCLONE_CONFIG_DISTANT_PROVIDER="${SAUVEGARDE_DISTANT_FOURNISSEUR:-Other}"
  export RCLONE_CONFIG_DISTANT_ENDPOINT="$DISTANT_ENDPOINT"
  export RCLONE_CONFIG_DISTANT_ACCESS_KEY_ID="$SAUVEGARDE_DISTANT_CLE"
  export RCLONE_CONFIG_DISTANT_SECRET_ACCESS_KEY="$secret"
  export RCLONE_CONFIG_DISTANT_REGION="${SAUVEGARDE_DISTANT_REGION:-}"
  export RCLONE_CONFIG_DISTANT_ENV_AUTH=false
  # Pas de fichier de configuration : tout vient de l'environnement, et
  # rclone n'a rien à écrire.
  export RCLONE_CONFIG=/dev/null
  # Deux envois en parallèle, morceaux de 8 Mo, deux morceaux en vol par
  # envoi : au plus ~32 Mo de tampons, sous le mem_limit du service. Pas de
  # statistiques périodiques dans le journal : seules les erreurs comptent.
  # Chaque réglage se surcharge par la variable rclone du même nom.
  export RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-2}" RCLONE_CHECKERS="${RCLONE_CHECKERS:-4}"
  export RCLONE_STATS="${RCLONE_STATS:-0}" RCLONE_RETRIES="${RCLONE_RETRIES:-3}"
  export RCLONE_S3_CHUNK_SIZE="${RCLONE_S3_CHUNK_SIZE:-8M}"
  export RCLONE_S3_UPLOAD_CONCURRENCY="${RCLONE_S3_UPLOAD_CONCURRENCY:-2}"
  CIBLE="distant:${SAUVEGARDE_DISTANT_BUCKET}"
  return 0
}

# Copie puis vérification d'un dossier. rclone copy n'efface jamais rien
# sur le distant et vérifie la somme de chaque fichier transféré ;
# `rclone check --one-way` confirme ensuite que chaque fichier local est
# bien là-bas, à l'identique. Pour les dumps, `--checksum` : la comparaison
# se fait sur la somme MD5 et non sur taille + date, si bien qu'une copie
# distante altérée (même taille, même date) est renvoyée puis revérifiée,
# au lieu d'être signalée chaque nuit sans être réparée. Pour les pièces,
# `--size-only` : ne pas relire des giga-octets chaque nuit alors que
# chaque transfert a déjà été vérifié à l'envoi.
copier_et_verifier() {
  source="$1"; cible="$2"; shift 2
  rclone copy "$source" "$cible" "$@" || return 1
  rclone check --one-way "$source" "$cible" "$@" || return 1
  return 0
}

copier_base_distant() {
  distant_preparer || return 1
  quotidiens=$(find "$DESTINATION/base" -maxdepth 1 -name '*.dump' 2>/dev/null | wc -l)
  mensuels=$(find "$DESTINATION/base/mensuel" -maxdepth 1 -name '*.dump' 2>/dev/null | wc -l)
  if [ "$quotidiens" -eq 0 ] && [ "$mensuels" -eq 0 ]; then
    journal "copie distante (base) : aucun dump à copier"
    return 0
  fi
  if [ "$quotidiens" -gt 0 ]; then
    # `--max-depth 1` épargne mensuel/, `--include` écarte un .partiel.
    if ! copier_et_verifier "$DESTINATION/base" "$CIBLE/quotidien" --checksum --max-depth 1 --include '*.dump'; then
      echec "copie distante (base) : les dumps quotidiens ne sont pas tous vérifiés sur $CIBLE/quotidien"
      return 1
    fi
  fi
  if [ "$mensuels" -gt 0 ]; then
    if ! copier_et_verifier "$DESTINATION/base/mensuel" "$CIBLE/mensuel" --checksum --include '*.dump'; then
      echec "copie distante (base) : les copies mensuelles ne sont pas toutes vérifiées sur $CIBLE/mensuel"
      return 1
    fi
  fi
  journal "✔ copie distante (base) : $quotidiens dump(s) quotidien(s) et $mensuels mensuel(s) présents et vérifiés sur $CIBLE"
  # Même rotation que sur la machine, sur quotidien/ seulement : mensuel/
  # est un autre préfixe, cette commande ne peut pas y toucher. Elle ne
  # supprime que ce qui est plus vieux que la rétention : un volume local
  # vide ou tout neuf ne fait rien effacer là-bas.
  if ! rclone delete "$CIBLE/quotidien" --min-age "${RETENTION_JOURS}d"; then
    journal "⚠ rotation distante non faite sur $CIBLE/quotidien : sera retentée à la prochaine copie"
  fi
  return 0
}

copier_pieces_distant() {
  distant_preparer || return 1
  if [ ! -d "$DESTINATION/pieces" ]; then
    journal "copie distante (pièces) : pas encore de miroir dans $DESTINATION/pieces"
    return 0
  fi
  fichiers=$(find "$DESTINATION/pieces" -type f | wc -l)
  if [ "$fichiers" -eq 0 ]; then
    journal "copie distante (pièces) : miroir vide, rien à copier"
    return 0
  fi
  if ! copier_et_verifier "$DESTINATION/pieces" "$CIBLE/pieces" --size-only; then
    echec "copie distante (pièces) : le miroir n'est pas entièrement vérifié sur $CIBLE/pieces"
    return 1
  fi
  journal "✔ copie distante (pièces) : $fichiers fichier(s) présents et vérifiés sur $CIBLE/pieces"
  return 0
}

# Une demande à la fois ; consommée si la copie a réussi, laissée en place
# sinon pour être retentée. Sans distant configuré, la demande est consommée
# avec un ✘ : la prochaine copie réussie reprendra de toute façon tout ce
# qui manque.
traiter_demande() {
  d="$1"
  if ! distant_configure; then
    rm -f "$DEMANDES/demande-$d"
    journal "✘ copie distante non faite ($d) : SAUVEGARDE_DISTANT_ENDPOINT vide — la sauvegarde reste sur cette machine seulement" >&2
    return 0
  fi
  if "copier_${d}_distant"; then
    rm -f "$DEMANDES/demande-$d"
    return 0
  fi
  return 1
}

copier_tout_distant() {
  distant_configure || { echec "copie distante non faite : SAUVEGARDE_DISTANT_ENDPOINT vide"; return 1; }
  resultat=0
  copier_base_distant || resultat=1
  copier_pieces_distant || resultat=1
  [ "$resultat" -eq 0 ] && rm -f "$DEMANDES"/demande-base "$DEMANDES"/demande-pieces
  return $resultat
}

lister_distant() {
  distant_configure || { echo "(aucune copie hors machine : SAUVEGARDE_DISTANT_ENDPOINT vide)"; return 0; }
  distant_preparer || return 1
  echo "Dumps quotidiens sur $CIBLE/quotidien :"
  rclone lsl "$CIBLE/quotidien" 2>/dev/null | grep . || echo "(aucun)"
  echo "Copies mensuelles sur $CIBLE/mensuel, à désigner par mensuel/<nom> :"
  rclone lsl "$CIBLE/mensuel" 2>/dev/null | grep . || echo "(aucune)"
  echo "Pièces sur $CIBLE/pieces :"
  rclone size "$CIBLE/pieces" 2>/dev/null || echo "(aucune)"
  return 0
}

# Rapatrie un dump du distant dans le volume, là où restaurer.sh l'attend.
# rclone vérifie la somme du fichier reçu ; on refuse en plus un fichier
# vide, et le nom n'accepte pas d'autre chemin que mensuel/.
rapatrier_dump() {
  nom="$1"
  distant_configure || { echec "rapatriement impossible : SAUVEGARDE_DISTANT_ENDPOINT vide"; return 1; }
  distant_preparer || return 1
  case "$nom" in
    mensuel/*) source="$CIBLE/$nom"; local_="$DESTINATION/base/$nom" ;;
    */*|"") echec "nom attendu : <nom>.dump ou mensuel/<nom>.dump (voir --lister)"; return 1 ;;
    *) source="$CIBLE/quotidien/$nom"; local_="$DESTINATION/base/$nom" ;;
  esac
  mkdir -p "$(dirname "$local_")" || return 1
  # rclone copyto ne se plaint pas d'une source absente : c'est l'absence
  # (ou la vacuité) du fichier reçu qui le dit.
  if ! rclone copyto "$source" "$local_" || [ ! -s "$local_" ]; then
    rm -f "$local_"
    echec "rapatriement impossible : $source introuvable, illisible ou vide (voir --lister)"
    return 1
  fi
  journal "✔ dump rapatrié : $local_ ($(du -h "$local_" | cut -f1)), somme vérifiée par rclone"
  return 0
}

rapatrier_pieces() {
  distant_configure || { echec "rapatriement impossible : SAUVEGARDE_DISTANT_ENDPOINT vide"; return 1; }
  distant_preparer || return 1
  mkdir -p "$DESTINATION/pieces" || return 1
  if ! copier_et_verifier "$CIBLE/pieces" "$DESTINATION/pieces" --size-only; then
    echec "rapatriement des pièces incomplet depuis $CIBLE/pieces"
    return 1
  fi
  journal "✔ pièces rapatriées dans $DESTINATION/pieces ($(find "$DESTINATION/pieces" -type f | wc -l) fichier(s))"
  return 0
}

# --- Ordonnancement -------------------------------------------------------------

sauvegarder() {
  case "$quoi" in
    base) sauvegarder_base ;;
    pieces) sauvegarder_pieces ;;
    distant) copier_tout_distant ;;
    *) echo "✘ argument inconnu : $quoi (attendu : base, pieces ou distant)" >&2; exit 2 ;;
  esac
}

# Secondes jusqu'à la prochaine occurrence de HEURE, en UTC.
attente_jusqua_l_heure() {
  maintenant=$(date -u +%s)
  cible=$(date -u -d "$(date -u +%Y-%m-%d) $HEURE:00" +%s)
  [ "$cible" -le "$maintenant" ] && cible=$((cible + 86400))
  echo $((cible - maintenant))
}

case "$quoi" in
  base|pieces|distant) ;;
  *) echo "✘ argument inconnu : $quoi (attendu : base, pieces ou distant)" >&2; exit 2 ;;
esac

# Sous-commandes du mode distant, appelées par restaurer.sh.
if [ "$quoi" = "distant" ]; then
  case "$action" in
    --lister) lister_distant; exit $? ;;
    --rapatrier) rapatrier_dump "${1:?nom du dump après --rapatrier}"; exit $? ;;
    --rapatrier-pieces) rapatrier_pieces; exit $? ;;
  esac
fi

if [ "$action" = "--une-fois" ]; then
  avertir_si_sans_distant
  if sauvegarder; then
    exit 0
  fi
  journal "✘ la sauvegarde ($quoi) a échoué, voir ci-dessus" >&2
  exit 1
elif [ -n "$action" ]; then
  echo "✘ option inconnue : $action" >&2
  exit 2
fi

avertir_si_sans_distant

if [ "$quoi" = "distant" ]; then
  journal "service de copie distante démarré : guette $DEMANDES, cible ${DISTANT_ENDPOINT:-(aucune)}"
  mkdir -p "$DEMANDES"
  while true; do
    attente=60
    for d in base pieces; do
      if [ -f "$DEMANDES/demande-$d" ]; then
        if ! traiter_demande "$d"; then
          journal "✘ la copie distante ($d) a échoué, voir ci-dessus ; nouvel essai dans $((REESSAI_SECONDES / 60)) min" >&2
          attente=$REESSAI_SECONDES
        fi
      fi
    done
    sleep "$attente"
  done
fi

journal "service de sauvegarde ($quoi) démarré : chaque jour à $HEURE UTC vers $DESTINATION"
while true; do
  attente=$(attente_jusqua_l_heure)
  journal "prochaine sauvegarde dans $((attente / 3600)) h $(((attente % 3600) / 60)) min"
  sleep "$attente"
  # Une sauvegarde qui échoue (base indisponible, disque plein) est
  # journalisée et n'arrête pas le service : la suivante retentera. Le
  # « ✘ » dans le journal est ce que l'exploitation doit surveiller.
  if ! sauvegarder; then
    journal "✘ la sauvegarde ($quoi) a échoué, voir ci-dessus" >&2
  fi
done
