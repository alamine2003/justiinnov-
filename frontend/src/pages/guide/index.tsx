import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { AlertTriangle, PlayCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { useAuth } from "@/context/use-auth"
import { fichierDuGuide, guidesVisibles, langueDeGuide, type IdDeGuide, type LangueDeGuide } from "@/lib/guides"
import { useQuery } from "@/lib/use-query"
import { cn } from "@/lib/utils"

/** Les entités qu'un sous-titre peut porter (WebVTT, § 6.4) ; les autres restent telles quelles. */
const ENTITES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&nbsp;": "\u00a0",
  "&lrm;": "\u200e",
  "&rlm;": "\u200f",
}

/**
 * Le texte des répliques d'un fichier WebVTT, dans l'ordre : chaque
 * réplique est une étape du guide. Analyse minimale, suffisante pour les
 * fichiers que le script de tournage écrit et robuste à ceux qu'on
 * retoucherait à la main : en-tête obligatoire (sans lui, ce n'est pas un
 * sous-titre — le serveur de développement répond la page de l'application
 * à une adresse inconnue), blocs `NOTE`, `STYLE` et `REGION` ignorés,
 * identifiant facultatif, texte sur plusieurs lignes, balises retirées.
 */
function etapesDuWebVTT(contenu: string): string[] {
  const lignes = contenu.replace(/^\uFEFF/, "").split(/\r\n|\r|\n/)
  if (!/^WEBVTT(?:[ \t].*)?$/.test(lignes[0] ?? "")) return []

  const blocs: string[][] = []
  let bloc: string[] = []
  for (const ligne of lignes) {
    if (ligne.trim() === "") {
      if (bloc.length > 0) blocs.push(bloc)
      bloc = []
    } else {
      bloc.push(ligne)
    }
  }
  if (bloc.length > 0) blocs.push(bloc)

  const etapes: string[] = []
  // Le premier bloc est l'en-tête ; une réplique a son horodatage en
  // première ligne, ou en deuxième derrière son identifiant.
  for (const [rang, lignesDuBloc] of blocs.entries()) {
    const horodatage = lignesDuBloc.findIndex((ligne) => ligne.includes("-->"))
    if (rang === 0 || horodatage < 0 || horodatage > 1) continue
    const texte = lignesDuBloc
      .slice(horodatage + 1)
      .join(" ")
      .replace(/<[^>]*>/g, "")
      .replace(/&(?:amp|lt|gt|nbsp|lrm|rlm);/g, (entite) => ENTITES[entite])
      .replace(/[ \t]+/g, " ")
      .trim()
    if (texte) etapes.push(texte)
  }
  return etapes
}

/** Les étapes d'un guide, lues dans ses sous-titres ; un fichier absent n'en donne aucune. */
async function lireLesEtapes(adresse: string, signal: AbortSignal): Promise<string[]> {
  const reponse = await fetch(adresse, { signal })
  if (reponse.status === 404) return []
  if (!reponse.ok) throw new Error(`HTTP ${reponse.status}`)
  return etapesDuWebVTT(await reponse.text())
}

/**
 * Les étapes du guide ouvert, en texte : la vidéo est muette, et ce
 * qu'elle montre doit se relire et se chercher dans la page. La source est
 * le fichier de sous-titres de la langue — celui que lit le lecteur —, pour
 * que la page ne dise jamais autre chose que la vidéo.
 */
function EtapesDuGuide({ id, langue }: { id: IdDeGuide; langue: LangueDeGuide }) {
  const { t } = useTranslation()
  const adresse = fichierDuGuide(id, langue, "vtt")
  // Sans `keepPreviousData`, les étapes du guide précédent ne s'affichent
  // pas sous le titre du suivant pendant le chargement.
  const { data, loading, error } = useQuery(adresse, (signal) => lireLesEtapes(adresse, signal), {
    keepPreviousData: false,
  })

  if (loading) {
    return (
      <output className="block text-xs text-muted-foreground">{t("guides.etapes.chargement")}</output>
    )
  }
  if (error) {
    return (
      <p role="alert" className="text-xs text-muted-foreground">
        {t("guides.etapes.erreur")}
      </p>
    )
  }
  if (!data || data.length === 0) return null

  return (
    <section aria-labelledby="guide-etapes" className="space-y-2 border-t border-border/60 pt-3">
      <h3 id="guide-etapes" className="text-sm font-semibold">
        {t("guides.etapes.titre")}
      </h3>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
        {data.map((etape, rang) => (
          // Le rang est l'identité d'une étape : la liste ne se réordonne pas.
          <li key={rang}>{etape}</li>
        ))}
      </ol>
    </section>
  )
}

/**
 * La largeur maximale du lecteur : la hauteur disponible sous l'en-tête de
 * page, au format des vidéos (16/10), mais jamais moins de 52 rem, sous
 * quoi le texte filmé (14 px sur 1280) tomberait sous 9 px.
 */
const LARGEUR_DU_LECTEUR = "max-w-[max(52rem,calc((var(--hauteur-page)_-_7.5rem)*1.6))]"

