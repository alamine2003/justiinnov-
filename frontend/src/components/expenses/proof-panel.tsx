import { useRef, useState, type FormEvent } from "react"
import { Download, Eye, FileCheck2, Loader2, Upload, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { EmptyRow } from "@/components/ui/table-states"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ProofPreview } from "@/components/expenses/proof-preview"
import { ProofStatusBadge } from "@/components/expenses/status-badge"
import { useAuth } from "@/context/use-auth"
import { fetchConfiguration } from "@/lib/accounts"
import {
  downloadProof,
  isPreviewable,
  reviewProof,
  uploadProof,
} from "@/lib/expenses"
import { PROOF_KINDS, proofKindLabel } from "@/lib/labels"
import { useReferentiel } from "@/lib/referentiel"
import type { Proof } from "@/lib/types"
import { formatDate } from "@/lib/utils"

function formatSize(t: TFunction, bytes: number) {
  if (bytes < 1024) return t("pieces.taille.octets", { valeur: bytes })
  if (bytes < 1024 * 1024) return t("pieces.taille.ko", { valeur: (bytes / 1024).toFixed(0) })
  return t("pieces.taille.mo", { valeur: (bytes / (1024 * 1024)).toFixed(1) })
}

/** Contraintes de dépôt, quand la configuration est lisible. */
interface UploadRules {
  accept?: string
  maxBytes?: number
  formats: string[]
}

interface ProofPanelProps {
  dossierId: number
  proofs: Proof[]
  /** Faux une fois le dossier clôturé : une preuve arrivée après coup se dépose jusque-là. */
  canUpload: boolean
  /** Le dossier est clôturé : l'état vide le dit, plutôt que d'inviter à déposer. */
  closed?: boolean
  onChanged: () => Promise<void>
}

/**
 * Décisions que le dialogue de contrôle sait proposer, dans cet ordre. Le
 * serveur dit lesquelles sont ouvertes (`allowed_reviews`) selon le rôle et
 * l'état ; l'archivage n'en fait jamais partie, il accompagne un remplacement.
 */
const REVIEW_CHOICES = ["validated", "to_review", "incomplete", "rejected"] as const

type ReviewChoice = (typeof REVIEW_CHOICES)[number]

function reviewChoices(proof: Proof): ReviewChoice[] {
  return REVIEW_CHOICES.filter((choice) => proof.allowed_reviews.includes(choice))
}

