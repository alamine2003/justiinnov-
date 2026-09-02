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
import { downloadProof, loadProofBlob } from "@/lib/expenses"
import type { Proof } from "@/lib/types"

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
  const [source, setSource] = useState<{ url: string; type: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!proof) {
      setSource(null)
      return
    }

    let revoked = false
    let objectUrl: string | null = null

    setLoading(true)
    setError(null)
    loadProofBlob(proof)
      .then((loaded) => {
        // La fenêtre peut avoir été refermée pendant le chargement : publier
        // l'URL alors laisserait le contenu en mémoire sans jamais l'afficher.
        if (revoked) {
          URL.revokeObjectURL(loaded.url)
          return
        }
        objectUrl = loaded.url
        setSource(loaded)
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Aperçu indisponible"),
      )
      .finally(() => setLoading(false))

    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [proof])

  if (!proof) return null

  const isImage = source?.type.startsWith("image/")

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
            <div className="flex h-96 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}
          {error && (
            <p className="p-6 text-sm text-destructive">{error}</p>
          )}
          {source && !loading && !error && (
            isImage ? (
              <img
                src={source.url}
                alt={proof.original_name}
                className="mx-auto max-h-[70vh] object-contain"
              />
            ) : (
              <iframe
                src={source.url}
                title={proof.original_name}
                className="h-[70vh] w-full border-0"
              />
            )
          )}
        </div>

        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => downloadProof(proof)}>
            <Download className="mr-1 h-4 w-4" />
            Télécharger
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