/**
 * Le guide vidéo (décision 118) : un tutoriel par geste, filmé sur la pile
 * de démonstration (`scripts/tourner-guides.mts`), dans la langue de
 * l'interface. Chacun ne voit que les guides des capacités qu'il a ; le
 * guide ouvert vit dans l'adresse (`?video=`), pour qu'un lien y mène.
 */
export function GuidePage() {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const [params] = useSearchParams()
  const langue = langueDeGuide(i18n.resolvedLanguage)
  const guides = guidesVisibles(can)
  const choisi = guides.find((guide) => guide.id === params.get("video")) ?? guides[0]
  // La vidéo (ou son affiche) qui n'a pas pu se charger : un lecteur gris
  // et muet ne disait rien. L'état porte la clé du lecteur, il ne survit
  // donc pas à un changement de guide ou de langue.
  const [enErreur, setEnErreur] = useState<string | null>(null)
  const cle = choisi ? `${choisi.id}-${langue}` : ""

  /** L'adresse d'un guide : un vrai lien, qui s'ouvre aussi dans un onglet. */
  const lienVers = (id: IdDeGuide) => {
    const suivant = new URLSearchParams(params)
    suivant.set("video", id)
    return `?${suivant.toString()}`
  }

  return (
    <div className="space-y-6 court:space-y-3">
      <PageHeader title={t("guides.titre")} description={t("guides.description")} />

      {choisi ? (
        // Le sommaire passe sous le lecteur jusqu'à `2xl` : à droite dès
        // `xl`, il ramenait la vidéo (tournée en 1280×800) à 584 px à 1280 et
        // le texte filmé à 6 ou 7 px, illisible (DESIGN.md, « Guide vidéo »).
        <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_22rem]">
          <Card className="border-border/60 shadow-sm">
            <CardContent>
              {/* Le lecteur tient dans la fenêtre, contrôles compris : sa
                  largeur est bornée par la hauteur de page (`--hauteur-page`,
                  moins l'en-tête de page et la marge de la carte, 7,5 rem,
                  fois 16/10), sans descendre sous 52 rem — 832 px, le texte
                  filmé à 9,1 px (DESIGN.md, « Guide vidéo »). Pleine
                  largeur, il passait sous la ligne de flottaison à 1366×768.
                  Titre et étapes s'alignent sur lui. */}
              <div className={cn("mx-auto w-full space-y-3", LARGEUR_DU_LECTEUR)}>
                {/* Muettes, sous-titrées : la clé remonte le lecteur quand
                    le guide ou la langue changent, sans quoi il garderait
                    l'ancienne source. */}
                <video
                  key={cle}
                  onError={() => setEnErreur(cle)}
                  aria-labelledby="guide-titre"
                  aria-describedby="guide-description"
                  controls
                  muted
                  preload="metadata"
                  poster={fichierDuGuide(choisi.id, langue, "jpg")}
                  className="aspect-[16/10] w-full rounded-lg border border-border/60 bg-muted outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {/* L'erreur d'une source ne remonte pas à la vidéo : elle
                      s'écoute sur la source elle-même. */}
                  <source
                    src={fichierDuGuide(choisi.id, langue, "webm")}
                    type="video/webm"
                    onError={() => setEnErreur(cle)}
                  />
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
                {enErreur === cle && (
                  <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                    {t("guides.video_indisponible")}
                  </p>
                )}
                <div>
                  <h2 id="guide-titre" className="text-base font-semibold">
                    {t(`guides.liste.${choisi.id}.titre`)}
                  </h2>
                  <p id="guide-description" className="text-sm text-muted-foreground">
                    {t(`guides.liste.${choisi.id}.description`)}
                  </p>
                </div>
                <EtapesDuGuide id={choisi.id} langue={langue} />
              </div>
            </CardContent>
          </Card>

          <nav aria-label={t("guides.sommaire")}>
            {/* Sous le lecteur, les guides se rangent en colonnes ; à côté, en une seule. */}
            <ol className="grid gap-2 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-1">
              {guides.map((guide, rang) => {
                const actif = guide.id === choisi.id
                return (
                  <li key={guide.id}>
                    <Link
                      to={lienVers(guide.id)}
                      replace
                      aria-current={actif ? "page" : undefined}
                      aria-label={t("guides.numero", {
                        numero: rang + 1,
                        titre: t(`guides.liste.${guide.id}.titre`),
                      })}
                      aria-describedby={`guide-${guide.id}-description`}
                      className={cn(
                        "flex h-full w-full items-start gap-3 rounded-lg border p-2 text-left transition-colors outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50",
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
                          {t("guides.numero", {
                            numero: rang + 1,
                            titre: t(`guides.liste.${guide.id}.titre`),
                          })}
                        </span>
                        <span id={`guide-${guide.id}-description`} className="block text-xs text-muted-foreground">
                          {t(`guides.liste.${guide.id}.description`)}
                        </span>
                      </span>
                    </Link>
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
