-- Schéma « bi » : le BI de pilotage (Grafana) lit ces vues, et rien d'autre
-- (décision 122). Elles reprennent, à la lettre, les définitions du serveur
-- — budget/aggregates.py, reporting/scope.py, reporting/alerts.py — et des
-- tests de parité (reporting/tests/test_bi.py) le vérifient : le BI ne
-- recalcule pas autrement, il lit autrement.
--
-- Ce fichier est un gabarit : `reporting.bi` y remplace les jetons (entre
-- doubles arobases) par
-- les ensembles de statuts, les libellés et le fuseau du serveur, tirés du
-- code Python — une seule source. Il est rejoué après chaque migration
-- (signal post_migrate) ; les vues sont retirées avant (pre_migrate), pour
-- qu'aucune ne bloque un changement de colonne.
--
-- Jamais exposé : mots de passe, jetons, secrets de double authentification,
-- sessions, adresses IP, téléphones et e-mails des bénéficiaires.

CREATE SCHEMA IF NOT EXISTS bi;
COMMENT ON SCHEMA bi IS 'BI de pilotage JUSTI GH : vues en lecture seule (décision 122).';

-- Arrondi « au pair », celui de Decimal.quantize (ROUND_HALF_EVEN) : round()
-- de PostgreSQL arrondit les moitiés loin de zéro, et un centime d'écart
-- avec l'application suffirait à faire douter d'un tableau.
CREATE FUNCTION bi.arrondi(x numeric, n integer) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE
    WHEN x IS NULL THEN NULL
    WHEN abs(x * power(10::numeric, n) - trunc(x * power(10::numeric, n))) = 0.5
      THEN round(
        (trunc(x * power(10::numeric, n))
          + CASE WHEN mod(trunc(x * power(10::numeric, n)), 2) = 0 THEN 0 ELSE sign(x) END)
        / power(10::numeric, n), n)
    ELSE round(x, n)
  END
$$;

