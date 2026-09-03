"""Génération des exports Excel et PDF (§5.7).

L'export des dépenses reprend délibérément les colonnes du fichier Excel
d'origine — N°ORDRE, DATE, TEAM, OWNER, LIBELLE DES TRANSACTIONS, DEPENSES,
MONTANT JUSTIFIER, ECART, PIECES JUSTIFICATIVES — pour que les rapprochements
avec l'historique restent possibles.
"""

from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from budget.aggregates import budget_figures
from expenses.models import Proof

ZERO = Decimal("0.00")

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True)

EXPENSE_COLUMNS = [
    ("N°ORDRE", 16),
    ("DATE", 18),
    ("PAYS", 16),
    ("TEAM", 18),
    ("OWNER", 20),
    ("LIBELLE DES TRANSACTIONS", 38),
    ("DEPENSES", 16),
    # Ce que porte la pièce, quand le décaissement a eu lieu dans une autre
    # devise : sans ces colonnes, le rapprochement avec le justificatif est
    # impossible, aucun des chiffres du classeur n'y figurant.
    ("DEVISE D'ORIGINE", 16),
    ("MONTANT D'ORIGINE", 18),
    ("MONTANT JUSTIFIER", 18),
    ("ECART", 14),
    ("STATUT", 14),
    ("PIECES JUSTIFICATIVES", 30),
]


def _style_header(sheet, columns):
    for index, (title, width) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"


def _proof_summary(dossier):
    """Reprend la nuance « Reçu (justif incomplet) » du fichier d'origine."""
    labels = []
    for proof in dossier.proofs.all():
        if proof.status == Proof.ProofStatus.ARCHIVED:
            continue
        label = proof.get_kind_display()
        if not proof.is_complete:
            label += " (justif incomplet)"
        labels.append(label)
    return " ; ".join(labels)


