import { useSearchParams } from "react-router-dom"
import { PlayCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { useAuth } from "@/context/use-auth"
import { fichierDuGuide, guidesVisibles, langueDeGuide } from "@/lib/guides"
import { cn } from "@/lib/utils"

/**
 * Le guide vidéo (décision 118) : un tutoriel par geste, filmé sur la pile
 * de démonstration (`scripts/tourner-guides.mts`), dans la langue de
 * l'interface. Chacun ne voit que les guides des capacités qu'il a ; le
 * guide ouvert vit dans l'adresse (`?video=`), pour qu'un lien y mène.
 */
export function GuidePage() {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const [params, setParams] = useSearchParams()
  const langue = langueDeGuide(i18n.resolvedLanguage)
  const guides = guidesVisibles(can)
  const choisi = guides.find((guide) => guide.id === params.get("video")) ?? guides[0]

  const choisir = (id: string) =>
    setParams(
      (courant) => {
        const suivant = new URLSearchParams(courant)
        suivant.set("video", id)
        return suivant
      },
      { replace: true },
    )

  return (
    <div className="space-y-6">
      <PageHeader title={t("guides.titre")} description={t("guides.description")} />

      {choisi ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="space-y-3">
              {/* Muettes, sous-titrées : la clé remonte le lecteur quand
                  le guide ou la langue changent, sans quoi il garderait
                  l'ancienne source. */}
              <video
                key={`${choisi.id}-${langue}`}
                aria-labelledby="guide-titre"
                aria-describedby="guide-description"
                controls
                muted
                preload="metadata"
                poster={fichierDuGuide(choisi.id, langue, "jpg")}
                className="aspect-[16/10] w-full rounded-lg border border-border/60 bg-muted"
              >
                <source src={fichierDuGuide(choisi.id, langue, "webm")} type="video/webm" />
                <track
                  kind="captions"
                  src={fichierDuGuide(choisi.id, langue, "vtt")}
                  srcLang={langue}
                  label={t("guides.sous_titres")}
                  default
                />
                {/* Ce texte ne s'affiche que si le navigateur ne lit pas la vidéo. */}
                {t("guides.illisible")}
              </video>
              <div>
                <h2 id="guide-titre" className="text-base font-semibold">
                  {t(`guides.liste.${choisi.id}.titre`)}
                </h2>
                <p id="guide-description" className="text-sm text-muted-foreground">
                  {t(`guides.liste.${choisi.id}.description`)}
                </p>
              </div>
            </CardContent>
          </Card>

          <nav aria-label={t("guides.sommaire")}>
            <ol className="space-y-2">
              {guides.map((guide, rang) => {
                const actif = guide.id === choisi.id
                return (
                  <li key={guide.id}>
                    <button
                      type="button"
                      aria-current={actif ? "true" : undefined}
                      aria-label={`${rang + 1}. ${t(`guides.liste.${guide.id}.titre`)}`}
                      aria-describedby={`guide-${guide.id}-description`}
                      onClick={() => choisir(guide.id)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-lg border p-2 text-left transition-colors outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50",
                        actif ? "border-ring bg-accent" : "border-border/60 bg-card",
                      )}
                    >
                      <img
                        src={fichierDuGuide(guide.id, langue, "jpg")}
                        alt=""
                        loading="lazy"
                        className="aspect-[16/10] w-24 shrink-0 rounded-md border border-border/60 bg-muted object-cover"
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">
                          {rang + 1}. {t(`guides.liste.${guide.id}.titre`)}
                        </span>
                        <span id={`guide-${guide.id}-description`} className="block text-xs text-muted-foreground">
                          {t(`guides.liste.${guide.id}.description`)}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          </nav>
        </div>
      ) : (
        <Card className="border-border/60 shadow-sm">
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
            <PlayCircle className="h-6 w-6 text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium">{t("guides.aucun.titre")}</p>
            <p className="text-sm text-muted-foreground">{t("guides.aucun.aide")}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