export function ProofPanel({
  dossierId,
  proofs,
  canUpload,
  closed = false,
  onChanged,
}: ProofPanelProps) {
  const { t } = useTranslation()
  const { can } = useAuth()

  // Les formats et la taille acceptés vivent dans la configuration du
  // serveur, réservée au siège. Un compte pays dépose sans ces garde-fous :
  // le serveur reste seul juge, l'écran ne fait qu'éviter un aller-retour.
  const configuration = useReferentiel("configuration", fetchConfiguration, {
    enabled: canUpload && can("manage_users"),
  })
  const rules: UploadRules = configuration.data
    ? {
        accept: configuration.data.justificatifs.formats_acceptes
          .map((f) => (f.startsWith(".") ? f : `.${f}`))
          .join(","),
        maxBytes: configuration.data.justificatifs.taille_max_mo * 1024 * 1024,
        formats: configuration.data.justificatifs.formats_acceptes,
      }
    : { formats: [] }

  const [uploadOpen, setUploadOpen] = useState(false)
  const [reviewing, setReviewing] = useState<Proof | null>(null)
  const [previewing, setPreviewing] = useState<Proof | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const handleDownload = async (proof: Proof) => {
    setBusyId(proof.id)
    setError(null)
    try {
      await downloadProof(proof)
    } catch (e) {
      setError(e instanceof Error ? e.message : t("pieces.telechargement_impossible"))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t("pieces.titre")}</h3>
          <p className="text-xs text-muted-foreground">{t("pieces.description")}</p>
        </div>
        {canUpload && (
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="mr-1 h-4 w-4" aria-hidden />
            {t("pieces.deposer")}
          </Button>
        )}
      </div>

      <FormError>{error}</FormError>

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("champs.file")}</TableHead>
              <TableHead scope="col">{t("champs.kind")}</TableHead>
              <TableHead scope="col">{t("commun.statut")}</TableHead>
              <TableHead scope="col">{t("pieces.colonnes.depot")}</TableHead>
              <TableHead scope="col" className="text-right">{t("commun.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {proofs.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon={FileCheck2}
                title={t("pieces.vide.titre")}
                hint={
                  canUpload
                    ? t("pieces.vide.aide_deposer")
                    : closed
                      ? t("pieces.vide.aide_cloture")
                      : t("pieces.vide.aide_sans_piece")
                }
              />
            ) : (
              proofs.map((proof) => (
                <TableRow key={proof.id}>
                  <TableCell>
                    <p className="font-medium">{proof.original_name}</p>
                    <p className="font-mono text-xs text-muted-foreground">
                      v{proof.version} · {formatSize(t, proof.size)} ·{" "}
                      {proof.sha256.slice(0, 12)}…
                    </p>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {proof.kind_display || proofKindLabel(t, proof.kind)}
                  </TableCell>
                  <TableCell>
                    <ProofStatusBadge status={proof.status} label={proof.status_display} />
                    {proof.rejection_reason && (
                      <p className="mt-1 max-w-[16rem] text-xs italic text-muted-foreground">
                        {proof.rejection_reason}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(proof.created_at)}
                    {proof.uploaded_by && <br />}
                    {proof.uploaded_by && t("pieces.par", { nom: proof.uploaded_by })}
                  </TableCell>
                  <TableCell className="text-right">
                    {isPreviewable(proof) && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("pieces.previsualiser_aria", { nom: proof.original_name })}
                        onClick={() => setPreviewing(proof)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("pieces.telecharger_aria", { nom: proof.original_name })}
                      disabled={busyId === proof.id}
                      onClick={() => void handleDownload(proof)}
                    >
                      {busyId === proof.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </Button>
                    {reviewChoices(proof).length > 0 && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("pieces.controler_aria", { nom: proof.original_name })}
                        onClick={() => setReviewing(proof)}
                      >
                        <FileCheck2 className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {uploadOpen && (
        <UploadDialog
          onOpenChange={setUploadOpen}
          dossierId={dossierId}
          proofs={proofs}
          rules={rules}
          onUploaded={onChanged}
        />
      )}

      {/* Clé sur la pièce : l'état du dialogue (décision, motif) repart de
          zéro d'une pièce à l'autre. */}
      {reviewing && (
        <ReviewDialog
          key={reviewing.id}
          proof={reviewing}
          onClose={() => setReviewing(null)}
          onReviewed={onChanged}
        />
      )}

      <ProofPreview proof={previewing} onClose={() => setPreviewing(null)} />
    </div>
  )
}

function UploadDialog({
  onOpenChange,
  dossierId,
  proofs,
  rules,
  onUploaded,
}: {
  onOpenChange: (open: boolean) => void
  dossierId: number
  proofs: Proof[]
  rules: UploadRules
  onUploaded: () => Promise<void>
}) {
  const { t } = useTranslation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState("receipt")
  const [replaces, setReplaces] = useState<number | "">("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)

  const replaceable = proofs.filter((p) => p.status !== "archived")

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setError(t("pieces.depot.fichier_requis"))
      return
    }
    if (rules.maxBytes && file.size > rules.maxBytes) {
      setError(
        t("pieces.depot.trop_gros", {
          taille: formatSize(t, file.size),
          limite: formatSize(t, rules.maxBytes),
        }),
      )
      return
    }
    setSaving(true)
    setError(null)
    setProgress(0)
    try {
      const form = new FormData()
      form.append("dossier", String(dossierId))
      form.append("kind", kind)
      form.append("file", file)
      if (replaces !== "") form.append("replaces", String(replaces))
      await uploadProof(form, (event) => {
        if (event.total) setProgress(Math.round((event.loaded / event.total) * 100))
      })
      await onUploaded()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("pieces.depot.impossible"))
    } finally {
      setSaving(false)
      setProgress(null)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("pieces.depot.titre")}</DialogTitle>
          <DialogDescription>
            {rules.formats.length > 0
              ? t("pieces.depot.formats", { formats: rules.formats.join(", ") })
              : t("pieces.depot.formats_generique")}{" "}
            {t("pieces.depot.doublon")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="proof-file">{t("champs.file")}</Label>
            <Input id="proof-file" type="file" ref={fileRef} accept={rules.accept} required />
            {rules.maxBytes && (
              <p className="text-xs text-muted-foreground">
                {t("pieces.depot.taille_max", { taille: formatSize(t, rules.maxBytes) })}
              </p>
            )}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="proof-kind">{t("champs.kind")}</Label>
            <NativeSelect
              id="proof-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {PROOF_KINDS.map((value) => (
                <option key={value} value={value}>
                  {proofKindLabel(t, value)}
                </option>
              ))}
            </NativeSelect>
          </div>
          {replaceable.length > 0 && (
            <div className="grid gap-2">
              <Label htmlFor="proof-replaces">{t("pieces.depot.remplace")}</Label>
              <NativeSelect
                id="proof-replaces"
                value={replaces}
                onChange={(e) =>
                  setReplaces(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">{t("pieces.depot.nouveau")}</option>
                {replaceable.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.original_name} (v{p.version})
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}
          {progress !== null && (
            <div className="grid gap-1">
              <progress
                aria-label={t("pieces.depot.envoi_aria")}
                value={progress}
                max={100}
                className="h-1.5 w-full overflow-hidden rounded-full bg-muted [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
              />
              <p className="text-xs text-muted-foreground">
                {t("pieces.depot.envoi", { pourcentage: progress })}
              </p>
            </div>
          )}
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("pieces.deposer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ReviewDialog({
  proof,
  onClose,
  onReviewed,
}: {
  proof: Proof
  onClose: () => void
  onReviewed: () => Promise<void>
}) {
  const { t } = useTranslation()
  const choices = reviewChoices(proof)
  const [status, setStatus] = useState<ReviewChoice>(choices[0] ?? "validated")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (status === "rejected" && !reason.trim()) {
      setError(t("pieces.controle.motif_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await reviewProof(proof.id, status, reason)
      await onReviewed()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t("pieces.controle.impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("pieces.controle.titre")}</DialogTitle>
          <DialogDescription>
            {t("pieces.controle.description", { nom: proof.original_name })}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="review-status">{t("pieces.controle.decision")}</Label>
            <NativeSelect
              id="review-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ReviewChoice)}
            >
              {choices.map((choice) => (
                <option key={choice} value={choice}>
                  {t(`pieces.controle.choix.${choice}`)}
                </option>
              ))}
            </NativeSelect>
          </div>
          {status === "rejected" && (
            <div className="grid gap-2">
              <Label htmlFor="review-reason">{t("champs.reason")}</Label>
              <Textarea
                id="review-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
              />
            </div>
          )}
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={onClose}>
                <X className="mr-1 h-4 w-4" aria-hidden />
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.enregistrer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
