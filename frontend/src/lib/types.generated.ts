// Généré par scripts/generer-types.mts depuis docs/api/schema.json.
// Ne pas modifier à la main : `npm run types:api` régénère ce fichier,
// et la CI refuse une version qui ne correspondrait plus au schéma.
export interface paths {
    "/api/audit/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Journal d'audit — consultation par la RH, qui audite, et la direction.
         *
         *     Le DM et le DF n'y ont pas accès : le journal relit leurs propres
         *     décisions, et cette relecture est un acte d'administration.
         */
        get: operations["audit_list"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/audit/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Journal d'audit — consultation par la RH, qui audite, et la direction.
         *
         *     Le DM et le DF n'y ont pas accès : le journal relit leurs propres
         *     décisions, et cette relecture est un acte d'administration.
         */
        get: operations["audit_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/beneficiaries/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Prospects, clients, fournisseurs et bénéficiaires d'un pays.
         *
         *     Le référentiel était commun : un pays lisait les fournisseurs et les
         *     prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
         *     Il est cloisonné comme le reste — et tenu par la RH, comme le reste du
         *     référentiel : le manager choisit un bénéficiaire, il n'en invente pas.
         */
        get: operations["beneficiaries_list"]
        put?: never
        /**
         * @description Prospects, clients, fournisseurs et bénéficiaires d'un pays.
         *
         *     Le référentiel était commun : un pays lisait les fournisseurs et les
         *     prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
         *     Il est cloisonné comme le reste — et tenu par la RH, comme le reste du
         *     référentiel : le manager choisit un bénéficiaire, il n'en invente pas.
         */
        post: operations["beneficiaries_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/beneficiaries/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Prospects, clients, fournisseurs et bénéficiaires d'un pays.
         *
         *     Le référentiel était commun : un pays lisait les fournisseurs et les
         *     prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
         *     Il est cloisonné comme le reste — et tenu par la RH, comme le reste du
         *     référentiel : le manager choisit un bénéficiaire, il n'en invente pas.
         */
        get: operations["beneficiaries_retrieve"]
        /**
         * @description Prospects, clients, fournisseurs et bénéficiaires d'un pays.
         *
         *     Le référentiel était commun : un pays lisait les fournisseurs et les
         *     prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
         *     Il est cloisonné comme le reste — et tenu par la RH, comme le reste du
         *     référentiel : le manager choisit un bénéficiaire, il n'en invente pas.
         */
        put: operations["beneficiaries_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /**
         * @description Prospects, clients, fournisseurs et bénéficiaires d'un pays.
         *
         *     Le référentiel était commun : un pays lisait les fournisseurs et les
         *     prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
         *     Il est cloisonné comme le reste — et tenu par la RH, comme le reste du
         *     référentiel : le manager choisit un bénéficiaire, il n'en invente pas.
         */
        patch: operations["beneficiaries_partial_update"]
        trace?: never
    }
    "/api/budgets/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Enveloppes annuelles et sous-enveloppes par projet. */
        get: operations["budgets_list"]
        put?: never
        /** @description Enveloppes annuelles et sous-enveloppes par projet. */
        post: operations["budgets_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/budgets/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Enveloppes annuelles et sous-enveloppes par projet. */
        get: operations["budgets_retrieve"]
        /** @description Enveloppes annuelles et sous-enveloppes par projet. */
        put: operations["budgets_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Enveloppes annuelles et sous-enveloppes par projet. */
        patch: operations["budgets_partial_update"]
        trace?: never
    }
    "/api/budgets/summary/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Consolidation par pays, avec total en FCFA (§5.6).
         *
         *     Porte sur **une** année : celle de ``?year=``, sinon l'année en cours.
         *     Sans ce garde-fou, l'absence de paramètre additionnait toutes les
         *     années d'un même pays comme s'il s'agissait d'une seule enveloppe.
         */
        get: operations["budgets_summary_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/configuration/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Paramètres du back-office.
         *
         *     Deux origines : l'environnement, figé au démarrage (stockage, courriel,
         *     fuseau), et la politique du workflow, modifiable en base. Les exposer
         *     ensemble permet de vérifier ce qui tourne réellement, sans se fier au
         *     fichier de configuration qu'on croit déployé.
         */
        get: operations["configuration_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/cost-centers/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["cost_centers_list"]
        put?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        post: operations["cost_centers_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/cost-centers/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["cost_centers_retrieve"]
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        put: operations["cost_centers_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        patch: operations["cost_centers_partial_update"]
        trace?: never
    }
    "/api/countries/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description CRUD des pays + activation/désactivation + historique. */
        get: operations["countries_list"]
        put?: never
        /** @description CRUD des pays + activation/désactivation + historique. */
        post: operations["countries_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/countries/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description CRUD des pays + activation/désactivation + historique. */
        get: operations["countries_retrieve"]
        /** @description CRUD des pays + activation/désactivation + historique. */
        put: operations["countries_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description CRUD des pays + activation/désactivation + historique. */
        patch: operations["countries_partial_update"]
        trace?: never
    }
    "/api/countries/disponibles/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Pays africains que la plateforme ne suit pas encore.
         *
         *     Le formulaire de création propose cette liste plutôt que de laisser
         *     deviner un code ISO : une faute de frappe se traduisait par un refus
         *     sans que rien n'indique quels codes sont acceptés. La liste vit côté
         *     serveur, là où la validation s'applique — la recopier dans le frontend
         *     la ferait diverger.
         */
        get: operations["countries_disponibles_list"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dashboard/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Vue de pilotage : consolidation, répartition par pays et alertes. */
        get: operations["dashboard_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dashboard/breakdown/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Répartition d'un pays par équipe, propriétaire, projet, catégorie et mois. */
        get: operations["dashboard_breakdown_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Dossiers de justification (N°ORDRE). */
        get: operations["dossiers_list"]
        put?: never
        /** @description Dossiers de justification (N°ORDRE). */
        post: operations["dossiers_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Dossiers de justification (N°ORDRE). */
        get: operations["dossiers_retrieve"]
        /** @description Dossiers de justification (N°ORDRE). */
        put: operations["dossiers_update"]
        post?: never
        /** @description Dossiers de justification (N°ORDRE). */
        delete: operations["dossiers_destroy"]
        options?: never
        head?: never
        /** @description Dossiers de justification (N°ORDRE). */
        patch: operations["dossiers_partial_update"]
        trace?: never
    }
    "/api/dossiers/{id}/close/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Dossiers de justification (N°ORDRE). */
        post: operations["dossiers_close_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/{id}/justify/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Dossiers de justification (N°ORDRE). */
        post: operations["dossiers_justify_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/{id}/reject/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Dossiers de justification (N°ORDRE). */
        post: operations["dossiers_reject_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/{id}/reopen/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Renvoie un dossier déclaré au brouillon (``transitions.rouvrir``). */
        post: operations["dossiers_reopen_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/{id}/review/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Dossiers de justification (N°ORDRE). */
        post: operations["dossiers_review_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/dossiers/{id}/submit/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Déclare le dossier : ses lignes partent avec lui. */
        post: operations["dossiers_submit_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exchange-rates/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Taux de conversion vers le FCFA, tenus par la direction.
         *
         *     Un taux change la valeur consolidée de toutes les enveloppes : il relève
         *     de ceux qui les attribuent, pas de la RH ni du contrôle.
         */
        get: operations["exchange_rates_list"]
        put?: never
        /**
         * @description Taux de conversion vers le FCFA, tenus par la direction.
         *
         *     Un taux change la valeur consolidée de toutes les enveloppes : il relève
         *     de ceux qui les attribuent, pas de la RH ni du contrôle.
         */
        post: operations["exchange_rates_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exchange-rates/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Taux de conversion vers le FCFA, tenus par la direction.
         *
         *     Un taux change la valeur consolidée de toutes les enveloppes : il relève
         *     de ceux qui les attribuent, pas de la RH ni du contrôle.
         */
        get: operations["exchange_rates_retrieve"]
        /**
         * @description Taux de conversion vers le FCFA, tenus par la direction.
         *
         *     Un taux change la valeur consolidée de toutes les enveloppes : il relève
         *     de ceux qui les attribuent, pas de la RH ni du contrôle.
         */
        put: operations["exchange_rates_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /**
         * @description Taux de conversion vers le FCFA, tenus par la direction.
         *
         *     Un taux change la valeur consolidée de toutes les enveloppes : il relève
         *     de ceux qui les attribuent, pas de la RH ni du contrôle.
         */
        patch: operations["exchange_rates_partial_update"]
        trace?: never
    }
    "/api/expense-titles/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["expense_titles_list"]
        put?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        post: operations["expense_titles_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/expense-titles/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["expense_titles_retrieve"]
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        put: operations["expense_titles_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        patch: operations["expense_titles_partial_update"]
        trace?: never
    }
    "/api/expenses/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        get: operations["expenses_list"]
        put?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        post: operations["expenses_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/expenses/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        get: operations["expenses_retrieve"]
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        put: operations["expenses_update"]
        post?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        delete: operations["expenses_destroy"]
        options?: never
        head?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        patch: operations["expenses_partial_update"]
        trace?: never
    }
    "/api/expenses/{id}/close/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        post: operations["expenses_close_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/expenses/{id}/justify/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        post: operations["expenses_justify_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/expenses/{id}/reject/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        post: operations["expenses_reject_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/expenses/{id}/review/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Lignes de dépenses.
         *
         *     Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
         *     brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
         *     ne se déclare donc jamais seule.
         */
        post: operations["expenses_review_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/expenses/register/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Registre de justification : chaque dépense avec ses preuves.
         *
         *     Le journal d'audit dit qui a fait quoi ; ce registre dit où est passé
         *     l'argent et ce qui l'atteste.
         */
        get: operations["expenses_register_list"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/expenses.csv": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Export des dépenses au format du fichier historique (xlsx, csv, docx). */
        get: operations["exports_expenses.csv_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/expenses.docx": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Export des dépenses au format du fichier historique (xlsx, csv, docx). */
        get: operations["exports_expenses.docx_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/expenses.xlsx": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Export des dépenses au format du fichier historique (xlsx, csv, docx). */
        get: operations["exports_expenses.xlsx_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/reconciliation.csv": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Rapprochement dépenses / montants justifiés (§5.7), xlsx, csv ou docx. */
        get: operations["exports_reconciliation.csv_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/reconciliation.docx": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Rapprochement dépenses / montants justifiés (§5.7), xlsx, csv ou docx. */
        get: operations["exports_reconciliation.docx_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/reconciliation.xlsx": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Rapprochement dépenses / montants justifiés (§5.7), xlsx, csv ou docx. */
        get: operations["exports_reconciliation.xlsx_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/exports/report.pdf": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Rapport PDF par pays et période. */
        get: operations["exports_report.pdf_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/health/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description État de la plateforme, pour Docker et la livraison continue.
         *
         *     Ni compte, ni jeton, ni limitation de débit : le contrôle de santé du
         *     conteneur l'interroge toutes les trente secondes, et un déploiement n'est
         *     déclaré réussi que lorsqu'il répond. Il ne dit que deux choses — le
         *     serveur répond, la base est joignable — et rien sur ce qu'elle contient.
         */
        get: operations["health_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/history/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Historique des changements de rattachement et de configuration. */
        get: operations["history_list"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/history/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Historique des changements de rattachement et de configuration. */
        get: operations["history_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/imports/expenses.xlsx": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Importe l'export des dépenses ou le classeur historique du client.
         *
         *     Réservé aux administrateurs, comme les exports : seuls eux manipulent
         *     des fichiers. Le pays déclare dans l'application, ligne à ligne ; ce qui
         *     entre par un classeur arrive en brouillon et suit ensuite le même
         *     circuit.
         *
         *     Le classeur historique est mono-pays et n'a pas de colonne PAYS : le
         *     pays vient alors du paramètre ``country`` (requête ou formulaire),
         *     vérifié contre le périmètre du demandeur.
         */
        post: operations["imports_expenses.xlsx_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/logout/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Déconnexion : le jeton est supprimé côté serveur.
         *
         *     Oublier le jeton dans le navigateur ne suffit pas : tant qu'il existe en
         *     base, quiconque l'a copié agit au nom du compte.
         */
        post: operations["logout_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/managers/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["managers_list"]
        put?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        post: operations["managers_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/managers/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["managers_retrieve"]
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        put: operations["managers_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        patch: operations["managers_partial_update"]
        trace?: never
    }
    "/api/marketing-categories/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["marketing_categories_list"]
        put?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        post: operations["marketing_categories_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/marketing-categories/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["marketing_categories_retrieve"]
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        put: operations["marketing_categories_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        patch: operations["marketing_categories_partial_update"]
        trace?: never
    }
    "/api/me/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Rôle, périmètre, droits et préférences de l'utilisateur connecté.
         *
         *     ``PATCH`` ne règle que ce qui appartient au titulaire (sa langue) ; le
         *     reste du profil relève du siège, via ``/api/users/``.
         */
        get: operations["me_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        /**
         * @description Rôle, périmètre, droits et préférences de l'utilisateur connecté.
         *
         *     ``PATCH`` ne règle que ce qui appartient au titulaire (sa langue) ; le
         *     reste du profil relève du siège, via ``/api/users/``.
         */
        patch: operations["me_partial_update"]
        trace?: never
    }
    "/api/me/2fa/confirm/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Confirmation de l'enrôlement par un premier code valide.
         *
         *     Tant qu'aucun code n'a été présenté, rien ne prouve que le titulaire a
         *     bien enregistré le secret : confirmer sans code ouvrirait un compte que
         *     son titulaire ne pourrait plus jamais rejoindre.
         */
        post: operations["me_2fa_confirm_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/me/2fa/enrol/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Enrôlement de l'application d'authentification du titulaire.
         *
         *     Le secret n'est engagé qu'à la confirmation : rappeler l'enrôlement en
         *     remplace un secret jamais confirmé, pour qui a fermé la page avant de
         *     scanner le QR. Un compte déjà confirmé ne se réenrôle pas ici — le
         *     secret actif ne doit pas se remplacer sans trace ; c'est le siège qui
         *     réinitialise (``/api/users/{id}/reset-2fa/``), et l'entrée de journal
         *     dit qui l'a fait.
         */
        post: operations["me_2fa_enrol_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/me/password/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Changement de mot de passe par l'utilisateur lui-même.
         *
         *     Le jeton en cours est remplacé : un jeton obtenu avec l'ancien mot de
         *     passe — sur un poste oublié, ou par qui l'a intercepté — ne doit pas
         *     survivre au nouveau. Le client reçoit le jeton de remplacement.
         */
        post: operations["me_password_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/notifications/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Notifications du destinataire courant, et lui seul. */
        get: operations["notifications_list"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/notifications/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Notifications du destinataire courant, et lui seul. */
        get: operations["notifications_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/notifications/{id}/read/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Notifications du destinataire courant, et lui seul. */
        post: operations["notifications_read_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/notifications/read-all/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Notifications du destinataire courant, et lui seul. */
        post: operations["notifications_read_all_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/notifications/unread_count/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Notifications du destinataire courant, et lui seul. */
        get: operations["notifications_unread_count_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/permissions/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Matrice des rôles et de ce qu'ils autorisent (décision 43).
         *
         *     Lue dans la même table que celle appliquée par ``RolePermission``, et
         *     modifiable par les administrateurs, case par case — sauf les verrous :
         *     le super administrateur garde tout, le pays ne reçoit jamais le droit de
         *     contrôler ce qu'il déclare, d'administrer ni d'arbitrer ses enveloppes.
         *     Chaque modification est journalisée avec l'avant et l'après.
         */
        get: operations["permissions_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        /**
         * @description Matrice des rôles et de ce qu'ils autorisent (décision 43).
         *
         *     Lue dans la même table que celle appliquée par ``RolePermission``, et
         *     modifiable par les administrateurs, case par case — sauf les verrous :
         *     le super administrateur garde tout, le pays ne reçoit jamais le droit de
         *     contrôler ce qu'il déclare, d'administrer ni d'arbitrer ses enveloppes.
         *     Chaque modification est journalisée avec l'avant et l'après.
         */
        patch: operations["permissions_partial_update"]
        trace?: never
    }
    "/api/projects/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["projects_list"]
        put?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        post: operations["projects_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/projects/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["projects_retrieve"]
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        put: operations["projects_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        patch: operations["projects_partial_update"]
        trace?: never
    }
    "/api/proofs/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Pièces justificatives, rattachées au dossier. */
        get: operations["proofs_list"]
        put?: never
        /** @description Pièces justificatives, rattachées au dossier. */
        post: operations["proofs_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/proofs/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Pièces justificatives, rattachées au dossier. */
        get: operations["proofs_retrieve"]
        /** @description Pièces justificatives, rattachées au dossier. */
        put: operations["proofs_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Pièces justificatives, rattachées au dossier. */
        patch: operations["proofs_partial_update"]
        trace?: never
    }
    "/api/proofs/{id}/download/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Téléchargement contrôlé (§5.4).
         *
         *     Le fichier transite par cette vue plutôt que par une URL signée : le
         *     périmètre est ainsi vérifié à chaque accès, et chaque téléchargement
         *     laisse une trace d'audit. Il est servi en flux : ``FileResponse``
         *     lit le fichier ouvert par blocs, sans le charger en mémoire — une
         *     pièce de vingt mégaoctets ne doit pas en coûter vingt au serveur.
         */
        get: operations["proofs_download_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/proofs/{id}/review/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Contrôle documentaire (``transitions.controler_piece``). */
        post: operations["proofs_review_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/reallocations/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Transferts entre enveloppes, soumis à approbation.
         *
         *     Une réallocation ne se réécrit pas : elle se demande, puis s'approuve
         *     ou se refuse. Un ``PATCH`` qui changerait le montant ou la cible après
         *     la demande — ou après la décision — ferait mentir le journal et le
         *     mouvement réellement exécuté sur les enveloppes ; ``PUT`` et ``PATCH``
         *     répondent donc 405, comme ``DELETE``.
         */
        get: operations["reallocations_list"]
        put?: never
        /**
         * @description Transferts entre enveloppes, soumis à approbation.
         *
         *     Une réallocation ne se réécrit pas : elle se demande, puis s'approuve
         *     ou se refuse. Un ``PATCH`` qui changerait le montant ou la cible après
         *     la demande — ou après la décision — ferait mentir le journal et le
         *     mouvement réellement exécuté sur les enveloppes ; ``PUT`` et ``PATCH``
         *     répondent donc 405, comme ``DELETE``.
         */
        post: operations["reallocations_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/reallocations/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Transferts entre enveloppes, soumis à approbation.
         *
         *     Une réallocation ne se réécrit pas : elle se demande, puis s'approuve
         *     ou se refuse. Un ``PATCH`` qui changerait le montant ou la cible après
         *     la demande — ou après la décision — ferait mentir le journal et le
         *     mouvement réellement exécuté sur les enveloppes ; ``PUT`` et ``PATCH``
         *     répondent donc 405, comme ``DELETE``.
         */
        get: operations["reallocations_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/reallocations/{id}/approve/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Approuve et exécute le transfert. */
        post: operations["reallocations_approve_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/reallocations/{id}/reject/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /** @description Refuse le transfert. Le motif est obligatoire (§5.5). */
        post: operations["reallocations_reject_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/teams/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["teams_list"]
        put?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        post: operations["teams_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/teams/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        get: operations["teams_retrieve"]
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        put: operations["teams_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Base commune : cloisonnement par pays + droits liés au rôle. */
        patch: operations["teams_partial_update"]
        trace?: never
    }
    "/api/token-auth/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Obtention du jeton, protégée contre le bourrage d'identifiants.
         *
         *     ``ObtainAuthToken`` force ``throttle_classes = ()`` : les limites globales
         *     de ``REST_FRAMEWORK`` ne s'y appliquent pas et il faut donc les réattacher
         *     explicitement. Chaque tentative, réussie ou non, est consignée avec le nom
         *     saisi et l'adresse : c'est la première trace d'une intrusion.
         *
         *     Second facteur : quand la double authentification du compte est
         *     confirmée, la charge utile doit porter ``code``. Le mot de passe est
         *     vérifié d'abord — un code n'est jamais demandé pour un mot de passe faux,
         *     sinon la réponse dirait à l'attaquant qu'il a trouvé le bon. Un compte
         *     pas encore enrôlé se connecte sans code ; si la politique exige la
         *     double authentification (``settings.TOTP_REQUIRED``), c'est le
         *     middleware qui lui ferme tout sauf l'enrôlement. Un compte enrôlé, lui,
         *     fournit son code que la politique l'exige ou non : un second facteur
         *     qu'on a choisi d'activer ne se contourne pas.
         */
        post: operations["token_auth_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/users/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Gestion des comptes. Réservée au siège ; désactivation plutôt que
         *     suppression, pour préserver l'imputabilité des actions passées.
         */
        get: operations["users_list"]
        put?: never
        /**
         * @description Gestion des comptes. Réservée au siège ; désactivation plutôt que
         *     suppression, pour préserver l'imputabilité des actions passées.
         */
        post: operations["users_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/users/{id}/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /**
         * @description Gestion des comptes. Réservée au siège ; désactivation plutôt que
         *     suppression, pour préserver l'imputabilité des actions passées.
         */
        get: operations["users_retrieve"]
        /**
         * @description Gestion des comptes. Réservée au siège ; désactivation plutôt que
         *     suppression, pour préserver l'imputabilité des actions passées.
         */
        put: operations["users_update"]
        post?: never
        delete?: never
        options?: never
        head?: never
        /**
         * @description Gestion des comptes. Réservée au siège ; désactivation plutôt que
         *     suppression, pour préserver l'imputabilité des actions passées.
         */
        patch: operations["users_partial_update"]
        trace?: never
    }
    "/api/users/{id}/reset-2fa/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        get?: never
        put?: never
        /**
         * @description Réinitialise la double authentification d'un compte.
         *
         *     Téléphone perdu, application réinstallée : le titulaire ne peut plus
         *     produire de code, et lui seul pouvait enrôler. Le siège efface le
         *     secret ; le compte redevient « à enrôler », son jeton tombe — qui le
         *     détenait n'est plus forcément le titulaire — et l'opération est
         *     tracée : lever une protection est une action sensible.
         */
        post: operations["users_reset_2fa_create"]
        delete?: never
        options?: never
        head?: never
        patch?: never
        trace?: never
    }
    "/api/workflow-configuration/": {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        /** @description Lecture et modification de la politique du workflow. */
        get: operations["workflow_configuration_retrieve"]
        put?: never
        post?: never
        delete?: never
        options?: never
        head?: never
        /** @description Lecture et modification de la politique du workflow. */
        patch: operations["workflow_configuration_partial_update"]
        trace?: never
    }
}
export type webhooks = Record<string, never>
export interface components {
    schemas: {
        /** @description Alerte calculée à la lecture (``reporting.alerts``). */
        Alert: {
            readonly kind: components["schemas"]["NotificationKindEnum"]
            readonly level: components["schemas"]["NotificationLevelEnum"]
            readonly title: string
            readonly detail: string
            readonly country: number | null
            readonly country_name: string | null
            readonly link: string
            readonly key: string
        }
        /**
         * @description * `created` - Création
         *     * `updated` - Modification
         *     * `submitted` - Soumission
         *     * `reviewed` - Mise en contrôle
         *     * `justified` - Justification
         *     * `unjustified` - Constat de non-justification
         *     * `approved` - Validation d'un justificatif
         *     * `rejected` - Rejet d'un justificatif
         *     * `proof_incomplete` - Justificatif signalé incomplet
         *     * `proof_to_review` - Justificatif remis à contrôler
         *     * `deleted` - Suppression d'un brouillon
         *     * `closed` - Clôture
         *     * `reopened` - Réouverture
         *     * `proof_uploaded` - Dépôt de justificatif
         *     * `proof_replaced` - Remplacement de justificatif
         *     * `downloaded` - Téléchargement
         *     * `imported` - Import Excel
         * @enum {string}
         */
        AuditActionEnum: "created" | "updated" | "submitted" | "reviewed" | "justified" | "unjustified" | "approved" | "rejected" | "proof_incomplete" | "proof_to_review" | "deleted" | "closed" | "reopened" | "proof_uploaded" | "proof_replaced" | "downloaded" | "imported"
        AuditLog: {
            readonly id: number
            /** Utilisateur */
            user: string
            action: components["schemas"]["AuditActionEnum"]
            readonly action_display: string
            /** Type d'objet */
            object_type: string
            /**
             * Identifiant
             * Format: int64
             */
            object_id: number | null
            /** Libellé */
            label: string
            /** Pays */
            country: number | null
            readonly country_name: string | null
            readonly detail: {
                [key: string]: unknown
            }
            /** Adresse IP */
            ip_address: string | null
            /** Appareil / session */
            user_agent: string
            /**
             * Le
             * Format: date-time
             */
            readonly created_at: string
        }
        /** @description Pays africain proposé à la création, non encore suivi. */
        AvailableCountry: {
            readonly code: string
            readonly name: string
        }
        Beneficiary: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string | null
            /** Nom */
            name: string
            /** Type */
            kind: components["schemas"]["BeneficiaryKindEnum"]
            readonly kind_display: string
            contact: string
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        /**
         * @description * `prospect` - Prospect
         *     * `client` - Client
         *     * `supplier` - Fournisseur
         *     * `beneficiary` - Bénéficiaire
         *     * `other` - Autre
         * @enum {string}
         */
        BeneficiaryKindEnum: "prospect" | "client" | "supplier" | "beneficiary" | "other"
        BeneficiaryRequest: {
            /** Pays */
            country: number
            /** Nom */
            name: string
            /** Type */
            kind?: components["schemas"]["BeneficiaryKindEnum"]
            contact?: string
            /** Actif */
            is_active?: boolean
        }
        Breakdown: {
            readonly year: number
            readonly by_team: components["schemas"]["BreakdownRow"][]
            readonly by_owner: components["schemas"]["BreakdownRow"][]
            readonly by_project: components["schemas"]["BreakdownRow"][]
            readonly by_category: components["schemas"]["BreakdownRow"][]
            readonly by_expense_title: components["schemas"]["BreakdownRow"][]
            readonly by_month: components["schemas"]["BreakdownRow"][]
        }
        BreakdownRow: {
            readonly label: string
            /** Format: decimal */
            readonly amount: string
            /** Format: decimal */
            readonly justified: string
            /** Format: decimal */
            readonly gap: string
            readonly lines: number
        }
        Budget: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string
            readonly country_ref: string
            readonly currency: string
            /** Année */
            year: number
            /** Projet */
            project: number | null
            readonly project_name: string | null
            /** Équipe */
            team: number | null
            readonly team_name: string | null
            manager: number | null
            readonly manager_name: string | null
            readonly scope_kind: components["schemas"]["BudgetScopeEnum"]
            readonly scope_label: string | null
            /**
             * Montant
             * Format: decimal
             */
            amount: string
            /** Politique de dépassement */
            overrun_policy: components["schemas"]["OverrunPolicyEnum"]
            readonly overrun_policy_display: string
            /** Actif */
            is_active: boolean
            readonly figures: components["schemas"]["BudgetFigures"]
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        /**
         * @description Indicateurs d'une enveloppe, calculés par ``aggregates.budget_figures``.
         *
         *     Forme documentaire : la vue rend le dictionnaire tel quel, ce sérialiseur
         *     ne sert qu'au schéma.
         */
        BudgetFigures: {
            /**
             * Format: decimal
             * @description Soumis ou en contrôle : sorti de l'enveloppe, pas encore constaté.
             */
            readonly engaged: string
            /** Format: decimal */
            readonly consumed: string
            /** Format: decimal */
            readonly justified: string
            /**
             * Format: decimal
             * @description Consommé sans preuve à l'appui.
             */
            readonly gap: string
            /** Format: decimal */
            readonly remaining: string
            /** Format: decimal */
            readonly execution_rate: string | null
            /** Format: decimal */
            readonly justification_rate: string | null
            /** Format: decimal */
            readonly amount_xof: string | null
            /** Format: decimal */
            readonly remaining_xof: string | null
        }
        BudgetReallocation: {
            readonly id: number
            /** Enveloppe source */
            source: number
            readonly source_label: string
            /** Enveloppe destinataire */
            target: number
            readonly target_label: string
            /**
             * Montant
             * Format: decimal
             */
            amount: string
            /** Justification */
            reason: string
            /** Statut */
            readonly status: components["schemas"]["ReallocationStatusEnum"]
            readonly status_display: string
            /** Demandée par */
            readonly requested_by: string
            /** Décidée par */
            readonly decided_by: string
            /**
             * Décidée le
             * Format: date-time
             */
            readonly decided_at: string | null
            /** Motif de la décision */
            readonly decision_note: string
            readonly can_decide: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        BudgetReallocationRequest: {
            /** Enveloppe source */
            source: number
            /** Enveloppe destinataire */
            target: number
            /**
             * Montant
             * Format: decimal
             */
            amount: string
            /** Justification */
            reason: string
        }
        BudgetRequest: {
            /** Pays */
            country: number
            /** Année */
            year: number
            /** Projet */
            project?: number | null
            /** Équipe */
            team?: number | null
            manager?: number | null
            /**
             * Montant
             * Format: decimal
             */
            amount: string
            /** Politique de dépassement */
            overrun_policy?: components["schemas"]["OverrunPolicyEnum"]
            /** Actif */
            is_active?: boolean
        }
        /**
         * @description * `country` - country
         *     * `project` - project
         *     * `team` - team
         *     * `manager` - manager
         * @enum {string}
         */
        BudgetScopeEnum: "country" | "project" | "team" | "manager"
        BudgetSummary: {
            readonly countries: components["schemas"]["CountryBudgetRow"][]
            /** Format: decimal */
            readonly total_remaining_xof: string
            /** @description Devises sans taux connu, laissées hors du total. */
            readonly unconverted_currencies: string[]
        }
        ChangeLog: {
            readonly id: number
            /** Entité */
            model_name: components["schemas"]["ChangeLogModelEnum"]
            readonly model_name_display: string
            /**
             * Identifiant d'entité
             * Format: int64
             */
            object_id: number | null
            /** Libellé */
            label: string
            action: components["schemas"]["ChangeLogActionEnum"]
            readonly action_display: string
            /** Pays */
            country: number | null
            readonly country_name: string | null
            /** Valeur précédente */
            from_value: string
            /** Nouvelle valeur */
            to_value: string
            readonly changed_fields: string[]
            readonly diff: {
                [key: string]: [
                    unknown,
                    unknown
                ]
            }
            /** Par */
            performed_by: string
            /** Adresse IP */
            ip_address: string | null
            /**
             * Le
             * Format: date-time
             */
            readonly created_at: string
        }
        /**
         * @description * `created` - Création
         *     * `updated` - Mise à jour
         *     * `reassigned` - Changement de rattachement
         *     * `deactivated` - Désactivation
         *     * `reactivated` - Réactivation
         *     * `deleted` - Suppression
         *     * `password_reset` - Réinitialisation du mot de passe
         *     * `password_changed` - Changement de mot de passe
         *     * `login` - Connexion
         *     * `login_failed` - Échec de connexion
         *     * `logout` - Déconnexion
         *     * `totp_confirmed` - Double authentification activée
         *     * `totp_reset` - Double authentification réinitialisée
         * @enum {string}
         */
        ChangeLogActionEnum: "created" | "updated" | "reassigned" | "deactivated" | "reactivated" | "deleted" | "password_reset" | "password_changed" | "login" | "login_failed" | "logout" | "totp_confirmed" | "totp_reset"
        /**
         * @description * `country` - Pays
         *     * `manager` - Manager
         *     * `team` - Équipe
         *     * `cost_center` - Centre de coûts
         *     * `project` - Projet
         *     * `expense_title` - Intitulé de dépenses
         *     * `marketing_category` - Catégorie marketing
         *     * `budget` - Enveloppe budgétaire
         *     * `reallocation` - Réallocation budgétaire
         *     * `exchange_rate` - Taux de change
         *     * `workflow_configuration` - Configuration du workflow
         *     * `user` - Compte utilisateur
         * @enum {string}
         */
        ChangeLogModelEnum: "country" | "manager" | "team" | "cost_center" | "project" | "expense_title" | "marketing_category" | "budget" | "reallocation" | "exchange_rate" | "workflow_configuration" | "user"
        ChangePasswordRequest: {
            current_password: string
            new_password: string
        }
        /** @description Réglages effectifs de la plateforme (``/api/configuration/``). */
        Configuration: {
            readonly alertes: components["schemas"]["ConfigurationAlertes"]
            readonly justificatifs: components["schemas"]["ConfigurationJustificatifs"]
            readonly budget: components["schemas"]["ConfigurationBudget"]
            readonly notifications: components["schemas"]["ConfigurationNotifications"]
            readonly systeme: components["schemas"]["ConfigurationSysteme"]
            readonly workflow: components["schemas"]["WorkflowConfiguration"]
            /** @description Un tableau de bord de supervision (Grafana) est déployé avec cette pile. */
            readonly supervision: boolean
        }
        ConfigurationAlertes: {
            readonly seuils: number[]
            /** Format: double */
            readonly facteur_depense_inhabituelle: number
        }
        ConfigurationBudget: {
            readonly devise_de_consolidation: string
        }
        ConfigurationJustificatifs: {
            readonly taille_max_mo: number
            readonly formats_acceptes: string[]
            readonly stockage: string
        }
        ConfigurationNotifications: {
            readonly email_configure: boolean
            readonly expediteur: string
        }
        ConfigurationSysteme: {
            readonly fuseau: string
            readonly mode_debug: boolean
        }
        ConsolidatedXof: {
            /** Format: decimal */
            readonly allocated: string
            /** Format: decimal */
            readonly remaining: string
            readonly unconverted_currencies: string[]
        }
        CostCenter: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string
            code: string
            /** Libellé */
            name: string
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        CostCenterRequest: {
            /** Pays */
            country: number
            code: string
            /** Libellé */
            name: string
            /** Actif */
            is_active?: boolean
        }
        /** @description Ligne de la consolidation par pays (``/api/budgets/summary/``). */
        CountryBudgetRow: {
            readonly country: number
            readonly country_name: string
            readonly country_ref: string | null
            readonly currency: string
            /** Format: decimal */
            readonly allocated: string
            /** Format: decimal */
            readonly sub_allocated: string
            /** Format: decimal */
            readonly engaged: string
            /** Format: decimal */
            readonly consumed: string
            /** Format: decimal */
            readonly justified: string
            /** Format: decimal */
            readonly remaining: string
            /** Format: decimal */
            readonly remaining_xof: string | null
        }
        /** @description Représentation compacte pour la liste des pays. */
        CountryDetail: {
            readonly id: number
            /** Nom */
            name: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref: string | null
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
            /** Symbole devise */
            currency_symbol: string
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone: string
            /** Actif */
            is_active: boolean
            readonly managers: components["schemas"]["Manager"][]
            readonly team_count: number
            readonly cost_center_count: number
            readonly project_count: number
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
            readonly teams: components["schemas"]["Team"][]
            readonly cost_centers: components["schemas"]["CostCenter"][]
            readonly projects: components["schemas"]["Project"][]
            readonly expense_titles: components["schemas"]["ExpenseTitle"][]
            readonly marketing_categories: components["schemas"]["MarketingCategory"][]
            readonly expense_title_count: number
            readonly marketing_category_count: number
        }
        /** @description Représentation compacte pour la liste des pays. */
        CountryList: {
            readonly id: number
            /** Nom */
            name: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref: string | null
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
            /** Symbole devise */
            currency_symbol: string
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone: string
            /** Actif */
            is_active: boolean
            readonly managers: components["schemas"]["Manager"][]
            readonly team_count: number
            readonly cost_center_count: number
            readonly project_count: number
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        CountryWrite: {
            readonly id: number
            /** Nom */
            name: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref: string | null
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
            /** Symbole devise */
            currency_symbol: string
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone: string
            /** Actif */
            is_active: boolean
            managers: number[]
        }
        CountryWriteRequest: {
            /** Nom */
            name: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref?: string | null
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
            /** Symbole devise */
            currency_symbol?: string
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone?: string
            /** Actif */
            is_active?: boolean
            managers?: number[]
        }
        Dashboard: {
            readonly year: number
            readonly totals: components["schemas"]["DashboardTotals"]
            readonly consolidated_xof: components["schemas"]["ConsolidatedXof"]
            readonly countries: components["schemas"]["DashboardCountryRow"][]
            readonly workload: components["schemas"]["Workload"]
            /** @description Les plus graves seulement ; ``alerts_total`` donne le compte réel. */
            readonly alerts: components["schemas"]["Alert"][]
            readonly alerts_total: number
        }
        DashboardCountryRow: {
            readonly country: number
            readonly country_name: string
            readonly country_ref: string | null
            readonly currency: string
            /** Format: decimal */
            readonly allocated: string
            /** Format: decimal */
            readonly sub_allocated: string
            /** Format: decimal */
            readonly engaged: string
            /** Format: decimal */
            readonly consumed: string
            /** Format: decimal */
            readonly justified: string
            /** Format: decimal */
            readonly gap: string
            /** Format: decimal */
            readonly remaining: string
            /** Format: decimal */
            readonly execution_rate: string | null
            /** Format: decimal */
            readonly justification_rate: string | null
            /** Format: decimal */
            readonly remaining_xof: string | null
        }
        /** @description Totaux consolidés en FCFA (``totals``). */
        DashboardTotals: {
            readonly currency: string
            /** Format: decimal */
            readonly allocated: string
            /** Format: decimal */
            readonly engaged: string
            /** Format: decimal */
            readonly consumed: string
            /** Format: decimal */
            readonly justified: string
            /**
             * Format: decimal
             * @description Dépensé sans preuve à l'appui.
             */
            readonly gap: string
            /** Format: decimal */
            readonly remaining: string
            /** Format: decimal */
            readonly execution_rate: string | null
            /** Format: decimal */
            readonly justification_rate: string | null
            /** @description Devises sans taux connu, laissées hors des totaux. */
            readonly unconverted_currencies: string[]
        }
        /**
         * @description * `ok` - ok
         *     * `ko` - ko
         * @enum {string}
         */
        DatabaseEnum: "ok" | "ko"
        Dossier: {
            readonly id: number
            /** N° d'ordre */
            number: string
            /** Libellé */
            label: string
            country: number
            readonly country_name: string
            readonly country_ref: string | null
            readonly currency: string
            readonly country_timezone: string
            team: number | null
            readonly team_name: string | null
            owner: number | null
            readonly owner_name: string | null
            /** Format: date */
            date: string
            /** Statut */
            readonly status: components["schemas"]["WorkflowStatusEnum"]
            readonly status_display: string
            /** Remarque de contrôle */
            note: string
            /** Motif de la réouverture */
            readonly reopen_note: string
            readonly totals: components["schemas"]["DossierTotals"]
            readonly expense_count: number
            readonly proof_count: number
            readonly allowed_actions: components["schemas"]["TransitionEnum"][]
            /** Ouvert par */
            readonly created_by: string
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        DossierDetail: {
            readonly id: number
            /** N° d'ordre */
            number: string
            /** Libellé */
            label: string
            country: number
            readonly country_name: string
            readonly country_ref: string | null
            readonly currency: string
            readonly country_timezone: string
            team: number | null
            readonly team_name: string | null
            owner: number | null
            readonly owner_name: string | null
            /** Format: date */
            date: string
            /** Statut */
            readonly status: components["schemas"]["WorkflowStatusEnum"]
            readonly status_display: string
            /** Remarque de contrôle */
            note: string
            /** Motif de la réouverture */
            readonly reopen_note: string
            readonly totals: components["schemas"]["DossierTotals"]
            readonly expense_count: number
            readonly proof_count: number
            readonly allowed_actions: components["schemas"]["TransitionEnum"][]
            /** Ouvert par */
            readonly created_by: string
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
            readonly expenses: components["schemas"]["Expense"][]
            readonly proofs: components["schemas"]["Proof"][]
        }
        DossierRequest: {
            /** N° d'ordre */
            number: string
            /** Libellé */
            label: string
            country: number
            team?: number | null
            owner?: number | null
            /** Format: date */
            date: string
            /** Remarque de contrôle */
            note?: string
        }
        /** @description Totaux d'un dossier, calculés en base (``Dossier.totals``). */
        DossierTotals: {
            /** Format: decimal */
            readonly amount: string
            /** Format: decimal */
            readonly justified: string
            /** Format: decimal */
            readonly gap: string
        }
        /**
         * @description Le dossier après une transition, avec son avertissement éventuel.
         *
         *     Forme documentaire (schéma) : la vue rend ``presenter()`` et y joint
         *     ``warning`` ; ce sérialiseur n'est jamais instancié.
         */
        DossierTransitionResponse: {
            readonly id: number
            /** N° d'ordre */
            number: string
            /** Libellé */
            label: string
            country: number
            readonly country_name: string
            readonly country_ref: string | null
            readonly currency: string
            readonly country_timezone: string
            team: number | null
            readonly team_name: string | null
            owner: number | null
            readonly owner_name: string | null
            /** Format: date */
            date: string
            /** Statut */
            readonly status: components["schemas"]["WorkflowStatusEnum"]
            readonly status_display: string
            /** Remarque de contrôle */
            note: string
            /** Motif de la réouverture */
            readonly reopen_note: string
            readonly totals: components["schemas"]["DossierTotals"]
            readonly expense_count: number
            readonly proof_count: number
            readonly allowed_actions: components["schemas"]["TransitionEnum"][]
            /** Ouvert par */
            readonly created_by: string
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
            readonly expenses: components["schemas"]["Expense"][]
            readonly proofs: components["schemas"]["Proof"][]
            readonly warning?: string
        }
        ExchangeRate: {
            readonly id: number
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
            /**
             * Taux vers le FCFA
             * Format: decimal
             * @description Nombre de FCFA pour une unité de la devise.
             */
            rate_to_xof: string
            /**
             * En vigueur depuis
             * Format: date
             */
            valid_from: string
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
        }
        ExchangeRateRequest: {
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
            /**
             * Taux vers le FCFA
             * Format: decimal
             * @description Nombre de FCFA pour une unité de la devise.
             */
            rate_to_xof: string
            /**
             * En vigueur depuis
             * Format: date
             */
            valid_from: string
        }
        Expense: {
            readonly id: number
            dossier: number
            readonly dossier_number: string
            country: number
            readonly country_name: string
            readonly currency: string
            readonly country_timezone: string
            team: number | null
            readonly team_name: string | null
            owner: number | null
            readonly owner_name: string | null
            /**
             * Date et heure
             * Format: date-time
             */
            date: string
            /** Lieu */
            place: string
            /** Libellé de la transaction */
            title: string
            description: string
            project: number | null
            readonly project_name: string | null
            expense_title: number | null
            marketing_category: number | null
            beneficiary: number | null
            readonly beneficiary_name: string | null
            /**
             * Enveloppe imputée
             * @description Résolue automatiquement ; obligatoire avant validation.
             */
            readonly budget: number | null
            readonly budget_label: string | null
            /**
             * Dépense
             * Format: decimal
             * @description Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe.
             */
            amount: string
            /**
             * Montant justifié
             * Format: decimal
             */
            readonly justified_amount: string
            /**
             * Format: decimal
             * @description Toujours calculé : dépense − montant justifié.
             */
            readonly gap: string
            /**
             * Devise du décaissement
             * @description Vide si la dépense a été faite dans la devise du pays.
             */
            original_currency: string
            /**
             * Montant décaissé
             * Format: decimal
             * @description Tel qu'il figure sur la pièce, dans sa devise d'origine.
             */
            original_amount: string | null
            /**
             * Taux appliqué
             * Format: decimal
             * @description Figé à la saisie. Le conserver permet de refaire le calcul plus tard, même si la table des taux a depuis été corrigée.
             */
            readonly original_rate: string | null
            /** Mode de paiement */
            payment_method: components["schemas"]["PaymentMethodEnum"]
            readonly payment_method_display: string
            /** Statut */
            readonly status: components["schemas"]["WorkflowStatusEnum"]
            readonly status_display: string
            /** Remarque */
            note: string
            /** Motif du contrôle */
            readonly control_note: string
            /** Saisie par */
            readonly created_by: string
            readonly allowed_actions: components["schemas"]["TransitionEnum"][]
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        /** @description Pièce vue depuis une dépense : de quoi juger sans ouvrir le dossier. */
        ExpenseProof: {
            readonly id: number
            /** Nom d'origine */
            original_name: string
            /** Type */
            kind: components["schemas"]["ProofKindEnum"]
            readonly kind_display: string
            /** Statut */
            status: components["schemas"]["ProofStatusEnum"]
            readonly status_display: string
            /**
             * Justificatif complet
             * @description Reprend la nuance « reçu (justif incomplet) » du fichier source.
             */
            is_complete: boolean
            /**
             * Empreinte SHA-256
             * @description Détecte toute modification ultérieure et les doublons.
             */
            sha256: string
            version: number
        }
        /**
         * @description Registre de justification : la dépense et ses preuves d'un seul tenant.
         *
         *     Répond à la question que l'application existe pour trancher — on vous a
         *     confié un budget, qu'avez-vous dépensé, et qu'est-ce qui l'atteste ? Aucun
         *     détail de la dépense n'est écarté.
         */
        ExpenseRegister: {
            readonly id: number
            dossier: number
            readonly dossier_number: string
            country: number
            readonly country_name: string
            readonly currency: string
            readonly country_timezone: string
            team: number | null
            readonly team_name: string | null
            owner: number | null
            readonly owner_name: string | null
            /**
             * Date et heure
             * Format: date-time
             */
            date: string
            /** Lieu */
            place: string
            /** Libellé de la transaction */
            title: string
            description: string
            project: number | null
            readonly project_name: string | null
            expense_title: number | null
            marketing_category: number | null
            beneficiary: number | null
            readonly beneficiary_name: string | null
            /**
             * Enveloppe imputée
             * @description Résolue automatiquement ; obligatoire avant validation.
             */
            readonly budget: number | null
            readonly budget_label: string | null
            /**
             * Dépense
             * Format: decimal
             * @description Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe.
             */
            amount: string
            /**
             * Montant justifié
             * Format: decimal
             */
            readonly justified_amount: string
            /**
             * Format: decimal
             * @description Toujours calculé : dépense − montant justifié.
             */
            readonly gap: string
            /**
             * Devise du décaissement
             * @description Vide si la dépense a été faite dans la devise du pays.
             */
            original_currency: string
            /**
             * Montant décaissé
             * Format: decimal
             * @description Tel qu'il figure sur la pièce, dans sa devise d'origine.
             */
            original_amount: string | null
            /**
             * Taux appliqué
             * Format: decimal
             * @description Figé à la saisie. Le conserver permet de refaire le calcul plus tard, même si la table des taux a depuis été corrigée.
             */
            readonly original_rate: string | null
            /** Mode de paiement */
            payment_method: components["schemas"]["PaymentMethodEnum"]
            readonly payment_method_display: string
            /** Statut */
            readonly status: components["schemas"]["WorkflowStatusEnum"]
            readonly status_display: string
            /** Remarque */
            note: string
            /** Motif du contrôle */
            readonly control_note: string
            /** Saisie par */
            readonly created_by: string
            readonly allowed_actions: components["schemas"]["TransitionEnum"][]
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
            readonly dossier_label: string
            readonly expense_title_label: string | null
            readonly marketing_category_name: string | null
            readonly proofs: components["schemas"]["ExpenseProof"][]
            readonly has_proof: boolean
        }
        ExpenseRequest: {
            dossier: number
            country: number
            team?: number | null
            owner?: number | null
            /**
             * Date et heure
             * Format: date-time
             */
            date: string
            /** Lieu */
            place?: string
            /** Libellé de la transaction */
            title: string
            description?: string
            project?: number | null
            expense_title?: number | null
            marketing_category?: number | null
            beneficiary?: number | null
            /**
             * Dépense
             * Format: decimal
             * @description Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe.
             */
            amount?: string
            /**
             * Devise du décaissement
             * @description Vide si la dépense a été faite dans la devise du pays.
             */
            original_currency?: string
            /**
             * Montant décaissé
             * Format: decimal
             * @description Tel qu'il figure sur la pièce, dans sa devise d'origine.
             */
            original_amount?: string | null
            /** Mode de paiement */
            payment_method?: components["schemas"]["PaymentMethodEnum"]
            /** Remarque */
            note?: string
        }
        ExpenseTitle: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string
            /** Intitulé */
            label: string
            description: string
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        ExpenseTitleRequest: {
            /** Pays */
            country: number
            /** Intitulé */
            label: string
            description?: string
            /** Actif */
            is_active?: boolean
        }
        /**
         * @description Transition d'une ligne : le siège (DF) peut fixer ce qui est prouvé.
         *
         *     Par défaut, justifier couvre toute la dépense ; une pièce partielle
         *     permet d'en constater une partie seulement. La borne haute (le montant
         *     de la dépense) se vérifie dans la vue, qui connaît la ligne.
         */
        ExpenseTransitionRequest: {
            note?: string
            /** Format: decimal */
            justified_amount?: string
        }
        /** @description La ligne après une transition, avec son avertissement éventuel. */
        ExpenseTransitionResponse: {
            readonly id: number
            dossier: number
            readonly dossier_number: string
            country: number
            readonly country_name: string
            readonly currency: string
            readonly country_timezone: string
            team: number | null
            readonly team_name: string | null
            owner: number | null
            readonly owner_name: string | null
            /**
             * Date et heure
             * Format: date-time
             */
            date: string
            /** Lieu */
            place: string
            /** Libellé de la transaction */
            title: string
            description: string
            project: number | null
            readonly project_name: string | null
            expense_title: number | null
            marketing_category: number | null
            beneficiary: number | null
            readonly beneficiary_name: string | null
            /**
             * Enveloppe imputée
             * @description Résolue automatiquement ; obligatoire avant validation.
             */
            readonly budget: number | null
            readonly budget_label: string | null
            /**
             * Dépense
             * Format: decimal
             * @description Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe.
             */
            amount: string
            /**
             * Montant justifié
             * Format: decimal
             */
            readonly justified_amount: string
            /**
             * Format: decimal
             * @description Toujours calculé : dépense − montant justifié.
             */
            readonly gap: string
            /**
             * Devise du décaissement
             * @description Vide si la dépense a été faite dans la devise du pays.
             */
            original_currency: string
            /**
             * Montant décaissé
             * Format: decimal
             * @description Tel qu'il figure sur la pièce, dans sa devise d'origine.
             */
            original_amount: string | null
            /**
             * Taux appliqué
             * Format: decimal
             * @description Figé à la saisie. Le conserver permet de refaire le calcul plus tard, même si la table des taux a depuis été corrigée.
             */
            readonly original_rate: string | null
            /** Mode de paiement */
            payment_method: components["schemas"]["PaymentMethodEnum"]
            readonly payment_method_display: string
            /** Statut */
            readonly status: components["schemas"]["WorkflowStatusEnum"]
            readonly status_display: string
            /** Remarque */
            note: string
            /** Motif du contrôle */
            readonly control_note: string
            /** Saisie par */
            readonly created_by: string
            readonly allowed_actions: components["schemas"]["TransitionEnum"][]
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
            readonly warning?: string
        }
        Health: {
            readonly status: components["schemas"]["HealthStatusEnum"]
            readonly database: components["schemas"]["DatabaseEnum"]
        }
        /**
         * @description * `ok` - ok
         *     * `indisponible` - indisponible
         * @enum {string}
         */
        HealthStatusEnum: "ok" | "indisponible"
        ImportError: {
            readonly ligne: number
            readonly motif: string
        }
        /** @description Classeur à importer, et le pays d'un classeur sans colonne PAYS. */
        ImportRequest: {
            /** Format: binary */
            file: string
            country?: number
        }
        ImportResult: {
            readonly dossiers_crees: number
            readonly lignes_creees: number
            readonly equipes_creees: number
            readonly managers_crees: number
            readonly erreurs: components["schemas"]["ImportError"][]
            readonly dry_run: boolean
        }
        /**
         * @description * `fr` - Français
         *     * `en` - English
         * @enum {string}
         */
        LanguageEnum: "fr" | "en"
        Manager: {
            readonly id: number
            /** Nom */
            name: string
            /** Courriel */
            email: string
            /** Fonction */
            title: string
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        ManagerRequest: {
            /** Nom */
            name: string
            /** Courriel */
            email?: string
            /** Fonction */
            title?: string
            /** Actif */
            is_active?: boolean
        }
        /** @description Forme documentaire de ``/api/notifications/read-all/``. */
        MarkedRead: {
            readonly marked: number
        }
        MarketingCategory: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string
            /** Nom */
            name: string
            description: string
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        MarketingCategoryRequest: {
            /** Pays */
            country: number
            /** Nom */
            name: string
            description?: string
            /** Actif */
            is_active?: boolean
        }
        /**
         * @description Profil de l'utilisateur connecté, consommé par le frontend.
         *
         *     Un compte technique d'amorçage peut ne pas avoir de profil : les champs
         *     sont donc calculés, pour que la réponse garde toujours la même forme.
         */
        Me: {
            readonly id: number
            /**
             * Nom d’utilisateur
             * @description Requis. 150 caractères maximum. Uniquement des lettres, nombres et les caractères « @ », « . », « + », « - » et « _ ».
             */
            username: string
            /** Prénom */
            first_name: string
            /** Nom */
            last_name: string
            /** Adresse électronique */
            email: string
            readonly role: (components["schemas"]["RoleEnum"] | components["schemas"]["NullEnum"]) | null
            readonly role_display: string | null
            readonly countries: components["schemas"]["ScopeCountry"][]
            readonly teams: components["schemas"]["ScopeTeam"][]
            readonly has_global_scope: boolean
            readonly must_change_password: boolean
            readonly totp_required: boolean
            readonly totp_confirmed: boolean
            readonly language: components["schemas"]["LanguageEnum"]
            readonly permissions: components["schemas"]["Permissions"]
            readonly workflow: components["schemas"]["MeWorkflow"]
            readonly supervision: boolean
        }
        /** @description Politique du circuit que l'interface doit connaître. */
        MeWorkflow: {
            readonly require_review_step: boolean
        }
        Notification: {
            readonly id: number
            /** Type */
            readonly kind: components["schemas"]["NotificationKindEnum"]
            readonly kind_display: string
            /** Niveau */
            readonly level: components["schemas"]["NotificationLevelEnum"]
            readonly level_display: string
            /** Titre */
            readonly title: string
            /** Message */
            readonly body: string
            /**
             * Lien
             * @description Chemin relatif dans l'application, ex. /dossiers/12.
             */
            readonly link: string
            /** Pays */
            readonly country: number | null
            readonly country_name: string | null
            /**
             * Lu le
             * Format: date-time
             */
            readonly read_at: string | null
            /**
             * Le
             * Format: date-time
             */
            readonly created_at: string
        }
        /**
         * @description * `budget_threshold` - Seuil budgétaire atteint
         *     * `budget_overrun` - Dépassement budgétaire
         *     * `expense_submitted` - Dépense à contrôler
         *     * `expense_rejected` - Dépense rejetée
         *     * `proof_missing` - Justificatif manquant
         *     * `proof_incomplete` - Justificatif incomplet
         *     * `reallocation_requested` - Demande de réallocation
         *     * `storage_error` - Anomalie de stockage
         *     * `dossier_reopened` - Dossier rouvert
         * @enum {string}
         */
        NotificationKindEnum: "budget_threshold" | "budget_overrun" | "expense_submitted" | "expense_rejected" | "proof_missing" | "proof_incomplete" | "reallocation_requested" | "storage_error" | "dossier_reopened"
        /**
         * @description * `info` - Information
         *     * `warning` - Avertissement
         *     * `critical` - Critique
         * @enum {string}
         */
        NotificationLevelEnum: "info" | "warning" | "critical"
        /** @enum {unknown} */
        NullEnum: null
        /**
         * @description * `block` - Bloquer
         *     * `warn` - Alerter
         *     * `approval` - Soumettre à approbation
         * @enum {string}
         */
        OverrunPolicyEnum: "block" | "warn" | "approval"
        PaginatedAuditLogList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["AuditLog"][]
        }
        PaginatedBeneficiaryList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Beneficiary"][]
        }
        PaginatedBudgetList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Budget"][]
        }
        PaginatedBudgetReallocationList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["BudgetReallocation"][]
        }
        PaginatedChangeLogList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["ChangeLog"][]
        }
        PaginatedCostCenterList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["CostCenter"][]
        }
        PaginatedCountryListList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["CountryList"][]
        }
        PaginatedDossierList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Dossier"][]
        }
        PaginatedExchangeRateList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["ExchangeRate"][]
        }
        PaginatedExpenseList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Expense"][]
        }
        PaginatedExpenseRegisterList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["ExpenseRegister"][]
        }
        PaginatedExpenseTitleList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["ExpenseTitle"][]
        }
        PaginatedManagerList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Manager"][]
        }
        PaginatedMarketingCategoryList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["MarketingCategory"][]
        }
        PaginatedNotificationList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Notification"][]
        }
        PaginatedProjectList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Project"][]
        }
        PaginatedProofList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Proof"][]
        }
        PaginatedTeamList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["Team"][]
        }
        PaginatedUserList: {
            /** @example 123 */
            count: number
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next: string | null
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous: string | null
            results: components["schemas"]["User"][]
        }
        PatchedBeneficiaryRequest: {
            /** Pays */
            country?: number
            /** Nom */
            name?: string
            /** Type */
            kind?: components["schemas"]["BeneficiaryKindEnum"]
            contact?: string
            /** Actif */
            is_active?: boolean
        }
        PatchedBudgetRequest: {
            /** Pays */
            country?: number
            /** Année */
            year?: number
            /** Projet */
            project?: number | null
            /** Équipe */
            team?: number | null
            manager?: number | null
            /**
             * Montant
             * Format: decimal
             */
            amount?: string
            /** Politique de dépassement */
            overrun_policy?: components["schemas"]["OverrunPolicyEnum"]
            /** Actif */
            is_active?: boolean
        }
        PatchedCostCenterRequest: {
            /** Pays */
            country?: number
            code?: string
            /** Libellé */
            name?: string
            /** Actif */
            is_active?: boolean
        }
        PatchedCountryWriteRequest: {
            /** Nom */
            name?: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code?: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref?: string | null
            /**
             * Devise
             * @description ISO 4217
             */
            currency?: string
            /** Symbole devise */
            currency_symbol?: string
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone?: string
            /** Actif */
            is_active?: boolean
            managers?: number[]
        }
        PatchedDossierRequest: {
            /** N° d'ordre */
            number?: string
            /** Libellé */
            label?: string
            country?: number
            team?: number | null
            owner?: number | null
            /** Format: date */
            date?: string
            /** Remarque de contrôle */
            note?: string
        }
        PatchedExchangeRateRequest: {
            /**
             * Devise
             * @description ISO 4217
             */
            currency?: string
            /**
             * Taux vers le FCFA
             * Format: decimal
             * @description Nombre de FCFA pour une unité de la devise.
             */
            rate_to_xof?: string
            /**
             * En vigueur depuis
             * Format: date
             */
            valid_from?: string
        }
        PatchedExpenseRequest: {
            dossier?: number
            country?: number
            team?: number | null
            owner?: number | null
            /**
             * Date et heure
             * Format: date-time
             */
            date?: string
            /** Lieu */
            place?: string
            /** Libellé de la transaction */
            title?: string
            description?: string
            project?: number | null
            expense_title?: number | null
            marketing_category?: number | null
            beneficiary?: number | null
            /**
             * Dépense
             * Format: decimal
             * @description Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe.
             */
            amount?: string
            /**
             * Devise du décaissement
             * @description Vide si la dépense a été faite dans la devise du pays.
             */
            original_currency?: string
            /**
             * Montant décaissé
             * Format: decimal
             * @description Tel qu'il figure sur la pièce, dans sa devise d'origine.
             */
            original_amount?: string | null
            /** Mode de paiement */
            payment_method?: components["schemas"]["PaymentMethodEnum"]
            /** Remarque */
            note?: string
        }
        PatchedExpenseTitleRequest: {
            /** Pays */
            country?: number
            /** Intitulé */
            label?: string
            description?: string
            /** Actif */
            is_active?: boolean
        }
        PatchedManagerRequest: {
            /** Nom */
            name?: string
            /** Courriel */
            email?: string
            /** Fonction */
            title?: string
            /** Actif */
            is_active?: boolean
        }
        PatchedMarketingCategoryRequest: {
            /** Pays */
            country?: number
            /** Nom */
            name?: string
            description?: string
            /** Actif */
            is_active?: boolean
        }
        /**
         * @description Préférences que le titulaire règle lui-même (``PATCH /api/me/``).
         *
         *     Seule la langue pour l'instant : le rôle, le périmètre et l'adresse
         *     e-mail restent du ressort du siège.
         */
        PatchedMePreferencesRequest: {
            language?: components["schemas"]["LanguageEnum"]
        }
        /**
         * @description Modification de la matrice : capacité → rôles, verrous vérifiés.
         *
         *     Une clé inconnue est refusée plutôt qu'ignorée ; une case figée qu'on
         *     tente de changer aussi, pour que l'appelant sache que rien n'a bougé.
         */
        PatchedPermissionMatrixUpdateRequest: {
            capabilities?: {
                [key: string]: ("super_admin" | "admin" | "df" | "dm" | "manager")[]
            }
        }
        PatchedProjectRequest: {
            /** Pays */
            country?: number
            /** Nom */
            name?: string
            description?: string
            /** Statut */
            status?: components["schemas"]["ProjectStatusEnum"]
            /** Format: decimal */
            budget?: string | null
            /** Actif */
            is_active?: boolean
        }
        PatchedProofRequest: {
            dossier?: number
            /**
             * Fichier
             * Format: binary
             */
            file?: string
            /** Type */
            kind?: components["schemas"]["ProofKindEnum"]
            replaces?: number | null
        }
        PatchedTeamRequest: {
            /** Pays */
            country?: number
            /** Nom */
            name?: string
            description?: string
            /** Actif */
            is_active?: boolean
        }
        /**
         * @description Création et mise à jour d'un compte par le siège.
         *
         *     ``username`` se choisit à la création et ne change plus. Toutes les
         *     identités de la plateforme sont stockées en texte sous ce nom — auteur
         *     d'une dépense, déposant d'une pièce, signataire d'une entrée de journal —
         *     et la règle des quatre yeux compare ce nom à celui de qui justifie.
         *     Renommer un compte romprait ces traces et permettrait, en changeant de
         *     nom entre la saisie et le constat, de justifier sa propre dépense. Le
         *     prénom et le nom, eux, restent libres : ils n'identifient rien.
         *
         *     ``must_change_password`` n'est pas modifiable : il est vrai dès qu'un
         *     mot de passe a été posé par un tiers, et seul son titulaire l'efface, en
         *     le remplaçant. Le siège ne peut pas déclarer personnel un mot de passe
         *     qu'il connaît. ``totp_confirmed`` non plus : seul le titulaire enrôle
         *     son application, le siège ne peut que réinitialiser (``reset-2fa``).
         *
         *     ``teams`` restreint la vue d'un manager à ces équipes (cf.
         *     ``UserProfile.team_ids``) ; chacune doit appartenir à un pays de
         *     ``countries``, sans quoi le compte verrait une équipe d'un pays qu'il
         *     n'a pas — ou n'en verrait aucune, sans que rien ne le dise.
         *
         *     L'adresse e-mail est obligatoire et professionnelle : c'est elle qui
         *     nomme le compte dans l'application d'authentification, et un compte
         *     d'entreprise ne se rattache pas à une adresse personnelle.
         */
        PatchedUserRequest: {
            /**
             * Nom d’utilisateur
             * @description Requis. 150 caractères maximum. Uniquement des lettres, nombres et les caractères « @ », « . », « + », « - » et « _ ».
             */
            username?: string
            /** Prénom */
            first_name?: string
            /** Nom */
            last_name?: string
            /** Format: email */
            email?: string
            /**
             * Actif
             * @description Précise si l’utilisateur doit être considéré comme actif. Décochez ceci plutôt que de supprimer le compte.
             */
            is_active?: boolean
            role?: components["schemas"]["RoleEnum"]
            countries?: number[]
            teams?: number[]
            password?: string
        }
        /**
         * @description Modification partielle de la politique du circuit.
         *
         *     Un paramètre inconnu est refusé plutôt qu'ignoré : un nom mal orthographié
         *     donnerait sinon l'impression qu'un réglage a été appliqué.
         */
        PatchedWorkflowConfigurationRequest: {
            require_review_step?: boolean
            unjustified_alert_days?: number
            alert_thresholds?: number[]
            /** Format: decimal */
            unusual_expense_factor?: string
            /** Politique de dépassement par défaut */
            default_overrun_policy?: components["schemas"]["OverrunPolicyEnum"]
            warn_without_proof_submission?: boolean
        }
        /**
         * @description * `cash` - Espèces
         *     * `transfer` - Virement
         *     * `mobile` - Mobile money
         *     * `card` - Carte
         *     * `check` - Chèque
         *     * `other` - Autre
         * @enum {string}
         */
        PaymentMethodEnum: "cash" | "transfer" | "mobile" | "card" | "check" | "other"
        /** @description Matrice rôle × capacité, telle que ``RolePermission`` l'applique. */
        PermissionMatrix: {
            readonly roles: components["schemas"]["PermissionMatrixRole"][]
            readonly capabilities: components["schemas"]["PermissionMatrixCapability"][]
            readonly note: string
        }
        PermissionMatrixCapability: {
            readonly key: string
            readonly group: string
            readonly label: string
            readonly description: string
            readonly roles: components["schemas"]["RoleEnum"][]
            readonly default_roles: components["schemas"]["RoleEnum"][]
            readonly fixed_roles: components["schemas"]["RoleEnum"][]
            readonly locked_roles: components["schemas"]["RoleEnum"][]
            readonly settable_by_roles: components["schemas"]["RoleEnum"][]
        }
        PermissionMatrixRole: {
            readonly value: components["schemas"]["RoleEnum"]
            readonly label: string
            readonly siege: boolean
            readonly always_global: boolean
        }
        Permissions: {
            /** @description Consulter la liste des comptes, leurs rôles et leurs périmètres. */
            readonly "users.read": boolean
            /** @description Ouvrir un compte et lui donner un rôle et un périmètre. */
            readonly "users.create": boolean
            /** @description Changer le rôle, le périmètre, activer ou désactiver, réinitialiser la double authentification. */
            readonly "users.update": boolean
            /** @description Lire la configuration, régler la politique du circuit et cette matrice. Réservé aux administrateurs, sans exception. */
            readonly "configuration.manage": boolean
            /** @description Relire la trace des actions sensibles, décisions du siège comprises. */
            readonly "audit.read": boolean
            /** @description Lire qui a modifié quoi dans le référentiel, sur son périmètre. */
            readonly "history.read": boolean
            /** @description Créer un pays parmi les filiales du groupe, ou un manager. */
            readonly "countries.create": boolean
            /** @description Changer la devise, le fuseau, les managers ; activer ou désactiver. */
            readonly "countries.update": boolean
            /** @description Ajouter une équipe, un centre de coûts, un projet, un intitulé, une catégorie, un bénéficiaire. */
            readonly "referentiel.create": boolean
            /** @description Renommer, rattacher, activer ou désactiver une entité du référentiel. */
            readonly "referentiel.update": boolean
            /** @description Créer une enveloppe annuelle ou une sous-enveloppe. */
            readonly "budgets.create": boolean
            /** @description Changer le montant, la politique de dépassement, désactiver ; valider une dépense qui dépasse son enveloppe. */
            readonly "budgets.update": boolean
            /** @description Proposer un transfert entre deux enveloppes. */
            readonly "reallocations.request": boolean
            /** @description Approuver ou refuser un transfert. Jamais le sien. */
            readonly "reallocations.decide": boolean
            /** @description Ajouter ou corriger un taux vers la devise de consolidation. */
            readonly "rates.manage": boolean
            /** @description Ouvrir un dossier, y ajouter des lignes de dépense. */
            readonly "expenses.create": boolean
            /** @description Corriger un dossier ou une ligne tant qu'ils ne sont pas soumis. */
            readonly "expenses.update": boolean
            /** @description Retirer un dossier ou une ligne jamais soumis. Son auteur seulement. */
            readonly "expenses.delete": boolean
            /** @description Joindre un justificatif, ou le remplacer, jusqu'à la clôture. */
            readonly "proofs.upload": boolean
            /** @description Déclarer un dossier : ses lignes partent avec lui, sans retour. */
            readonly "dossiers.submit": boolean
            /** @description Prendre un dossier soumis en contrôle : le DM prépare, le DF tranche. */
            readonly "expenses.review": boolean
            /** @description Constater qu'une pièce couvre une dépense, ou l'absence de preuve. */
            readonly "expenses.validate": boolean
            /** @description Déclarer l'affaire terminée une fois chaque ligne justifiée. */
            readonly "expenses.close": boolean
            /** @description Valider, rejeter ou signaler incomplet un justificatif. */
            readonly "proofs.review": boolean
            /** @description Renvoyer un dossier déclaré au pays pour demander des comptes, motif à l'appui. */
            readonly "dossiers.reopen": boolean
            /** @description Télécharger le registre en Excel, CSV, Word ou PDF. */
            readonly "data.export": boolean
            /** @description Charger un classeur de dépenses en brouillons. */
            readonly "data.import": boolean
        }
        Project: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string
            /** Nom */
            name: string
            description: string
            /** Statut */
            status: components["schemas"]["ProjectStatusEnum"]
            readonly status_display: string
            /** Format: decimal */
            budget: string | null
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        ProjectRequest: {
            /** Pays */
            country: number
            /** Nom */
            name: string
            description?: string
            /** Statut */
            status?: components["schemas"]["ProjectStatusEnum"]
            /** Format: decimal */
            budget?: string | null
            /** Actif */
            is_active?: boolean
        }
        /**
         * @description * `planned` - Planifié
         *     * `active` - En cours
         *     * `on_hold` - En pause
         *     * `completed` - Terminé
         * @enum {string}
         */
        ProjectStatusEnum: "planned" | "active" | "on_hold" | "completed"
        Proof: {
            readonly id: number
            dossier: number
            /** Nom d'origine */
            readonly original_name: string
            /** Type */
            kind: components["schemas"]["ProofKindEnum"]
            readonly kind_display: string
            /** Statut */
            readonly status: components["schemas"]["ProofStatusEnum"]
            readonly status_display: string
            /**
             * Justificatif complet
             * @description Reprend la nuance « reçu (justif incomplet) » du fichier source.
             */
            readonly is_complete: boolean
            /**
             * Empreinte SHA-256
             * @description Détecte toute modification ultérieure et les doublons.
             */
            readonly sha256: string
            /** Taille (octets) */
            readonly size: number
            /** Type MIME */
            readonly content_type: string
            readonly version: number
            replaces: number | null
            /** Déposé par */
            readonly uploaded_by: string
            /** Motif de rejet */
            readonly rejection_reason: string
            readonly download_url: string
            readonly allowed_reviews: components["schemas"]["ProofStatusEnum"][]
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        /**
         * @description * `receipt` - Reçu
         *     * `invoice` - Facture
         *     * `discharge` - Décharge
         *     * `deliverable` - Livrable
         *     * `other` - Autre
         * @enum {string}
         */
        ProofKindEnum: "receipt" | "invoice" | "discharge" | "deliverable" | "other"
        ProofRequest: {
            dossier: number
            /**
             * Fichier
             * Format: binary
             */
            file: string
            /** Type */
            kind?: components["schemas"]["ProofKindEnum"]
            replaces?: number | null
        }
        ProofReviewRequest: {
            status: components["schemas"]["ProofStatusEnum"]
            reason?: string
        }
        /**
         * @description * `received` - Reçu
         *     * `incomplete` - Incomplet
         *     * `to_review` - À contrôler
         *     * `validated` - Validé
         *     * `rejected` - Rejeté
         *     * `archived` - Archivé
         * @enum {string}
         */
        ProofStatusEnum: "received" | "incomplete" | "to_review" | "validated" | "rejected" | "archived"
        /** @description Motif accompagnant une décision ; obligatoire en cas de refus (§5.5). */
        ReallocationDecisionRequest: {
            note?: string
        }
        /**
         * @description * `pending` - En attente
         *     * `approved` - Approuvée
         *     * `rejected` - Refusée
         * @enum {string}
         */
        ReallocationStatusEnum: "pending" | "approved" | "rejected"
        /**
         * @description * `super_admin` - Super administrateur (DG, DO, CEO, DEV)
         *     * `admin` - Administrateur (RH)
         *     * `df` - DF — directeur financier (siège)
         *     * `dm` - DM — directeur manager (siège)
         *     * `manager` - Manager (pays)
         * @enum {string}
         */
        RoleEnum: "super_admin" | "admin" | "df" | "dm" | "manager"
        /**
         * @description Pays du périmètre, en représentation compacte.
         *
         *     Le fuseau et la devise y sont : un compte pays borne ses périodes dans
         *     l'heure de son pays et lit ses montants dans sa devise, et l'interface
         *     n'a pas à charger le référentiel entier pour le savoir.
         */
        ScopeCountry: {
            readonly id: number
            /** Nom */
            name: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref: string | null
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone: string
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
        }
        /**
         * @description Pays du périmètre, en représentation compacte.
         *
         *     Le fuseau et la devise y sont : un compte pays borne ses périodes dans
         *     l'heure de son pays et lit ses montants dans sa devise, et l'interface
         *     n'a pas à charger le référentiel entier pour le savoir.
         */
        ScopeCountryRequest: {
            /** Nom */
            name: string
            /**
             * Code ISO
             * @description ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.
             */
            code: string
            /**
             * Identifiant pays
             * @description Identifiant fonctionnel utilisé par le siège, ex. CT-01.
             */
            country_ref?: string | null
            /**
             * Fuseau horaire
             * @description Identifiant IANA, ex. Africa/Abidjan.
             */
            timezone?: string
            /**
             * Devise
             * @description ISO 4217
             */
            currency: string
        }
        /** @description Équipe du périmètre d'un manager, en représentation compacte. */
        ScopeTeam: {
            readonly id: number
            /** Nom */
            name: string
            /** Pays */
            country: number
        }
        /** @description Équipe du périmètre d'un manager, en représentation compacte. */
        ScopeTeamRequest: {
            /** Nom */
            name: string
            /** Pays */
            country: number
        }
        Team: {
            readonly id: number
            /** Pays */
            country: number
            readonly country_name: string
            /** Nom */
            name: string
            description: string
            /** Actif */
            is_active: boolean
            /**
             * Créé le
             * Format: date-time
             */
            readonly created_at: string
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        TeamRequest: {
            /** Pays */
            country: number
            /** Nom */
            name: string
            description?: string
            /** Actif */
            is_active?: boolean
        }
        /** @description Jeton d'API remis à la connexion et au changement de mot de passe. */
        Token: {
            readonly token: string
        }
        /** @description Refus de ``/api/token-auth/`` quand le second facteur manque ou est faux. */
        TokenAuthError: {
            readonly code: string[]
            readonly totp_required: boolean
        }
        /** @description Identifiants présentés à ``/api/token-auth/``. */
        TokenAuthRequest: {
            username: string
            password: string
            /** @description Code de double authentification, exigé dès que le compte est enrôlé (réponse 400 avec ``totp_required`` sinon). */
            code?: string
        }
        /** @description Code à six chiffres présenté pour confirmer l'enrôlement. */
        TotpCodeRequest: {
            code: string
        }
        TotpConfirmed: {
            readonly totp_confirmed: boolean
        }
        /** @description Secret d'enrôlement, remis une seule fois. */
        TotpEnrolment: {
            readonly otpauth_uri: string
            readonly qr_png_base64: string
            readonly secret: string
        }
        /**
         * @description * `edit` - edit
         *     * `add_line` - add_line
         *     * `upload` - upload
         *     * `delete` - delete
         *     * `submit` - submit
         *     * `review` - review
         *     * `justify` - justify
         *     * `reject` - reject
         *     * `close` - close
         *     * `reopen` - reopen
         * @enum {string}
         */
        TransitionEnum: "edit" | "add_line" | "upload" | "delete" | "submit" | "review" | "justify" | "reject" | "close" | "reopen"
        /**
         * @description Motif accompagnant une transition ; obligatoire pour un rejet (§5.5)
         *     et pour une réouverture.
         */
        TransitionRequest: {
            note?: string
        }
        /** @description Forme documentaire de ``/api/notifications/unread_count/``. */
        UnreadCount: {
            readonly unread: number
        }
        /**
         * @description Création et mise à jour d'un compte par le siège.
         *
         *     ``username`` se choisit à la création et ne change plus. Toutes les
         *     identités de la plateforme sont stockées en texte sous ce nom — auteur
         *     d'une dépense, déposant d'une pièce, signataire d'une entrée de journal —
         *     et la règle des quatre yeux compare ce nom à celui de qui justifie.
         *     Renommer un compte romprait ces traces et permettrait, en changeant de
         *     nom entre la saisie et le constat, de justifier sa propre dépense. Le
         *     prénom et le nom, eux, restent libres : ils n'identifient rien.
         *
         *     ``must_change_password`` n'est pas modifiable : il est vrai dès qu'un
         *     mot de passe a été posé par un tiers, et seul son titulaire l'efface, en
         *     le remplaçant. Le siège ne peut pas déclarer personnel un mot de passe
         *     qu'il connaît. ``totp_confirmed`` non plus : seul le titulaire enrôle
         *     son application, le siège ne peut que réinitialiser (``reset-2fa``).
         *
         *     ``teams`` restreint la vue d'un manager à ces équipes (cf.
         *     ``UserProfile.team_ids``) ; chacune doit appartenir à un pays de
         *     ``countries``, sans quoi le compte verrait une équipe d'un pays qu'il
         *     n'a pas — ou n'en verrait aucune, sans que rien ne le dise.
         *
         *     L'adresse e-mail est obligatoire et professionnelle : c'est elle qui
         *     nomme le compte dans l'application d'authentification, et un compte
         *     d'entreprise ne se rattache pas à une adresse personnelle.
         */
        User: {
            readonly id: number
            /**
             * Nom d’utilisateur
             * @description Requis. 150 caractères maximum. Uniquement des lettres, nombres et les caractères « @ », « . », « + », « - » et « _ ».
             */
            username: string
            /** Prénom */
            first_name: string
            /** Nom */
            last_name: string
            /** Format: email */
            email: string
            /**
             * Actif
             * @description Précise si l’utilisateur doit être considéré comme actif. Décochez ceci plutôt que de supprimer le compte.
             */
            is_active: boolean
            role: components["schemas"]["RoleEnum"]
            countries: number[]
            readonly countries_detail: components["schemas"]["ScopeCountry"][]
            teams: number[]
            readonly teams_detail: components["schemas"]["ScopeTeam"][]
            readonly must_change_password: boolean
            readonly totp_confirmed: boolean
        }
        /**
         * @description Création et mise à jour d'un compte par le siège.
         *
         *     ``username`` se choisit à la création et ne change plus. Toutes les
         *     identités de la plateforme sont stockées en texte sous ce nom — auteur
         *     d'une dépense, déposant d'une pièce, signataire d'une entrée de journal —
         *     et la règle des quatre yeux compare ce nom à celui de qui justifie.
         *     Renommer un compte romprait ces traces et permettrait, en changeant de
         *     nom entre la saisie et le constat, de justifier sa propre dépense. Le
         *     prénom et le nom, eux, restent libres : ils n'identifient rien.
         *
         *     ``must_change_password`` n'est pas modifiable : il est vrai dès qu'un
         *     mot de passe a été posé par un tiers, et seul son titulaire l'efface, en
         *     le remplaçant. Le siège ne peut pas déclarer personnel un mot de passe
         *     qu'il connaît. ``totp_confirmed`` non plus : seul le titulaire enrôle
         *     son application, le siège ne peut que réinitialiser (``reset-2fa``).
         *
         *     ``teams`` restreint la vue d'un manager à ces équipes (cf.
         *     ``UserProfile.team_ids``) ; chacune doit appartenir à un pays de
         *     ``countries``, sans quoi le compte verrait une équipe d'un pays qu'il
         *     n'a pas — ou n'en verrait aucune, sans que rien ne le dise.
         *
         *     L'adresse e-mail est obligatoire et professionnelle : c'est elle qui
         *     nomme le compte dans l'application d'authentification, et un compte
         *     d'entreprise ne se rattache pas à une adresse personnelle.
         */
        UserRequest: {
            /**
             * Nom d’utilisateur
             * @description Requis. 150 caractères maximum. Uniquement des lettres, nombres et les caractères « @ », « . », « + », « - » et « _ ».
             */
            username: string
            /** Prénom */
            first_name?: string
            /** Nom */
            last_name?: string
            /** Format: email */
            email: string
            /**
             * Actif
             * @description Précise si l’utilisateur doit être considéré comme actif. Décochez ceci plutôt que de supprimer le compte.
             */
            is_active?: boolean
            role: components["schemas"]["RoleEnum"]
            countries?: number[]
            teams?: number[]
            password?: string
        }
        /**
         * @description Modification partielle de la politique du circuit.
         *
         *     Un paramètre inconnu est refusé plutôt qu'ignoré : un nom mal orthographié
         *     donnerait sinon l'impression qu'un réglage a été appliqué.
         */
        WorkflowConfiguration: {
            require_review_step: boolean
            unjustified_alert_days: number
            alert_thresholds: number[]
            /** Format: decimal */
            unusual_expense_factor: string
            /** Politique de dépassement par défaut */
            default_overrun_policy: components["schemas"]["OverrunPolicyEnum"]
            readonly default_overrun_policy_display: string
            warn_without_proof_submission: boolean
            /**
             * Modifié le
             * Format: date-time
             */
            readonly updated_at: string
        }
        /**
         * @description * `draft` - Brouillon
         *     * `submitted` - Soumis
         *     * `in_review` - En contrôle
         *     * `justified` - Justifié
         *     * `unjustified` - Non justifié
         *     * `closed` - Clôturé
         * @enum {string}
         */
        WorkflowStatusEnum: "draft" | "submitted" | "in_review" | "justified" | "unjustified" | "closed"
        Workload: {
            readonly expenses_to_review: number
            readonly expenses_draft: number
            readonly expenses_unjustified: number
            readonly dossiers_open: number
        }
    }
    responses: never
    parameters: never
    requestBodies: never
    headers: never
    pathItems: never
}
export type $defs = Record<string, never>
export interface operations {
    audit_list: {
        parameters: {
            query?: {
                /**
                 * @description * `created` - Création
                 *     * `updated` - Modification
                 *     * `submitted` - Soumission
                 *     * `reviewed` - Mise en contrôle
                 *     * `justified` - Justification
                 *     * `unjustified` - Constat de non-justification
                 *     * `approved` - Validation d'un justificatif
                 *     * `rejected` - Rejet d'un justificatif
                 *     * `proof_incomplete` - Justificatif signalé incomplet
                 *     * `proof_to_review` - Justificatif remis à contrôler
                 *     * `deleted` - Suppression d'un brouillon
                 *     * `closed` - Clôture
                 *     * `reopened` - Réouverture
                 *     * `proof_uploaded` - Dépôt de justificatif
                 *     * `proof_replaced` - Remplacement de justificatif
                 *     * `downloaded` - Téléchargement
                 *     * `imported` - Import Excel
                 */
                action?: "approved" | "closed" | "created" | "deleted" | "downloaded" | "imported" | "justified" | "proof_incomplete" | "proof_replaced" | "proof_to_review" | "proof_uploaded" | "rejected" | "reopened" | "reviewed" | "submitted" | "unjustified" | "updated"
                country?: number
                object_type?: string
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
                user?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedAuditLogList"]
                }
            }
        }
    }
    audit_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Journal d'audit. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["AuditLog"]
                }
            }
        }
    }
    beneficiaries_list: {
        parameters: {
            query?: {
                country?: number
                is_active?: boolean
                /**
                 * @description * `prospect` - Prospect
                 *     * `client` - Client
                 *     * `supplier` - Fournisseur
                 *     * `beneficiary` - Bénéficiaire
                 *     * `other` - Autre
                 */
                kind?: "beneficiary" | "client" | "other" | "prospect" | "supplier"
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedBeneficiaryList"]
                }
            }
        }
    }
    beneficiaries_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["BeneficiaryRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["BeneficiaryRequest"]
                "multipart/form-data": components["schemas"]["BeneficiaryRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Beneficiary"]
                }
            }
        }
    }
    beneficiaries_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Bénéficiaire. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Beneficiary"]
                }
            }
        }
    }
    beneficiaries_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Bénéficiaire. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["BeneficiaryRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["BeneficiaryRequest"]
                "multipart/form-data": components["schemas"]["BeneficiaryRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Beneficiary"]
                }
            }
        }
    }
    beneficiaries_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Bénéficiaire. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedBeneficiaryRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedBeneficiaryRequest"]
                "multipart/form-data": components["schemas"]["PatchedBeneficiaryRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Beneficiary"]
                }
            }
        }
    }
    budgets_list: {
        parameters: {
            query?: {
                country?: number
                country__country_ref?: string
                is_active?: boolean
                manager?: number
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                project?: number
                /** @description Un terme de recherche. */
                search?: string
                team?: number
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedBudgetList"]
                }
            }
        }
    }
    budgets_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["BudgetRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["BudgetRequest"]
                "multipart/form-data": components["schemas"]["BudgetRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Budget"]
                }
            }
        }
    }
    budgets_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Budget. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Budget"]
                }
            }
        }
    }
    budgets_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Budget. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["BudgetRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["BudgetRequest"]
                "multipart/form-data": components["schemas"]["BudgetRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Budget"]
                }
            }
        }
    }
    budgets_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Budget. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedBudgetRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedBudgetRequest"]
                "multipart/form-data": components["schemas"]["PatchedBudgetRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Budget"]
                }
            }
        }
    }
    budgets_summary_retrieve: {
        parameters: {
            query?: {
                /** @description Exercice consolidé ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["BudgetSummary"]
                }
            }
        }
    }
    configuration_retrieve: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Configuration"]
                }
            }
        }
    }
    cost_centers_list: {
        parameters: {
            query?: {
                country?: number
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedCostCenterList"]
                }
            }
        }
    }
    cost_centers_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["CostCenterRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["CostCenterRequest"]
                "multipart/form-data": components["schemas"]["CostCenterRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CostCenter"]
                }
            }
        }
    }
    cost_centers_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Centre de coûts. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CostCenter"]
                }
            }
        }
    }
    cost_centers_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Centre de coûts. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["CostCenterRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["CostCenterRequest"]
                "multipart/form-data": components["schemas"]["CostCenterRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CostCenter"]
                }
            }
        }
    }
    cost_centers_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Centre de coûts. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedCostCenterRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedCostCenterRequest"]
                "multipart/form-data": components["schemas"]["PatchedCostCenterRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CostCenter"]
                }
            }
        }
    }
    countries_list: {
        parameters: {
            query?: {
                country_ref?: string
                currency?: string
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedCountryListList"]
                }
            }
        }
    }
    countries_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["CountryWriteRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["CountryWriteRequest"]
                "multipart/form-data": components["schemas"]["CountryWriteRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CountryWrite"]
                }
            }
        }
    }
    countries_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pays. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CountryDetail"]
                }
            }
        }
    }
    countries_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pays. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["CountryWriteRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["CountryWriteRequest"]
                "multipart/form-data": components["schemas"]["CountryWriteRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CountryWrite"]
                }
            }
        }
    }
    countries_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pays. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedCountryWriteRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedCountryWriteRequest"]
                "multipart/form-data": components["schemas"]["PatchedCountryWriteRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["CountryWrite"]
                }
            }
        }
    }
    countries_disponibles_list: {
        parameters: {
            query?: {
                country_ref?: string
                currency?: string
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["AvailableCountry"][]
                }
            }
        }
    }
    dashboard_retrieve: {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Dashboard"]
                }
            }
        }
    }
    dashboard_breakdown_retrieve: {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Breakdown"]
                }
            }
        }
    }
    dossiers_list: {
        parameters: {
            query?: {
                country?: number
                country__country_ref?: string
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                owner?: number
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
                /**
                 * @description * `draft` - Brouillon
                 *     * `submitted` - Soumis
                 *     * `in_review` - En contrôle
                 *     * `justified` - Justifié
                 *     * `unjustified` - Non justifié
                 *     * `closed` - Clôturé
                 */
                status?: "closed" | "draft" | "in_review" | "justified" | "submitted" | "unjustified"
                team?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedDossierList"]
                }
            }
        }
    }
    dossiers_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["DossierRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["DossierRequest"]
                "multipart/form-data": components["schemas"]["DossierRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Dossier"]
                }
            }
        }
    }
    dossiers_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierDetail"]
                }
            }
        }
    }
    dossiers_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["DossierRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["DossierRequest"]
                "multipart/form-data": components["schemas"]["DossierRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Dossier"]
                }
            }
        }
    }
    dossiers_destroy: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown
                }
                content?: never
            }
        }
    }
    dossiers_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedDossierRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedDossierRequest"]
                "multipart/form-data": components["schemas"]["PatchedDossierRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Dossier"]
                }
            }
        }
    }
    dossiers_close_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["TransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TransitionRequest"]
                "multipart/form-data": components["schemas"]["TransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierTransitionResponse"]
                }
            }
        }
    }
    dossiers_justify_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["TransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TransitionRequest"]
                "multipart/form-data": components["schemas"]["TransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierTransitionResponse"]
                }
            }
        }
    }
    dossiers_reject_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["TransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TransitionRequest"]
                "multipart/form-data": components["schemas"]["TransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierTransitionResponse"]
                }
            }
        }
    }
    dossiers_reopen_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["TransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TransitionRequest"]
                "multipart/form-data": components["schemas"]["TransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierTransitionResponse"]
                }
            }
        }
    }
    dossiers_review_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["TransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TransitionRequest"]
                "multipart/form-data": components["schemas"]["TransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierTransitionResponse"]
                }
            }
        }
    }
    dossiers_submit_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dossier de justification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["TransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TransitionRequest"]
                "multipart/form-data": components["schemas"]["TransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["DossierTransitionResponse"]
                }
            }
        }
    }
    exchange_rates_list: {
        parameters: {
            query?: {
                currency?: string
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedExchangeRateList"]
                }
            }
        }
    }
    exchange_rates_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExchangeRateRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExchangeRateRequest"]
                "multipart/form-data": components["schemas"]["ExchangeRateRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExchangeRate"]
                }
            }
        }
    }
    exchange_rates_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Taux de change. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExchangeRate"]
                }
            }
        }
    }
    exchange_rates_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Taux de change. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExchangeRateRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExchangeRateRequest"]
                "multipart/form-data": components["schemas"]["ExchangeRateRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExchangeRate"]
                }
            }
        }
    }
    exchange_rates_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Taux de change. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedExchangeRateRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedExchangeRateRequest"]
                "multipart/form-data": components["schemas"]["PatchedExchangeRateRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExchangeRate"]
                }
            }
        }
    }
    expense_titles_list: {
        parameters: {
            query?: {
                country?: number
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedExpenseTitleList"]
                }
            }
        }
    }
    expense_titles_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseTitleRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseTitleRequest"]
                "multipart/form-data": components["schemas"]["ExpenseTitleRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTitle"]
                }
            }
        }
    }
    expense_titles_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Intitulé de dépenses. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTitle"]
                }
            }
        }
    }
    expense_titles_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Intitulé de dépenses. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseTitleRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseTitleRequest"]
                "multipart/form-data": components["schemas"]["ExpenseTitleRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTitle"]
                }
            }
        }
    }
    expense_titles_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Intitulé de dépenses. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedExpenseTitleRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedExpenseTitleRequest"]
                "multipart/form-data": components["schemas"]["PatchedExpenseTitleRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTitle"]
                }
            }
        }
    }
    expenses_list: {
        parameters: {
            query?: {
                beneficiary?: number
                country?: number
                country__country_ref?: string
                date__gte?: string
                date__lte?: string
                dossier?: number
                dossier__number?: string
                expense_title?: number
                marketing_category?: number
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                owner?: number
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /**
                 * @description * `cash` - Espèces
                 *     * `transfer` - Virement
                 *     * `mobile` - Mobile money
                 *     * `card` - Carte
                 *     * `check` - Chèque
                 *     * `other` - Autre
                 */
                payment_method?: "card" | "cash" | "check" | "mobile" | "other" | "transfer"
                project?: number
                /** @description Un terme de recherche. */
                search?: string
                /**
                 * @description * `draft` - Brouillon
                 *     * `submitted` - Soumis
                 *     * `in_review` - En contrôle
                 *     * `justified` - Justifié
                 *     * `unjustified` - Non justifié
                 *     * `closed` - Clôturé
                 */
                status?: "closed" | "draft" | "in_review" | "justified" | "submitted" | "unjustified"
                /** @description Les valeurs multiples doivent être séparées par des virgules. */
                status__in?: string[]
                team?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedExpenseList"]
                }
            }
        }
    }
    expenses_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseRequest"]
                "multipart/form-data": components["schemas"]["ExpenseRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Expense"]
                }
            }
        }
    }
    expenses_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Expense"]
                }
            }
        }
    }
    expenses_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseRequest"]
                "multipart/form-data": components["schemas"]["ExpenseRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Expense"]
                }
            }
        }
    }
    expenses_destroy: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown
                }
                content?: never
            }
        }
    }
    expenses_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedExpenseRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedExpenseRequest"]
                "multipart/form-data": components["schemas"]["PatchedExpenseRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Expense"]
                }
            }
        }
    }
    expenses_close_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ExpenseTransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseTransitionRequest"]
                "multipart/form-data": components["schemas"]["ExpenseTransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTransitionResponse"]
                }
            }
        }
    }
    expenses_justify_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ExpenseTransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseTransitionRequest"]
                "multipart/form-data": components["schemas"]["ExpenseTransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTransitionResponse"]
                }
            }
        }
    }
    expenses_reject_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ExpenseTransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseTransitionRequest"]
                "multipart/form-data": components["schemas"]["ExpenseTransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTransitionResponse"]
                }
            }
        }
    }
    expenses_review_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Dépense. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ExpenseTransitionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ExpenseTransitionRequest"]
                "multipart/form-data": components["schemas"]["ExpenseTransitionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ExpenseTransitionResponse"]
                }
            }
        }
    }
    expenses_register_list: {
        parameters: {
            query?: {
                beneficiary?: number
                country?: number
                country__country_ref?: string
                date__gte?: string
                date__lte?: string
                dossier?: number
                dossier__number?: string
                expense_title?: number
                marketing_category?: number
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                owner?: number
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /**
                 * @description * `cash` - Espèces
                 *     * `transfer` - Virement
                 *     * `mobile` - Mobile money
                 *     * `card` - Carte
                 *     * `check` - Chèque
                 *     * `other` - Autre
                 */
                payment_method?: "card" | "cash" | "check" | "mobile" | "other" | "transfer"
                project?: number
                /** @description Un terme de recherche. */
                search?: string
                /**
                 * @description * `draft` - Brouillon
                 *     * `submitted` - Soumis
                 *     * `in_review` - En contrôle
                 *     * `justified` - Justifié
                 *     * `unjustified` - Non justifié
                 *     * `closed` - Clôturé
                 */
                status?: "closed" | "draft" | "in_review" | "justified" | "submitted" | "unjustified"
                /** @description Les valeurs multiples doivent être séparées par des virgules. */
                status__in?: string[]
                team?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedExpenseRegisterList"]
                }
            }
        }
    }
    "exports_expenses.csv_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    "exports_expenses.docx_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    "exports_expenses.xlsx_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    "exports_reconciliation.csv_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    "exports_reconciliation.docx_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    "exports_reconciliation.xlsx_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    "exports_report.pdf_retrieve": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Mois (1-12) ; sans lui, l'exercice entier. */
                month?: number
                /** @description Exercice ; l'année en cours par défaut. */
                year?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    health_retrieve: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Health"]
                }
            }
            503: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Health"]
                }
            }
        }
    }
    history_list: {
        parameters: {
            query?: {
                /**
                 * @description * `created` - Création
                 *     * `updated` - Mise à jour
                 *     * `reassigned` - Changement de rattachement
                 *     * `deactivated` - Désactivation
                 *     * `reactivated` - Réactivation
                 *     * `deleted` - Suppression
                 *     * `password_reset` - Réinitialisation du mot de passe
                 *     * `password_changed` - Changement de mot de passe
                 *     * `login` - Connexion
                 *     * `login_failed` - Échec de connexion
                 *     * `logout` - Déconnexion
                 *     * `totp_confirmed` - Double authentification activée
                 *     * `totp_reset` - Double authentification réinitialisée
                 */
                action?: "created" | "deactivated" | "deleted" | "login" | "login_failed" | "logout" | "password_changed" | "password_reset" | "reactivated" | "reassigned" | "totp_confirmed" | "totp_reset" | "updated"
                country?: number
                /**
                 * @description * `country` - Pays
                 *     * `manager` - Manager
                 *     * `team` - Équipe
                 *     * `cost_center` - Centre de coûts
                 *     * `project` - Projet
                 *     * `expense_title` - Intitulé de dépenses
                 *     * `marketing_category` - Catégorie marketing
                 *     * `budget` - Enveloppe budgétaire
                 *     * `reallocation` - Réallocation budgétaire
                 *     * `exchange_rate` - Taux de change
                 *     * `workflow_configuration` - Configuration du workflow
                 *     * `user` - Compte utilisateur
                 */
                model_name?: "budget" | "cost_center" | "country" | "exchange_rate" | "expense_title" | "manager" | "marketing_category" | "project" | "reallocation" | "team" | "user" | "workflow_configuration"
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedChangeLogList"]
                }
            }
        }
    }
    history_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Historique. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ChangeLog"]
                }
            }
        }
    }
    "imports_expenses.xlsx_create": {
        parameters: {
            query?: {
                /** @description Pays ; un pays inconnu ou hors périmètre répond 404. */
                country?: number
                /** @description Valide le classeur sans rien écrire. */
                dry_run?: boolean
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["ImportRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["ImportResult"]
                }
            }
        }
    }
    logout_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown
                }
                content?: never
            }
        }
    }
    managers_list: {
        parameters: {
            query?: {
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedManagerList"]
                }
            }
        }
    }
    managers_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ManagerRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ManagerRequest"]
                "multipart/form-data": components["schemas"]["ManagerRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Manager"]
                }
            }
        }
    }
    managers_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) manager. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Manager"]
                }
            }
        }
    }
    managers_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) manager. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ManagerRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ManagerRequest"]
                "multipart/form-data": components["schemas"]["ManagerRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Manager"]
                }
            }
        }
    }
    managers_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) manager. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedManagerRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedManagerRequest"]
                "multipart/form-data": components["schemas"]["PatchedManagerRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Manager"]
                }
            }
        }
    }
    marketing_categories_list: {
        parameters: {
            query?: {
                country?: number
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedMarketingCategoryList"]
                }
            }
        }
    }
    marketing_categories_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarketingCategoryRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["MarketingCategoryRequest"]
                "multipart/form-data": components["schemas"]["MarketingCategoryRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["MarketingCategory"]
                }
            }
        }
    }
    marketing_categories_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Catégorie marketing. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["MarketingCategory"]
                }
            }
        }
    }
    marketing_categories_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Catégorie marketing. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarketingCategoryRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["MarketingCategoryRequest"]
                "multipart/form-data": components["schemas"]["MarketingCategoryRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["MarketingCategory"]
                }
            }
        }
    }
    marketing_categories_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Catégorie marketing. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedMarketingCategoryRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedMarketingCategoryRequest"]
                "multipart/form-data": components["schemas"]["PatchedMarketingCategoryRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["MarketingCategory"]
                }
            }
        }
    }
    me_retrieve: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Me"]
                }
            }
        }
    }
    me_partial_update: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedMePreferencesRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedMePreferencesRequest"]
                "multipart/form-data": components["schemas"]["PatchedMePreferencesRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Me"]
                }
            }
        }
    }
    me_2fa_confirm_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["TotpCodeRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TotpCodeRequest"]
                "multipart/form-data": components["schemas"]["TotpCodeRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["TotpConfirmed"]
                }
            }
        }
    }
    me_2fa_enrol_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["TotpEnrolment"]
                }
            }
        }
    }
    me_password_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ChangePasswordRequest"]
                "multipart/form-data": components["schemas"]["ChangePasswordRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Token"]
                }
            }
        }
    }
    notifications_list: {
        parameters: {
            query?: {
                country?: number
                /**
                 * @description * `budget_threshold` - Seuil budgétaire atteint
                 *     * `budget_overrun` - Dépassement budgétaire
                 *     * `expense_submitted` - Dépense à contrôler
                 *     * `expense_rejected` - Dépense rejetée
                 *     * `proof_missing` - Justificatif manquant
                 *     * `proof_incomplete` - Justificatif incomplet
                 *     * `reallocation_requested` - Demande de réallocation
                 *     * `storage_error` - Anomalie de stockage
                 *     * `dossier_reopened` - Dossier rouvert
                 */
                kind?: "budget_overrun" | "budget_threshold" | "dossier_reopened" | "expense_rejected" | "expense_submitted" | "proof_incomplete" | "proof_missing" | "reallocation_requested" | "storage_error"
                /**
                 * @description * `info` - Information
                 *     * `warning` - Avertissement
                 *     * `critical` - Critique
                 */
                level?: "critical" | "info" | "warning"
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedNotificationList"]
                }
            }
        }
    }
    notifications_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Notification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Notification"]
                }
            }
        }
    }
    notifications_read_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Notification. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Notification"]
                }
            }
        }
    }
    notifications_read_all_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["MarkedRead"]
                }
            }
        }
    }
    notifications_unread_count_retrieve: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["UnreadCount"]
                }
            }
        }
    }
    permissions_retrieve: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PermissionMatrix"]
                }
            }
        }
    }
    permissions_partial_update: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedPermissionMatrixUpdateRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedPermissionMatrixUpdateRequest"]
                "multipart/form-data": components["schemas"]["PatchedPermissionMatrixUpdateRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PermissionMatrix"]
                }
            }
        }
    }
    projects_list: {
        parameters: {
            query?: {
                country?: number
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
                /**
                 * @description * `planned` - Planifié
                 *     * `active` - En cours
                 *     * `on_hold` - En pause
                 *     * `completed` - Terminé
                 */
                status?: "active" | "completed" | "on_hold" | "planned"
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedProjectList"]
                }
            }
        }
    }
    projects_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ProjectRequest"]
                "multipart/form-data": components["schemas"]["ProjectRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Project"]
                }
            }
        }
    }
    projects_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Projet. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Project"]
                }
            }
        }
    }
    projects_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Projet. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ProjectRequest"]
                "multipart/form-data": components["schemas"]["ProjectRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Project"]
                }
            }
        }
    }
    projects_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Projet. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedProjectRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedProjectRequest"]
                "multipart/form-data": components["schemas"]["PatchedProjectRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Project"]
                }
            }
        }
    }
    proofs_list: {
        parameters: {
            query?: {
                dossier?: number
                is_complete?: boolean
                /**
                 * @description * `receipt` - Reçu
                 *     * `invoice` - Facture
                 *     * `discharge` - Décharge
                 *     * `deliverable` - Livrable
                 *     * `other` - Autre
                 */
                kind?: "deliverable" | "discharge" | "invoice" | "other" | "receipt"
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
                /**
                 * @description * `received` - Reçu
                 *     * `incomplete` - Incomplet
                 *     * `to_review` - À contrôler
                 *     * `validated` - Validé
                 *     * `rejected` - Rejeté
                 *     * `archived` - Archivé
                 */
                status?: "archived" | "incomplete" | "received" | "rejected" | "to_review" | "validated"
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedProofList"]
                }
            }
        }
    }
    proofs_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["ProofRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Proof"]
                }
            }
        }
    }
    proofs_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pièce justificative. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Proof"]
                }
            }
        }
    }
    proofs_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pièce justificative. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProofRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ProofRequest"]
                "multipart/form-data": components["schemas"]["ProofRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Proof"]
                }
            }
        }
    }
    proofs_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pièce justificative. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedProofRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedProofRequest"]
                "multipart/form-data": components["schemas"]["PatchedProofRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Proof"]
                }
            }
        }
    }
    proofs_download_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pièce justificative. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/octet-stream": string
                }
            }
        }
    }
    proofs_review_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Pièce justificative. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProofReviewRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ProofReviewRequest"]
                "multipart/form-data": components["schemas"]["ProofReviewRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Proof"]
                }
            }
        }
    }
    reallocations_list: {
        parameters: {
            query?: {
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
                source__country?: number
                /**
                 * @description * `pending` - En attente
                 *     * `approved` - Approuvée
                 *     * `rejected` - Refusée
                 */
                status?: "approved" | "pending" | "rejected"
                target__country?: number
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedBudgetReallocationList"]
                }
            }
        }
    }
    reallocations_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["BudgetReallocationRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["BudgetReallocationRequest"]
                "multipart/form-data": components["schemas"]["BudgetReallocationRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["BudgetReallocation"]
                }
            }
        }
    }
    reallocations_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Réallocation budgétaire. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["BudgetReallocation"]
                }
            }
        }
    }
    reallocations_approve_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Réallocation budgétaire. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ReallocationDecisionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ReallocationDecisionRequest"]
                "multipart/form-data": components["schemas"]["ReallocationDecisionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["BudgetReallocation"]
                }
            }
        }
    }
    reallocations_reject_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Réallocation budgétaire. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ReallocationDecisionRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["ReallocationDecisionRequest"]
                "multipart/form-data": components["schemas"]["ReallocationDecisionRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["BudgetReallocation"]
                }
            }
        }
    }
    teams_list: {
        parameters: {
            query?: {
                country?: number
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedTeamList"]
                }
            }
        }
    }
    teams_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["TeamRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TeamRequest"]
                "multipart/form-data": components["schemas"]["TeamRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Team"]
                }
            }
        }
    }
    teams_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Équipe. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Team"]
                }
            }
        }
    }
    teams_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Équipe. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["TeamRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["TeamRequest"]
                "multipart/form-data": components["schemas"]["TeamRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Team"]
                }
            }
        }
    }
    teams_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) Équipe. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedTeamRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedTeamRequest"]
                "multipart/form-data": components["schemas"]["PatchedTeamRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Team"]
                }
            }
        }
    }
    token_auth_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/x-www-form-urlencoded": components["schemas"]["TokenAuthRequest"]
                "multipart/form-data": components["schemas"]["TokenAuthRequest"]
                "application/json": components["schemas"]["TokenAuthRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["Token"]
                }
            }
            400: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["TokenAuthError"]
                }
            }
        }
    }
    users_list: {
        parameters: {
            query?: {
                is_active?: boolean
                /** @description Quel champ utiliser pour classer les résultats. */
                ordering?: string
                /** @description Un numéro de page de l'ensemble des résultats. */
                page?: number
                /** @description Nombre de résultats à retourner par page. */
                page_size?: number
                /**
                 * @description * `super_admin` - Super administrateur (DG, DO, CEO, DEV)
                 *     * `admin` - Administrateur (RH)
                 *     * `df` - DF — directeur financier (siège)
                 *     * `dm` - DM — directeur manager (siège)
                 *     * `manager` - Manager (pays)
                 */
                profile__role?: "admin" | "df" | "dm" | "manager" | "super_admin"
                /** @description Un terme de recherche. */
                search?: string
            }
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["PaginatedUserList"]
                }
            }
        }
    }
    users_create: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["UserRequest"]
                "multipart/form-data": components["schemas"]["UserRequest"]
            }
        }
        responses: {
            201: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["User"]
                }
            }
        }
    }
    users_retrieve: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) utilisateur. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["User"]
                }
            }
        }
    }
    users_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) utilisateur. */
                id: number
            }
            cookie?: never
        }
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["UserRequest"]
                "multipart/form-data": components["schemas"]["UserRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["User"]
                }
            }
        }
    }
    users_partial_update: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) utilisateur. */
                id: number
            }
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedUserRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedUserRequest"]
                "multipart/form-data": components["schemas"]["PatchedUserRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["User"]
                }
            }
        }
    }
    users_reset_2fa_create: {
        parameters: {
            query?: never
            header?: never
            path: {
                /** @description Un(une) valeur entière unique identifiant ce(cette) utilisateur. */
                id: number
            }
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["User"]
                }
            }
        }
    }
    workflow_configuration_retrieve: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: never
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["WorkflowConfiguration"]
                }
            }
        }
    }
    workflow_configuration_partial_update: {
        parameters: {
            query?: never
            header?: never
            path?: never
            cookie?: never
        }
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedWorkflowConfigurationRequest"]
                "application/x-www-form-urlencoded": components["schemas"]["PatchedWorkflowConfigurationRequest"]
                "multipart/form-data": components["schemas"]["PatchedWorkflowConfigurationRequest"]
            }
        }
        responses: {
            200: {
                headers: {
                    [name: string]: unknown
                }
                content: {
                    "application/json": components["schemas"]["WorkflowConfiguration"]
                }
            }
        }
    }
}
