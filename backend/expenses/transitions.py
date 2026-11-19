"""Services de transition du circuit de justification (décision 41).

Les règles du circuit vivaient dans les vues : une commande ou un import qui
voulait soumettre un dossier devait fabriquer une requête HTTP. Elles sont
ici, sous forme de services purs — sans HTTP ni sérialisation — que les vues,
l'import et les commandes appellent :

- :func:`soumettre` — le dossier part avec ses lignes ;
- :func:`rouvrir` — seule exception à l'irréversibilité, motivée ;
- :func:`mettre_en_controle`, :func:`trancher`, :func:`cloturer` — les
  actes de contrôle du siège, sur un dossier ou sur une ligne ;
- :func:`retirer_brouillon` — un brouillon, par son auteur, avec ce qu'il
  contient s'il s'agit d'un dossier ;
- :func:`controler_piece` — le contrôle documentaire d'un justificatif ;
- :func:`demander_rectification`, :func:`approuver_rectification`,
  :func:`refuser_rectification` — la seconde exception à l'irréversibilité :
  un constat remis en cause sur demande motivée, tranché par un
  administrateur qui n'est pas le demandeur.

Chaque service prend les verrous (``select_for_update``), vérifie l'état
(``next_status``), la capacité (``ACTION_CAPACITES``), les quatre yeux, les lignes
exigées, l'imputation et la politique de dépassement, journalise via
``core.journal`` et déclenche les notifications. Il reçoit l'``Access`` de
celui qui agit et une :class:`~core.journal.Trace` (qui, depuis où) ; il
rend un :class:`Resultat` — l'instance après transition, l'avertissement
éventuel, les entrées de journal écrites.

Un refus est une exception de ``core.regles`` : la vue la traduit en 400,
403 ou 404 (:func:`~core.regles.traduire_les_regles`), une commande
l'attrape telle quelle. Les messages sont ceux que l'API renvoyait déjà.

Depuis la décision 131, ce module n'est plus qu'une façade : les services
vivent dans un module commun et cinq modules, un par sujet, et s'importent
ici sous les mêmes noms qu'avant — vues, import, commandes et tests n'ont
pas à savoir où.

- :mod:`expenses.exigences` — le résultat, les motifs exigés, les
  prédicats partagés, la relecture sous verrou ;
- :mod:`expenses.circuit` — le tronc commun, le dossier, la ligne, les
  services du circuit, :func:`executer`, :func:`renommer` ;
- :mod:`expenses.saisie` — les verrous et les règles de la saisie ;
- :mod:`expenses.retrait` — le retrait d'un brouillon ;
- :mod:`expenses.controle_des_pieces` — le contrôle d'un justificatif ;
- :mod:`expenses.rectifications` — la rectification.

Un test qui remplace une fonction (``mock.patch``) la remplace dans le
module où elle est appelée, pas ici : la façade n'en a qu'une copie du nom.
"""

from .circuit import (
    _CIRCUITS,
    _SERVICES,
    AUDIT_ACTIONS,
    SANS_PREUVE,
    _appliquer_a_la_ligne,
    _appliquer_au_dossier,
    _apres_sur_la_ligne,
    _apres_sur_le_dossier,
    _avant_sur_la_ligne,
    _avant_sur_le_dossier,
    _exiger_equipe_et_owner,
    _exiger_les_auteurs_des_lignes,
    _exiger_les_lignes,
    _instantane_de_la_ligne,
    _instantane_du_dossier,
    _rouvrir_les_lignes,
    _soumettre_les_lignes,
    _transition,
    _verrouiller_la_ligne,
    _verrouiller_le_dossier,
    cloturer,
    executer,
    mettre_en_controle,
    renommer,
    rouvrir,
    soumettre,
    trancher,
)
from .controle_des_pieces import (
    PROOF_AUDIT_ACTIONS,
    controler_piece,
)
from .exigences import (
    MOTIF_MANQUANT,
    VERROUILLE,
    Resultat,
    _detail,
    exiger_l_auteur_du_brouillon,
    exiger_les_quatre_yeux,
    exiger_un_brouillon,
    exiger_un_dossier_ouvert,
    exiger_une_ligne_jamais_rectifiee,
    relire_sous_verrou,
    sans_preuve,
)
from .rectifications import (
    _decider_la_demande,
    _exiger_le_perimetre,
    _journaliser_la_demande,
    _verrouiller_la_demande,
    approuver_rectification,
    demander_rectification,
    peut_decider_rectification,
    refuser_rectification,
    verifier_la_decision_de_rectification,
)
from .retrait import (
    _retirer_le_contenu,
    _retirer_les_pieces,
    retirer_brouillon,
)
from .saisie import (
    AJOUT_PAR_L_AUTEUR,
    preparer_l_ajout,
    preparer_la_modification,
    preparer_la_modification_du_dossier,
    verrouiller,
    verrouiller_le_dossier_vise,
)
from .workflow import PROOF_LOCKED_STATUSES

#: Tout ce que le module exposait avant la décision 131, sous le même nom.
#: ``PROOF_LOCKED_STATUSES`` y était importé, et ``pieces`` l'y lit.
__all__ = [
    "AJOUT_PAR_L_AUTEUR",
    "AUDIT_ACTIONS",
    "MOTIF_MANQUANT",
    "PROOF_AUDIT_ACTIONS",
    "PROOF_LOCKED_STATUSES",
    "Resultat",
    "SANS_PREUVE",
    "VERROUILLE",
    "_CIRCUITS",
    "_SERVICES",
    "_appliquer_a_la_ligne",
    "_appliquer_au_dossier",
    "_apres_sur_la_ligne",
    "_apres_sur_le_dossier",
    "_avant_sur_la_ligne",
    "_avant_sur_le_dossier",
    "_decider_la_demande",
    "_detail",
    "_exiger_equipe_et_owner",
    "_exiger_le_perimetre",
    "_exiger_les_auteurs_des_lignes",
    "_exiger_les_lignes",
    "_instantane_de_la_ligne",
    "_instantane_du_dossier",
    "_journaliser_la_demande",
    "_retirer_le_contenu",
    "_retirer_les_pieces",
    "_rouvrir_les_lignes",
    "_soumettre_les_lignes",
    "_transition",
    "_verrouiller_la_demande",
    "_verrouiller_la_ligne",
    "_verrouiller_le_dossier",
    "approuver_rectification",
    "cloturer",
    "controler_piece",
    "demander_rectification",
    "executer",
    "exiger_l_auteur_du_brouillon",
    "exiger_les_quatre_yeux",
    "exiger_un_brouillon",
    "exiger_un_dossier_ouvert",
    "exiger_une_ligne_jamais_rectifiee",
    "mettre_en_controle",
    "peut_decider_rectification",
    "preparer_l_ajout",
    "preparer_la_modification",
    "preparer_la_modification_du_dossier",
    "refuser_rectification",
    "relire_sous_verrou",
    "renommer",
    "retirer_brouillon",
    "rouvrir",
    "sans_preuve",
    "soumettre",
    "trancher",
    "verifier_la_decision_de_rectification",
    "verrouiller",
    "verrouiller_le_dossier_vise",
]