def build_expenses_workbook(dossiers):
    """Classeur des lignes de dépenses, groupées par dossier."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "BASE DE DONNEES ACTIONS"
    _style_header(sheet, EXPENSE_COLUMNS)

    source = dossiers.prefetch_related("expenses__team", "expenses__owner", "proofs")
    row_index = 2
    totals = {"amount": ZERO, "justified": ZERO}

    for dossier in source:
        proofs = _proof_summary(dossier)
        for expense in dossier.expenses.all():
            gap = expense.amount - expense.justified_amount
            totals["amount"] += expense.amount
            totals["justified"] += expense.justified_amount
            values = [
                dossier.number,
                expense.date.strftime("%d/%m/%Y %H:%M"),
                dossier.country.name,
                expense.team.name if expense.team else "",
                expense.owner.name if expense.owner else "",
                expense.title,
                float(expense.amount),
                expense.original_currency or "",
                float(expense.original_amount)
                if expense.original_amount is not None
                else "",
                float(expense.justified_amount),
                float(gap),
                expense.get_status_display(),
                proofs,
            ]
            for column, value in enumerate(values, start=1):
                sheet.cell(row=row_index, column=column, value=value)
            row_index += 1

    if row_index > 2:
        sheet.cell(row=row_index, column=6, value="TOTAL").font = Font(bold=True)
        sheet.cell(row=row_index, column=7, value=float(totals["amount"])).font = Font(bold=True)
        sheet.cell(row=row_index, column=10, value=float(totals["justified"])).font = Font(bold=True)
        sheet.cell(
            row=row_index, column=11,
            value=float(totals["amount"] - totals["justified"]),
        ).font = Font(bold=True)

    return _to_bytes(workbook)


RECONCILIATION_COLUMNS = [
    ("PAYS", 20),
    ("ENVELOPPE", 30),
    ("DEVISE", 10),
    ("BUDGET", 16),
    ("ENGAGE", 16),
    ("CONSOMME", 16),
    ("JUSTIFIE", 16),
    ("ECART", 16),
    ("DISPONIBLE", 16),
    ("TAUX JUSTIFICATION", 20),
]


def build_reconciliation_workbook(budgets, dossiers):
    """Rapprochement enveloppe par enveloppe, puis dossier par dossier."""
    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Rapprochement budgets"
    _style_header(sheet, RECONCILIATION_COLUMNS)

    for index, budget in enumerate(budgets, start=2):
        figures = budget_figures(budget)
        rate = figures["justification_rate"]
        values = [
            budget.country.name,
            budget.project.name if budget.project else "Enveloppe du pays",
            budget.country.currency,
            float(budget.amount),
            float(figures["engaged"]),
            float(figures["consumed"]),
            float(figures["justified"]),
            float(figures["gap"]),
            float(figures["remaining"]),
            float(rate) if rate is not None else "",
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row=index, column=column, value=value)

    detail = workbook.create_sheet("Rapprochement dossiers")
    _style_header(
        detail,
        [
            ("N°ORDRE", 16), ("LIBELLE", 34), ("PAYS", 18), ("DATE", 14),
            ("STATUT", 14), ("DEPENSES", 16), ("JUSTIFIE", 16), ("ECART", 16),
            ("PIECES", 12),
        ],
    )
    for index, dossier in enumerate(dossiers.select_related("country"), start=2):
        totals = dossier.totals()
        values = [
            dossier.number,
            dossier.label,
            dossier.country.name,
            dossier.date.strftime("%d/%m/%Y"),
            dossier.get_status_display(),
            float(totals["amount"]),
            float(totals["justified"]),
            float(totals["gap"]),
            dossier.counts()["proofs"],
        ]
        for column, value in enumerate(values, start=1):
            detail.cell(row=index, column=column, value=value)

    return _to_bytes(workbook)


def _to_bytes(workbook):
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _fmt(value):
    return f"{Decimal(value):,.2f}".replace(",", " ")


def build_country_report_pdf(budgets, dossiers, expenses, year):
    """Rapport de synthèse par pays, avec ses enveloppes et ses dossiers."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Rapport de contrôle budgétaire {year}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitreRapport", parent=styles["Title"], fontSize=18, spaceAfter=4
    )
    story = [
        Paragraph(f"Contrôle budgétaire — {year}", title_style),
        Paragraph(
            "Montants exprimés dans la devise de chaque pays.", styles["Normal"]
        ),
        Spacer(1, 8 * mm),
    ]

    budget_rows = [[
        "Pays", "Enveloppe", "Budget", "Engagé", "Consommé", "Justifié", "Disponible",
    ]]
    for budget in budgets:
        figures = budget_figures(budget)
        budget_rows.append([
            budget.country.name,
            budget.project.name if budget.project else "Enveloppe du pays",
            _fmt(budget.amount),
            _fmt(figures["engaged"]),
            _fmt(figures["consumed"]),
            _fmt(figures["justified"]),
            _fmt(figures["remaining"]),
        ])

    story.append(Paragraph("Enveloppes", styles["Heading2"]))
    story.append(_table(budget_rows) if len(budget_rows) > 1 else _empty(styles))
    story.append(Spacer(1, 8 * mm))

    dossier_rows = [[
        "N°ORDRE", "Libellé", "Pays", "Date", "Statut", "Dépenses", "Justifié", "Écart",
    ]]
    for dossier in dossiers.select_related("country")[:200]:
        totals = dossier.totals()
        dossier_rows.append([
            dossier.number,
            dossier.label[:45],
            dossier.country.name,
            dossier.date.strftime("%d/%m/%Y"),
            dossier.get_status_display(),
            _fmt(totals["amount"]),
            _fmt(totals["justified"]),
            _fmt(totals["gap"]),
        ])

    story.append(Paragraph("Dossiers de justification", styles["Heading2"]))
    story.append(_table(dossier_rows) if len(dossier_rows) > 1 else _empty(styles))

    document.build(story)
    return buffer.getvalue()


def _empty(styles):
    return Paragraph("Aucune donnée sur la période.", styles["Italic"])


def _table(rows):
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B0B7C3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F8")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    return table