-- Rapport arrondi à quatre décimales, NULL sans dénominateur
-- (aggregates._ratio).
CREATE FUNCTION bi.ratio(numerateur numeric, denominateur numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN coalesce(denominateur, 0) = 0 THEN NULL
              ELSE bi.arrondi(numerateur / denominateur, 4) END
$$;

-- « Aujourd'hui » du serveur : timezone.localdate(), dans TIME_ZONE.
CREATE FUNCTION bi.aujourd_hui() RETURNS date
LANGUAGE sql STABLE AS $$ SELECT (now() AT TIME ZONE '@@FUSEAU_SERVEUR@@')::date $$;

-- Date à laquelle un exercice se consolide : le 31 décembre d'un exercice
-- clos, aujourd'hui sinon (aggregates.date_de_reference).
CREATE FUNCTION bi.date_de_reference(annee integer) RETURNS date
LANGUAGE sql STABLE AS $$ SELECT least(make_date(annee, 12, 31), bi.aujourd_hui()) $$;

-- Niveau d'exécution d'un taux (aggregates.niveau_d_execution).
CREATE FUNCTION bi.niveau(taux numeric, seuil numeric) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN taux IS NULL THEN 'ok'
              WHEN taux > 1 THEN 'exceeded'
              WHEN taux >= seuil / 100 THEN 'warning'
              ELSE 'ok' END
$$;

CREATE FUNCTION bi.libelle_niveau(niveau text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE niveau WHEN 'exceeded' THEN 'Dépassé'
                     WHEN 'warning' THEN 'À surveiller'
                     ELSE 'Normal' END
$$;

-- Libellés français des codes, tirés des choix des modèles.
CREATE FUNCTION bi.libelle_statut(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_STATUT@@ $$;
CREATE FUNCTION bi.libelle_paiement(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_PAIEMENT@@ $$;
CREATE FUNCTION bi.libelle_beneficiaire(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_BENEFICIAIRE@@ $$;
CREATE FUNCTION bi.libelle_piece(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_TYPE_PIECE@@ $$;
CREATE FUNCTION bi.libelle_etat_piece(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_ETAT_PIECE@@ $$;
CREATE FUNCTION bi.libelle_action(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_ACTION@@ $$;
CREATE FUNCTION bi.libelle_role(code text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT @@CASE_ROLE@@ $$;

-- Paramètres de la politique (WorkflowConfiguration, défauts du modèle
-- si la ligne n'existe pas encore).
CREATE VIEW bi.parametres AS
SELECT
  coalesce(
    (SELECT max(v.valeur)
       FROM jsonb_array_elements(coalesce(w.alert_thresholds, '@@SEUILS_DEFAUT@@'::jsonb)) AS e(x)
       CROSS JOIN LATERAL (
         SELECT CASE WHEN jsonb_typeof(e.x) = 'number' THEN e.x::text::numeric END AS valeur
       ) AS v
      WHERE v.valeur < 100),
    @@SEUIL_PAR_DEFAUT@@) AS seuil_alerte,
  coalesce(w.alert_thresholds, '@@SEUILS_DEFAUT@@'::jsonb) AS seuils,
  coalesce(w.unusual_expense_factor, @@FACTEUR_DEFAUT@@) AS facteur_inhabituel,
  coalesce(w.unjustified_alert_days, 0) AS delai_alerte_jours,
  coalesce(w.suppressions_ouvertes, false) AS corbeille_ouverte
FROM (SELECT 1) AS un
LEFT JOIN core_workflowconfiguration AS w ON w.id = 1;

-- Pays, avec un fuseau que PostgreSQL connaît (scope.fuseau_de : UTC à défaut).
CREATE VIEW bi.pays AS
SELECT c.id, c.name AS nom, c.code, c.country_ref AS reference, c.currency AS devise,
       c.currency_symbol AS symbole, c.is_active AS actif,
       CASE WHEN c.timezone IN (SELECT name FROM pg_timezone_names) THEN c.timezone
            ELSE 'UTC' END AS fuseau
FROM core_country AS c;

-- Taux de change publiés, et leur période de validité.
CREATE VIEW bi.taux AS
SELECT r.id, r.currency AS devise, r.rate_to_xof AS taux_xof, r.valid_from AS depuis,
       lead(r.valid_from) OVER (PARTITION BY r.currency ORDER BY r.valid_from, r.id) AS jusqu_a,
       r.created_at AS publie_le
FROM budget_exchangerate AS r;

-- Enveloppes actives et leur consommation (aggregates.budget_figures,
-- alerts.budget_alerts). Une ligne pèse sur l'enveloppe à laquelle elle est
-- imputée ; les réallocations approuvées sont déjà dans le montant.
CREATE VIEW bi.enveloppes AS
WITH conso AS (
  SELECT e.budget_id,
         coalesce(sum(e.amount) FILTER (WHERE e.status IN (@@ENGAGES@@)), 0) AS engage,
         coalesce(sum(e.amount) FILTER (WHERE e.status IN (@@CONSOMMES@@)), 0) AS consomme,
         coalesce(sum(e.justified_amount) FILTER (WHERE e.status IN (@@CONSOMMES@@)), 0) AS justifie
    FROM expenses_expense AS e
   WHERE e.budget_id IS NOT NULL
   GROUP BY e.budget_id
), base AS (
  SELECT b.id, b.year AS annee, b.country_id AS pays_id, c.nom AS pays, c.devise,
         CASE WHEN b.project_id IS NOT NULL THEN 'projet'
              WHEN b.team_id IS NOT NULL THEN 'equipe'
              WHEN b.manager_id IS NOT NULL THEN 'manager'
              ELSE 'pays' END AS portee,
         coalesce(p.name, t.name, m.name, c.nom) AS cible,
         b.project_id AS projet_id, p.reference AS reference_projet,
         b.team_id AS equipe_id, b.manager_id,
         b.amount AS montant, b.overrun_policy AS politique_depassement,
         coalesce(x.engage, 0.00) AS engage,
         coalesce(x.consomme, 0.00) AS consomme,
         coalesce(x.justifie, 0.00) AS justifie
    FROM budget_budget AS b
    JOIN bi.pays AS c ON c.id = b.country_id
    LEFT JOIN core_project AS p ON p.id = b.project_id
    LEFT JOIN core_team AS t ON t.id = b.team_id
    LEFT JOIN core_manager AS m ON m.id = b.manager_id
    LEFT JOIN conso AS x ON x.budget_id = b.id
   WHERE b.is_active
), calcul AS (
  SELECT base.*,
         base.consomme - base.justifie AS ecart,
         base.montant - base.consomme - base.engage AS disponible,
         bi.ratio(base.consomme + base.engage, base.montant) AS taux_execution,
         bi.ratio(base.justifie, base.consomme) AS taux_justification,
         CASE WHEN base.montant = 0 THEN NULL
              ELSE bi.arrondi((base.consomme + base.engage) / base.montant * 100, 1) END
           AS pourcentage_utilise,
         bi.date_de_reference(base.annee) AS date_reference,
         CASE WHEN base.devise = '@@DEVISE_CONSOLIDATION@@' THEN 1::numeric ELSE (
           SELECT r.rate_to_xof FROM budget_exchangerate AS r
            WHERE r.currency = base.devise AND r.valid_from <= bi.date_de_reference(base.annee)
            ORDER BY r.valid_from DESC, r.id DESC LIMIT 1) END AS taux_xof
    FROM base
)
SELECT calcul.*,
       bi.niveau(calcul.taux_execution, prm.seuil_alerte) AS niveau_execution,
       bi.libelle_niveau(bi.niveau(calcul.taux_execution, prm.seuil_alerte)) AS libelle_niveau,
       CASE WHEN calcul.consomme + calcul.engage > calcul.montant THEN 'budget_overrun'
            WHEN calcul.montant = 0 THEN NULL
            WHEN seuil.atteint IS NOT NULL THEN 'budget_threshold' END AS alerte,
       CASE WHEN calcul.consomme + calcul.engage > calcul.montant THEN 'critical'
            WHEN calcul.montant = 0 OR seuil.atteint IS NULL THEN NULL
            WHEN seuil.atteint >= 100 THEN 'critical' ELSE 'warning' END AS gravite,
       seuil.atteint AS seuil_atteint,
       CASE WHEN calcul.consomme + calcul.engage > calcul.montant
            THEN calcul.consomme + calcul.engage - calcul.montant END AS depassement,
       bi.arrondi(calcul.montant * calcul.taux_xof, 2) AS montant_xof,
       bi.arrondi(calcul.engage * calcul.taux_xof, 2) AS engage_xof,
       bi.arrondi(calcul.consomme * calcul.taux_xof, 2) AS consomme_xof,
       bi.arrondi(calcul.justifie * calcul.taux_xof, 2) AS justifie_xof,
       bi.arrondi(calcul.ecart * calcul.taux_xof, 2) AS ecart_xof,
       bi.arrondi(calcul.disponible * calcul.taux_xof, 2) AS disponible_xof
  FROM calcul
 CROSS JOIN bi.parametres AS prm
 CROSS JOIN LATERAL (
   SELECT max(v.valeur) AS atteint
     FROM jsonb_array_elements(prm.seuils) AS s(x)
     CROSS JOIN LATERAL (
       SELECT CASE WHEN jsonb_typeof(s.x) = 'number' THEN s.x::text::numeric END AS valeur
     ) AS v
    WHERE v.valeur <= calcul.pourcentage_utilise
 ) AS seuil;

-- Consolidation par pays et par exercice (aggregates.consolidation_par_pays).
CREATE VIEW bi.consolidation_pays AS
WITH somme AS (
  SELECT pays_id, pays, devise, annee,
         coalesce(sum(montant) FILTER (WHERE portee = 'pays'), 0.00) AS attribue_pays,
         coalesce(sum(montant) FILTER (WHERE portee <> 'pays'), 0.00) AS sous_enveloppes,
         sum(engage) AS engage, sum(consomme) AS consomme, sum(justifie) AS justifie,
         count(*) AS enveloppes,
         count(*) FILTER (WHERE alerte = 'budget_overrun') AS enveloppes_depassees
    FROM bi.enveloppes
   GROUP BY pays_id, pays, devise, annee
), calcul AS (
  SELECT somme.*,
         CASE WHEN attribue_pays = 0 AND sous_enveloppes <> 0 THEN sous_enveloppes
              ELSE attribue_pays END AS attribue
    FROM somme
), indicateurs AS (
  SELECT calcul.*,
         consomme - justifie AS ecart,
         attribue - sous_enveloppes AS non_reparti,
         attribue - (consomme + engage) AS disponible,
         bi.ratio(consomme + engage, attribue) AS taux_execution,
         bi.ratio(justifie, consomme) AS taux_justification,
         bi.date_de_reference(annee) AS date_reference,
         CASE WHEN devise = '@@DEVISE_CONSOLIDATION@@' THEN 1::numeric ELSE (
           SELECT r.rate_to_xof FROM budget_exchangerate AS r
            WHERE r.currency = calcul.devise AND r.valid_from <= bi.date_de_reference(calcul.annee)
            ORDER BY r.valid_from DESC, r.id DESC LIMIT 1) END AS taux_xof
    FROM calcul
)
SELECT i.pays_id, i.pays, i.devise, i.annee, i.enveloppes, i.enveloppes_depassees,
       i.attribue, i.sous_enveloppes, i.engage, i.consomme, i.justifie, i.ecart,
       i.non_reparti, i.disponible, i.taux_execution,
       bi.niveau(i.taux_execution, prm.seuil_alerte) AS niveau_execution,
       bi.libelle_niveau(bi.niveau(i.taux_execution, prm.seuil_alerte)) AS libelle_niveau,
       i.taux_justification, i.date_reference, i.taux_xof,
       bi.arrondi(i.attribue * i.taux_xof, 2) AS attribue_xof,
       bi.arrondi(i.sous_enveloppes * i.taux_xof, 2) AS sous_enveloppes_xof,
       bi.arrondi(i.engage * i.taux_xof, 2) AS engage_xof,
       bi.arrondi(i.consomme * i.taux_xof, 2) AS consomme_xof,
       bi.arrondi(i.justifie * i.taux_xof, 2) AS justifie_xof,
       bi.arrondi(i.ecart * i.taux_xof, 2) AS ecart_xof,
       bi.arrondi(i.disponible * i.taux_xof, 2) AS disponible_xof
  FROM indicateurs AS i
 CROSS JOIN bi.parametres AS prm;

-- Consolidé en FCFA par exercice : les pays sans taux sont exclus et
-- nommés, jamais comptés pour zéro.
CREATE VIEW bi.consolidation AS
SELECT annee,
       coalesce(sum(attribue_xof), 0.00) AS attribue_xof,
       coalesce(sum(sous_enveloppes_xof), 0.00) AS sous_enveloppes_xof,
       coalesce(sum(engage_xof), 0.00) AS engage_xof,
       coalesce(sum(consomme_xof), 0.00) AS consomme_xof,
       coalesce(sum(justifie_xof), 0.00) AS justifie_xof,
       coalesce(sum(ecart_xof), 0.00) AS ecart_xof,
       coalesce(sum(disponible_xof), 0.00) AS disponible_xof,
       bi.ratio(coalesce(sum(consomme_xof), 0) + coalesce(sum(engage_xof), 0),
                coalesce(sum(attribue_xof), 0)) AS taux_execution,
       bi.niveau(bi.ratio(coalesce(sum(consomme_xof), 0) + coalesce(sum(engage_xof), 0),
                          coalesce(sum(attribue_xof), 0)),
                 (SELECT seuil_alerte FROM bi.parametres)) AS niveau_execution,
       bi.ratio(coalesce(sum(justifie_xof), 0), coalesce(sum(consomme_xof), 0)) AS taux_justification,
       coalesce(array_agg(DISTINCT devise ORDER BY devise) FILTER (WHERE taux_xof IS NULL),
                '{}'::text[]) AS devises_non_converties,
       count(*) AS pays,
       count(*) FILTER (WHERE taux_xof IS NULL) AS pays_non_convertis
  FROM bi.consolidation_pays
 GROUP BY annee;

-- Une ligne de dépense par enregistrement, brouillons compris (le statut
-- dit ce qui compte). Dates au fuseau du pays, comme l'exercice de la ligne
-- (expenses.services.exercice) ; montant en FCFA au taux de la date de
-- référence de son exercice.
CREATE VIEW bi.lignes AS
WITH preuves AS (
  SELECT pr.expense_id, pr.dossier_id
    FROM expenses_proof AS pr
   WHERE pr.status NOT IN (@@PIECES_INUTILISABLES@@)
), lignes AS (
  SELECT e.*, c.nom AS pays, c.devise, c.fuseau,
         (e.date AT TIME ZONE c.fuseau) AS date_locale
    FROM expenses_expense AS e
    JOIN bi.pays AS c ON c.id = e.country_id
)
SELECT l.id, l.dossier_id, d.number AS numero_dossier, d.label AS libelle_dossier,
       l.country_id AS pays_id, l.pays, l.devise,
       l.date AS date_utc, l.date_locale,
       l.date_locale::date AS jour,
       extract(year FROM l.date_locale)::integer AS annee,
       date_trunc('month', l.date_locale)::date AS mois,
       extract(isodow FROM l.date_locale)::integer AS jour_semaine,
       l.status AS statut, bi.libelle_statut(l.status) AS libelle_statut,
       l.status = '@@BROUILLON@@' AS brouillon,
       l.status IN (@@ENGAGES@@) AS engagee,
       l.status IN (@@CONSOMMES@@) AS consommee,
       l.amount AS montant, l.justified_amount AS justifie,
       l.amount - l.justified_amount AS ecart,
       taux.taux_xof,
       bi.arrondi(l.amount * taux.taux_xof, 2) AS montant_xof,
       bi.arrondi(l.justified_amount * taux.taux_xof, 2) AS justifie_xof,
       l.project_id AS projet_id, p.name AS projet, p.reference AS reference_projet,
       dp.id AS projet_dossier_id, dp.name AS projet_dossier, dp.reference AS reference_projet_dossier,
       dp.kind AS type_projet_code,
       pt.name AS type_projet, d.kind_id AS type_dossier_id, dk.name AS type_dossier,
       l.team_id AS equipe_id, t.name AS equipe,
       l.owner_id AS manager_id, m.name AS manager,
       l.marketing_category_id AS categorie_id, mc.name AS categorie,
       l.expense_title_id AS intitule_id, et.label AS intitule,
       l.beneficiary_id AS beneficiaire_id, bf.name AS beneficiaire,
       bf.kind AS type_beneficiaire_code, bi.libelle_beneficiaire(bf.kind) AS type_beneficiaire,
       l.title AS libelle, l.place AS lieu,
       l.payment_method AS mode_paiement_code, bi.libelle_paiement(l.payment_method) AS mode_paiement,
       nullif(l.original_currency, '') AS devise_origine, l.original_amount AS montant_origine,
       l.budget_id AS enveloppe_id, l.created_by AS saisie_par,
       l.created_at AS saisie_le,
       (EXISTS (SELECT 1 FROM preuves AS pv WHERE pv.expense_id = l.id)
        OR EXISTS (SELECT 1 FROM preuves AS pv
                    WHERE pv.dossier_id = l.dossier_id AND pv.expense_id IS NULL)) AS a_preuve
  FROM lignes AS l
  JOIN expenses_dossier AS d ON d.id = l.dossier_id
  LEFT JOIN core_project AS p ON p.id = l.project_id
  LEFT JOIN core_project AS dp ON dp.id = d.project_id
  LEFT JOIN core_projecttype AS pt ON pt.code = dp.kind
  LEFT JOIN core_dossierkind AS dk ON dk.id = d.kind_id
  LEFT JOIN core_team AS t ON t.id = l.team_id
  LEFT JOIN core_manager AS m ON m.id = l.owner_id
  LEFT JOIN core_marketingcategory AS mc ON mc.id = l.marketing_category_id
  LEFT JOIN core_expensetitle AS et ON et.id = l.expense_title_id
  LEFT JOIN expenses_beneficiary AS bf ON bf.id = l.beneficiary_id
  CROSS JOIN LATERAL (
    SELECT CASE WHEN l.devise = '@@DEVISE_CONSOLIDATION@@' THEN 1::numeric ELSE (
      SELECT r.rate_to_xof FROM budget_exchangerate AS r
       WHERE r.currency = l.devise
         AND r.valid_from <= bi.date_de_reference(extract(year FROM l.date_locale)::integer)
       ORDER BY r.valid_from DESC, r.id DESC LIMIT 1) END AS taux_xof
  ) AS taux;

-- Étapes de chaque ligne déclarée, lues au journal d'audit : dernière
-- soumission, dernière mise en contrôle, dernier constat, clôture.
CREATE VIEW bi.delais AS
WITH etapes AS (
  SELECT a.object_id AS ligne_id,
         max(a.created_at) FILTER (WHERE a.action = 'submitted') AS soumise_le,
         max(a.created_at) FILTER (WHERE a.action = 'reviewed') AS mise_en_controle_le,
         max(a.created_at) FILTER (WHERE a.action IN ('justified', 'unjustified')) AS constatee_le,
         max(a.created_at) FILTER (WHERE a.action = 'closed') AS cloturee_le,
         count(*) FILTER (WHERE a.action = 'reopened') AS reouvertures
    FROM expenses_auditlog AS a
   WHERE a.object_type = 'Expense'
   GROUP BY a.object_id
)
SELECT l.id AS ligne_id, l.pays_id, l.pays, l.annee, l.mois, l.statut, l.libelle_statut,
       l.equipe, l.manager, l.projet_dossier, l.type_projet,
       l.date_utc AS depensee_le, et.soumise_le, et.mise_en_controle_le,
       et.constatee_le, et.cloturee_le, coalesce(et.reouvertures, 0) AS reouvertures,
       round(extract(epoch FROM et.soumise_le - l.date_utc) / 86400, 1) AS jours_depense_soumission,
       CASE WHEN et.constatee_le >= et.soumise_le
            THEN round(extract(epoch FROM et.constatee_le - et.soumise_le) / 86400, 1) END
         AS jours_soumission_constat,
       CASE WHEN l.engagee AND et.soumise_le IS NOT NULL
            THEN round(extract(epoch FROM now() - et.soumise_le) / 86400, 1) END
         AS jours_en_attente
  FROM bi.lignes AS l
  LEFT JOIN etapes AS et ON et.ligne_id = l.id
 WHERE NOT l.brouillon;

-- File de contrôle du siège : les lignes soumises ou en contrôle
-- (workload « à contrôler » du Pilotage), avec leur ancienneté.
CREATE VIEW bi.file_controle AS
SELECT d.*, l.numero_dossier, l.libelle, l.montant, l.montant_xof, l.devise, l.a_preuve
  FROM bi.delais AS d
  JOIN bi.lignes AS l ON l.id = d.ligne_id
 WHERE l.engagee;

-- Dossiers, avec leurs lignes sans preuve (Dossier.lignes_sans_preuve) et
-- l'alerte « justificatif manquant » (alerts.proof_alerts).
CREATE VIEW bi.dossiers AS
WITH utilisables AS (
  SELECT * FROM expenses_proof WHERE status NOT IN (@@PIECES_INUTILISABLES@@)
), base AS (
  SELECT d.id, d.number AS numero, d.label AS libelle, d.country_id AS pays_id,
         c.nom AS pays, c.devise, c.fuseau, d.date, extract(year FROM d.date)::integer AS annee,
         date_trunc('month', d.date)::date AS mois,
         d.status AS statut, bi.libelle_statut(d.status) AS libelle_statut,
         d.status <> '@@CLOTURE@@' AS ouvert,
         d.project_id AS projet_id, p.name AS projet, p.reference AS reference_projet,
         pt.name AS type_projet, dk.name AS type_dossier, d.predefini,
         t.name AS equipe, m.name AS manager, d.created_by AS ouvert_par,
         d.created_at AS ouvert_le,
         EXISTS (SELECT 1 FROM utilisables AS u WHERE u.dossier_id = d.id AND u.expense_id IS NULL)
           AS piece_d_avant,
         (SELECT count(*) FROM expenses_expense AS e WHERE e.dossier_id = d.id) AS lignes,
         (SELECT count(*) FROM expenses_expense AS e
           WHERE e.dossier_id = d.id
             AND NOT EXISTS (SELECT 1 FROM utilisables AS u WHERE u.expense_id = e.id))
           AS lignes_sans_piece_propre,
         (SELECT count(*) FROM expenses_proof AS pr
           WHERE pr.dossier_id = d.id AND pr.status = 'incomplete') AS pieces_incompletes,
         (SELECT coalesce(sum(e.amount), 0.00) FROM expenses_expense AS e
           WHERE e.dossier_id = d.id AND e.status IN (@@ENGAGES@@, @@CONSOMMES@@)) AS montant
    FROM expenses_dossier AS d
    JOIN bi.pays AS c ON c.id = d.country_id
    LEFT JOIN core_project AS p ON p.id = d.project_id
    LEFT JOIN core_projecttype AS pt ON pt.code = p.kind
    LEFT JOIN core_dossierkind AS dk ON dk.id = d.kind_id
    LEFT JOIN core_team AS t ON t.id = d.team_id
    LEFT JOIN core_manager AS m ON m.id = d.owner_id
)
SELECT b.*,
       CASE WHEN b.piece_d_avant THEN 0 ELSE b.lignes_sans_piece_propre END AS lignes_sans_preuve,
       CASE WHEN b.statut NOT IN (@@ENGAGES@@, @@CONSOMMES@@) THEN NULL
            WHEN prm.delai_alerte_jours > 0
             AND b.date > (now() AT TIME ZONE b.fuseau)::date - prm.delai_alerte_jours THEN NULL
            WHEN b.lignes_sans_piece_propre > 0 AND NOT b.piece_d_avant THEN 'proof_missing'
            WHEN b.pieces_incompletes > 0 THEN 'proof_incomplete' END AS alerte
  FROM base AS b
 CROSS JOIN bi.parametres AS prm;

-- Justificatifs : état, type, délai de dépôt, rejets.
CREATE VIEW bi.pieces AS
SELECT pr.id, pr.dossier_id, d.number AS numero_dossier, pr.expense_id AS ligne_id,
       d.country_id AS pays_id, c.nom AS pays,
       pr.kind AS type_code, bi.libelle_piece(pr.kind) AS type,
       pr.status AS etat_code, bi.libelle_etat_piece(pr.status) AS etat,
       pr.is_complete AS complete, pr.version, pr.replaces_id IS NOT NULL AS remplace_une_version,
       EXISTS (SELECT 1 FROM expenses_proof AS v WHERE v.replaces_id = pr.id) AS remplacee,
       pr.size AS taille, pr.content_type AS type_mime, pr.uploaded_by AS deposee_par,
       pr.created_at AS deposee_le, date_trunc('month', pr.created_at AT TIME ZONE c.fuseau)::date AS mois,
       extract(year FROM pr.created_at AT TIME ZONE c.fuseau)::integer AS annee,
       nullif(pr.rejection_reason, '') AS motif_rejet,
       CASE WHEN e.id IS NOT NULL
            THEN round(extract(epoch FROM pr.created_at - e.date) / 86400, 1) END AS jours_apres_depense
  FROM expenses_proof AS pr
  JOIN expenses_dossier AS d ON d.id = pr.dossier_id
  JOIN bi.pays AS c ON c.id = d.country_id
  LEFT JOIN expenses_expense AS e ON e.id = pr.expense_id;

-- Demandes de rectification et leur décision.
CREATE VIEW bi.rectifications AS
SELECT r.id, r.expense_id AS ligne_id, e.country_id AS pays_id, c.nom AS pays,
       r.status AS etat, CASE r.status WHEN 'pending' THEN 'En attente'
                                       WHEN 'approved' THEN 'Approuvée'
                                       WHEN 'refused' THEN 'Refusée' ELSE r.status END AS libelle_etat,
       r.requested_by AS demandee_par, r.created_at AS demandee_le,
       r.decided_by AS decidee_par, r.decided_at AS decidee_le,
       CASE WHEN r.decided_at IS NOT NULL
            THEN round(extract(epoch FROM r.decided_at - r.created_at) / 86400, 1) END AS jours_de_decision,
       r.previous_status AS statut_precedent, r.previous_justified_amount AS justifie_precedent,
       e.amount AS montant, c.devise,
       extract(year FROM r.created_at AT TIME ZONE c.fuseau)::integer AS annee
  FROM expenses_rectification AS r
  JOIN expenses_expense AS e ON e.id = r.expense_id
  JOIN bi.pays AS c ON c.id = e.country_id;

-- Réallocations entre enveloppes.
CREATE VIEW bi.reallocations AS
SELECT ra.id, ra.amount AS montant, ra.status AS etat,
       CASE ra.status WHEN 'pending' THEN 'En attente'
                      WHEN 'approved' THEN 'Approuvée'
                      WHEN 'rejected' THEN 'Refusée' ELSE ra.status END AS libelle_etat,
       ra.source_id AS enveloppe_source_id, src.year AS annee, src.country_id AS pays_id,
       c.nom AS pays, c.devise, ra.target_id AS enveloppe_cible_id,
       ra.requested_by AS demandee_par, ra.created_at AS demandee_le,
       ra.decided_by AS decidee_par, ra.decided_at AS decidee_le
  FROM budget_budgetreallocation AS ra
  JOIN budget_budget AS src ON src.id = ra.source_id
  JOIN bi.pays AS c ON c.id = src.country_id;

-- Dépenses inhabituelles (alerts.unusual_expense_alerts) : par pays et par
-- exercice, une ligne plus de « facteur » fois la moyenne des autres.
CREATE VIEW bi.inhabituelles AS
WITH stats AS (
  SELECT pays_id, annee, sum(montant) AS total, count(*) AS n
    FROM bi.lignes
   WHERE consommee
   GROUP BY pays_id, annee
)
SELECT l.id AS ligne_id, l.pays_id, l.pays, l.devise, l.annee, l.mois, l.jour,
       l.numero_dossier, l.libelle, l.statut, l.libelle_statut, l.montant, l.montant_xof,
       l.manager, l.equipe, l.beneficiaire, prm.facteur_inhabituel AS facteur,
       CASE WHEN l.consommee THEN prm.facteur_inhabituel * s.total / (s.n - 1 + prm.facteur_inhabituel)
            ELSE prm.facteur_inhabituel * s.total / s.n END AS seuil
  FROM bi.lignes AS l
  JOIN stats AS s ON s.pays_id = l.pays_id AND s.annee = l.annee
 CROSS JOIN bi.parametres AS prm
 WHERE NOT l.brouillon
   AND s.n >= 2 AND s.total <> 0
   AND l.montant > CASE WHEN l.consommee
                        THEN prm.facteur_inhabituel * s.total / (s.n - 1 + prm.facteur_inhabituel)
                        ELSE prm.facteur_inhabituel * s.total / s.n END;

-- Doublons probables : même pays, même jour, même montant, même
-- bénéficiaire (ou même libellé sans bénéficiaire), hors brouillons.
CREATE VIEW bi.doublons AS
SELECT l.pays_id, l.pays, l.devise, l.jour, l.annee, l.montant,
       coalesce(l.beneficiaire, lower(l.libelle)) AS reference,
       count(*) AS lignes, array_agg(l.id ORDER BY l.id) AS lignes_ids,
       array_agg(DISTINCT l.numero_dossier) AS dossiers
  FROM bi.lignes AS l
 WHERE NOT l.brouillon
 GROUP BY l.pays_id, l.pays, l.devise, l.jour, l.annee, l.montant,
          coalesce(l.beneficiaire, lower(l.libelle))
HAVING count(*) > 1;

-- Comptes et adoption : rôle, périmètre, dernière connexion, double
-- authentification, activité au journal. Ni mot de passe, ni jeton, ni
-- secret, ni adresse.
CREATE VIEW bi.comptes AS
SELECT u.id, u.username AS compte, u.is_active AS actif,
       pr.role, bi.libelle_role(pr.role) AS libelle_role,
       pr.totp_confirmed_at IS NOT NULL AS double_authentification,
       pr.must_change_password AS mot_de_passe_provisoire,
       u.date_joined AS cree_le, u.last_login AS derniere_connexion,
       (SELECT array_agg(c.name ORDER BY c.name)
          FROM accounts_userprofile_countries AS pc
          JOIN core_country AS c ON c.id = pc.country_id
         WHERE pc.userprofile_id = pr.id) AS pays,
       (SELECT count(*) FROM expenses_auditlog AS a
         WHERE a."user" = u.username AND a.created_at >= now() - interval '30 days') AS actions_30_jours
  FROM auth_user AS u
  JOIN accounts_userprofile AS pr ON pr.user_id = u.id;

-- Journal des actions sensibles, sans adresse ni appareil.
CREATE VIEW bi.journal AS
SELECT a.id, a.created_at AS le, a."user" AS compte, a.action,
       bi.libelle_action(a.action) AS libelle_action, a.object_type AS type_objet,
       a.object_id AS objet_id, a.label AS libelle, a.country_id AS pays_id, c.nom AS pays,
       date_trunc('day', a.created_at)::date AS jour,
       a.action IN (@@ACTIONS_SENSIBLES@@) AS sensible
  FROM expenses_auditlog AS a
  LEFT JOIN bi.pays AS c ON c.id = a.country_id;

-- Corbeille (décision 120) : ce qui a été retiré avant l'ouverture.
CREATE VIEW bi.corbeille AS
SELECT s.id, s.nature, s.reference, s.libelle, s.country_id AS pays_id, c.nom AS pays,
       s.montant, s.devise, s.racine_id IS NULL AS element_choisi,
       s.supprime_par, s.supprime_le, s.motif
  FROM expenses_elementsupprime AS s
  LEFT JOIN bi.pays AS c ON c.id = s.country_id;
