import { useEffect, useState } from "react"
import { Download, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { FormError } from "@/components/ui/form-error"
import { downloadProof, loadProofBlob } from "@/lib/expenses"
import type { Proof } from "@/lib/types"

interface Source {
  proofId: number
  url: string | null
  type: string
  error: string | null
}

/**
 * Prévisualisation d'une pièce justificative (§5.4).
 *
 * Le contrôleur doit pouvoir juger une facture sans quitter l'application ni
 * accumuler des fichiers sur son poste.
 */
export function ProofPreview({
  proof,
  onClose,
}: {
  proof: Proof | null
  onClose: () => void
}) {
  // L'état porte l'identifiant de la pièce chargée : « en cours » se déduit
  // de la comparaison, sans écrire dans l'état au début de l'effet.
  const [source, setSource] = useState<Source | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    if (!proof) return

    let revoked = false
    let objectUrl: string | null = null
    const proofId = proof.id

    loadProofBlob(proof)
      .then((loaded) => {
        // La fenêtre peut avoir été refermée pendant le chargement : publier
        // l'URL alors laisserait le contenu en mémoire sans jamais l'afficher.
        if (revoked) {
          URL.revokeObjectURL(loaded.url)
          return
        }
        objectUrl = loaded.url
        setSource({ proofId, url: loaded.url, type: loaded.type, error: null })
      })
      .catch((e: unknown) => {
        if (revoked) return
        setSource({
          proofId,
          url: null,
          type: "",
          error: e instanceof Error ? e.message : "Aperçu indisponible",
        })
      })

    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [proof])

  if (!proof) return null

  const current = source?.proofId === proof.id ? source : null
  const loading = current === null
  const isImage = current?.type.startsWith("image/")

  const handleDownload = async () => {
    setDownloading(true)
    setDownloadError(null)
    try {
      await downloadProof(proof)
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : "Téléchargement impossible")
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] w-full sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{proof.original_name}</DialogTitle>
          <DialogDescription>
            {proof.kind_display} · version {proof.version} ·{" "}
            <span className="font-mono">{proof.sha256.slice(0, 16)}…</span>
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-[24rem] overflow-auto rounded-lg border border-border/60 bg-muted/30">
          {loading && (
            <div className="flex h-96 items-center justify-center" aria-busy="true">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <span className="sr-only">Chargement de l'aperçu…</span>
            </div>
          )}
          {current?.error && <FormError className="m-4">{current.error}</FormError>}
          {current?.url &&
            (isImage ? (
              <img
                src={current.url}
                alt={proof.original_name}
                className="mx-auto max-h-[70vh] object-contain"
              />
            ) : (
              <iframe
                src={current.url}
                title={proof.original_name}
                className="h-[70vh] w-full border-0"
              />
            ))}
        </div>

        <div className="flex items-center justify-end gap-3">
          <FormError className="flex-1 py-2">{downloadError}</FormError>
          <Button variant="outline" size="sm" disabled={downloading} onClick={() => void handleDownload()}>
            {downloading ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-1 h-4 w-4" aria-hidden />
            )}
            Télécharger
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
