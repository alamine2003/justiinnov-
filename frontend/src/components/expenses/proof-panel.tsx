import { useRef, useState, type FormEvent } from "react"
import { Download, Eye, FileCheck2, Loader2, Upload, X } from "lucide-react"
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
import { useReferentiel } from "@/lib/referentiel"
import {
  PROOF_KIND_LABELS,
  type Proof,
  type ProofStatus,
} from "@/lib/types"
import { formatDate } from "@/lib/utils"

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
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
  canUpload: boolean
  onChanged: () => Promise<void>
}

export function ProofPanel({
  dossierId,
  proofs,
  canUpload,
  onChanged,
}: ProofPanelProps) {
  const { can } = useAuth()
  const canReview = can("validate_expenses")

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
      setError(e instanceof Error ? e.message : "Téléchargement impossible")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Pièces justificatives</h3>
          <p className="text-xs text-muted-foreground">
            Rattachées au dossier ; chaque fichier porte son empreinte SHA-256.
          </p>
        </div>
        {canUpload && (
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="mr-1 h-4 w-4" aria-hidden />
            Déposer
          </Button>
        )}
      </div>

      <FormError>{error}</FormError>

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Fichier</TableHead>
              <TableHead scope="col">Type</TableHead>
              <TableHead scope="col">Statut</TableHead>
              <TableHead scope="col">Dépôt</TableHead>
              <TableHead scope="col" className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {proofs.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon={FileCheck2}
                title="Aucun justificatif"
                hint={
                  canUpload
                    ? "Déposez la facture, le reçu ou la décharge qui atteste la dépense."
                    : "Le dossier a été déclaré sans pièce."
                }
              />
            ) : (
              proofs.map((proof) => (
                <TableRow key={proof.id}>
                  <TableCell>
                    <p className="font-medium">{proof.original_name}</p>
                    <p className="font-mono text-xs text-muted-foreground">
                      v{proof.version} · {formatSize(proof.size)} ·{" "}
                      {proof.sha256.slice(0, 12)}…
                    </p>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {proof.kind_display || PROOF_KIND_LABELS[proof.kind] || proof.kind}
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
                    {proof.uploaded_by && `par ${proof.uploaded_by}`}
                  </TableCell>
                  <TableCell className="text-right">
                    {isPreviewable(proof) && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Prévisualiser ${proof.original_name}`}
                        onClick={() => setPreviewing(proof)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Télécharger ${proof.original_name}`}
                      disabled={busyId === proof.id}
                      onClick={() => void handleDownload(proof)}
                    >
                      {busyId === proof.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </Button>
                    {canReview && proof.status !== "archived" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Contrôler ${proof.original_name}`}
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
      setError("Sélectionnez un fichier.")
      return
    }
    if (rules.maxBytes && file.size > rules.maxBytes) {
      setError(
        `Le fichier pèse ${formatSize(file.size)} ; la limite est de ${formatSize(rules.maxBytes)}.`,
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
      setError(err instanceof Error ? err.message : "Dépôt impossible")
    } finally {
      setSaving(false)
      setProgress(null)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Déposer un justificatif</DialogTitle>
          <DialogDescription>
            {rules.formats.length > 0
              ? `Formats acceptés : ${rules.formats.join(", ")}.`
              : "PDF, image ou document."}{" "}
            Un fichier déjà présent sur ce dossier est refusé, sauf s'il
            remplace explicitement une version antérieure.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="proof-file">Fichier</Label>
            <Input id="proof-file" type="file" ref={fileRef} accept={rules.accept} required />
            {rules.maxBytes && (
              <p className="text-xs text-muted-foreground">
                Taille maximale : {formatSize(rules.maxBytes)}.
              </p>
            )}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="proof-kind">Type</Label>
            <NativeSelect
              id="proof-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {Object.entries(PROOF_KIND_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>
          {replaceable.length > 0 && (
            <div className="grid gap-2">
              <Label htmlFor="proof-replaces">Remplace (facultatif)</Label>
              <NativeSelect
                id="proof-replaces"
                value={replaces}
                onChange={(e) =>
                  setReplaces(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">Nouveau justificatif</option>
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
                aria-label="Envoi du fichier"
                value={progress}
                max={100}
                className="h-1.5 w-full overflow-hidden rounded-full bg-muted [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
              />
              <p className="text-xs text-muted-foreground">Envoi… {progress} %</p>
            </div>
          )}
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Déposer
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

const REVIEW_CHOICES: { value: ProofStatus; label: string }[] = [
  { value: "validated", label: "Valider la pièce" },
  { value: "to_review", label: "À contrôler" },
  { value: "incomplete", label: "Marquer incomplet" },
  { value: "rejected", label: "Rejeter" },
  { value: "archived", label: "Archiver" },
]

function ReviewDialog({
  proof,
  onClose,
  onReviewed,
}: {
  proof: Proof
  onClose: () => void
  onReviewed: () => Promise<void>
}) {
  const [status, setStatus] = useState<ProofStatus>("validated")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (status === "rejected" && !reason.trim()) {
      setError("Un rejet doit être motivé.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await reviewProof(proof.id, status, reason)
      await onReviewed()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Contrôle impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Contrôle documentaire</DialogTitle>
          <DialogDescription>
            {proof.original_name} — un rejet doit être motivé.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="review-status">Décision</Label>
            <NativeSelect
              id="review-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ProofStatus)}
            >
              {REVIEW_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          {status === "rejected" && (
            <div className="grid gap-2">
              <Label htmlFor="review-reason">Motif</Label>
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
                Annuler
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Enregistrer
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
