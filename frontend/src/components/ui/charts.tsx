/**
 * Primitives graphiques : jauges, courbe mensuelle et barres d'enveloppe.
 *
 * Elles ne connaissent que des nombres déjà calculés par le serveur. Ce
 * qu'elles calculent, ce sont des longueurs — largeur de barre, longueur
 * d'arc, coordonnée d'un point —, jamais un solde, un écart ni un taux :
 * voir « Rien ne se calcule dans l'interface » dans DESIGN.md.
 *
 * Toutes prennent leurs teintes des jetons de la marque (`marque`,
 * `banniere`, `destructive`, `statut-attente`) : aucune couleur en dur.
 */
import { monthShortName } from "@/lib/months"
import { cn, formatCompactAmount, ratio } from "@/lib/utils"

/** Longueur d'un cercle de rayon `r`, pour un `stroke-dasharray`. */
const perimetre = (r: number) => 2 * Math.PI * r

/** Pourcentage CSS d'une part de `whole`, borné à la largeur disponible. */
const pct = (part: number, whole: number) => `${ratio(part, whole) * 100}%`

// ---------------------------------------------------------------------------
// Jauges
// ---------------------------------------------------------------------------

interface JaugeProps {
  /** Taux décimal du serveur (« 0.8250 »), ou `null` quand il n'y en a pas. */
  rate: string | null | undefined
  /** Taux déjà formaté, écrit au centre de l'anneau. */
  label: string
  /** Dépassement : l'anneau passe en teinte destructive. */
  over?: boolean
  /** Proche du plafond : l'anneau passe en teinte d'attente. */
  near?: boolean
  /** Ce que la jauge montre, pour les lecteurs d'écran. */
  title: string
  className?: string
}

/**
 * Anneau simple avec son taux au centre. Un dépassement remplit l'anneau et
 * le fait virer au corail : la jauge ne dépasse pas son propre cadre, c'est
 * la teinte qui le dit.
 */
export function Jauge({ rate, label, over, near, title, className }: JaugeProps) {
  const valeur = ratio(Number(rate ?? 0), 1)
  const r = 30
  const teinte = over ? "stroke-destructive" : near ? "stroke-statut-attente" : "stroke-marque"
  return (
    <div className={cn("relative h-[74px] w-[74px] shrink-0", className)}>
      <span className="sr-only">{title}</span>
      <svg viewBox="0 0 74 74" className="h-full w-full" aria-hidden>
        <circle cx="37" cy="37" r={r} fill="none" strokeWidth="8" className="stroke-muted" />
        <circle
          cx="37"
          cy="37"
          r={r}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${valeur * perimetre(r)} ${perimetre(r)}`}
          transform="rotate(-90 37 37)"
          className={teinte}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-semibold tracking-tight">
        {label}
      </span>
    </div>
  )
}

interface JaugeDoubleProps {
  /** Anneau extérieur : le taux d'exécution. */
  executionRate: string | null | undefined
  /** Anneau intérieur, plus fin : le taux de justification. */
  justificationRate: string | null | undefined
  /** Taux d'exécution formaté, au centre. */
  label: string
  /** Légende sous le taux, au centre. */
  caption: string
  title: string
}

/**
 * Deux anneaux concentriques — exécution à l'extérieur, justification à
 * l'intérieur. Dessinée pour le bandeau marine du Pilotage : ses teintes
 * sont celles du bandeau, elle ne va pas sur une carte claire.
 */
export function JaugeDouble({
  executionRate,
  justificationRate,
  label,
  caption,
  title,
}: JaugeDoubleProps) {
  const execution = ratio(Number(executionRate ?? 0), 1)
  const justification = ratio(Number(justificationRate ?? 0), 1)
  return (
    <div className="relative h-[132px] w-[132px] shrink-0">
      <span className="sr-only">{title}</span>
      <svg viewBox="0 0 132 132" className="h-full w-full" aria-hidden>
        <circle
          cx="66"
          cy="66"
          r="54"
          fill="none"
          strokeWidth="13"
          className="stroke-banniere-bordure"
        />
        <circle
          cx="66"
          cy="66"
          r="54"
          fill="none"
          strokeWidth="13"
          strokeLinecap="round"
          strokeDasharray={`${execution * perimetre(54)} ${perimetre(54)}`}
          transform="rotate(-90 66 66)"
          className="stroke-marque"
        />
        <circle
          cx="66"
          cy="66"
          r="43"
          fill="none"
          strokeWidth="5"
          className="stroke-banniere-bordure"
        />
        <circle
          cx="66"
          cy="66"
          r="43"
          fill="none"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${justification * perimetre(43)} ${perimetre(43)}`}
          transform="rotate(-90 66 66)"
          className="stroke-banniere-accent"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold tracking-tight text-banniere-foreground">
          {label}
        </span>
        <span className="mt-0.5 text-[0.625rem] text-banniere-muted">{caption}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Courbe mensuelle
// ---------------------------------------------------------------------------

/** Un mois de l'exercice : ce qui a été dépensé, ce qui est justifié. */
export interface PointMensuel {
  /** 1 à 12. */
  month: number
  amount: number
  justified: number
}

/** Cadre du dessin, en unités de `viewBox`. */
const CADRE = { largeur: 1000, hauteur: 200, gauche: 42, droite: 8, haut: 12, bas: 34 }

/**
 * Graduation « ronde » au-dessus du plus grand point : 1, 2 ou 5 fois une
 * puissance de dix, pour que les quatre repères tombent juste.
 */
function plafond(max: number): number {
  if (max <= 0) return 1
  const puissance = 10 ** Math.floor(Math.log10(max))
  const pas = [1, 2, 2.5, 5, 10].find((p) => max <= p * puissance) ?? 10
  return pas * puissance
}

interface CourbeMensuelleProps {
  /** Les douze mois de l'exercice, dans l'ordre ; un mois sans dépense vaut zéro. */
  points: PointMensuel[]
  title: string
}

/**
 * Dépensé en aire pleine, justifié en pointillé : l'écart entre les deux
 * traits est ce qui manque de preuve. Les valeurs sont celles du mois, pas
 * un cumul — c'est ce que le serveur renvoie.
 */
export function CourbeMensuelle({ points, title }: CourbeMensuelleProps) {
  const { largeur, hauteur, gauche, droite, haut, bas } = CADRE
  const base = hauteur - bas
  const utile = largeur - gauche - droite
  const max = plafond(Math.max(...points.map((p) => Math.max(p.amount, p.justified)), 0))
  const x = (index: number) =>
    points.length > 1 ? gauche + (index * utile) / (points.length - 1) : gauche + utile / 2
  const y = (valeur: number) => base - ratio(valeur, max) * (base - haut)
  const ligne = (cle: "amount" | "justified") =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(p[cle]).toFixed(1)}`).join(" ")
  const graduations = [0, 0.25, 0.5, 0.75, 1]

  return (
    <div>
      <span className="sr-only">{title}</span>
      {/* Pas de `preserveAspectRatio="none"` : il étirerait les graduations
          et les noms de mois avec le dessin. */}
      <svg viewBox={`0 0 ${largeur} ${hauteur}`} className="block h-auto w-full" aria-hidden>
      {graduations.map((part) => {
        const ligneY = base - part * (base - haut)
        return (
          <g key={part}>
            <line
              x1={gauche}
              y1={ligneY}
              x2={largeur - droite}
              y2={ligneY}
              strokeWidth="1"
              className={part === 0 ? "stroke-border" : "stroke-border/50"}
            />
            <text
              x={gauche - 8}
              y={ligneY + 3}
              textAnchor="end"
              className="fill-muted-foreground text-[0.5625rem]"
            >
              {formatCompactAmount(part * max)}
            </text>
          </g>
        )
      })}

      <path
        d={`${ligne("amount")} L${x(points.length - 1).toFixed(1)} ${base} L${gauche} ${base} Z`}
        className="fill-marque"
        fillOpacity={0.13}
      />
      <path
        d={ligne("amount")}
        fill="none"
        strokeWidth="2.2"
        strokeLinejoin="round"
        strokeLinecap="round"
        className="stroke-marque"
      />
      <path
        d={ligne("justified")}
        fill="none"
        strokeWidth="1.8"
        strokeDasharray="5 4"
        strokeLinejoin="round"
        strokeLinecap="round"
        className="stroke-marque-fort"
      />

      {points.map((point, index) => (
        <text
          key={point.month}
          x={x(index)}
          y={hauteur - 12}
          textAnchor="middle"
          className="fill-muted-foreground text-[0.5938rem]"
        >
          {monthShortName(point.month)}
        </text>
      ))}
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Barres d'enveloppe
// ---------------------------------------------------------------------------

interface BarreEnveloppeProps {
  consumed: number
  engaged: number
  allocated: number
  /**
   * Échelle commune à toutes les barres d'une liste : la plus grande
   * enveloppe. Deux pays ne se comparent qu'à échelle égale.
   */
  scale: number
  title: string
}

/**
 * Une enveloppe de pays en barre horizontale : consommé, engagé, et un trait
 * vertical sur le montant attribué. Ce qui dépasse le trait part en corail,
 * pour que le dépassement se voie sans lire le chiffre.
 */
export function BarreEnveloppe({
  consumed,
  engaged,
  allocated,
  scale,
  title,
}: BarreEnveloppeProps) {
  const dansEnveloppe = Math.min(consumed, allocated)
  // L'engagé se pose après le consommé, sans franchir le montant attribué :
  // au-delà, c'est le dépassement qui occupe la barre.
  const engage = Math.max(Math.min(engaged, allocated - dansEnveloppe), 0)
  // Le dépassement se mesure sur consommé **et** engagé — la définition du
  // serveur (`remaining = allocated - (consumed + engaged)`). Mesuré sur le
  // seul consommé, la barre s'arrêtait au plafond sans segment corail alors
  // que le taux d'exécution affichait 120 % : le dessin démentait le chiffre.
  const depassement = Math.max(consumed + engaged - allocated, 0)
  return (
    <div className="relative h-[22px]">
      <span className="sr-only">{title}</span>
      <div
        className="absolute inset-y-0 left-0 rounded bg-muted"
        style={{ width: pct(allocated, scale) }}
      />
      <div
        className="absolute inset-y-0 left-0 rounded-l bg-marque"
        style={{ width: pct(dansEnveloppe, scale) }}
      />
      <div
        className="absolute inset-y-0 bg-marque-clair"
        style={{ left: pct(dansEnveloppe, scale), width: pct(engage, scale) }}
      />
      {depassement > 0 && (
        <div
          className="absolute inset-y-0 rounded-r bg-destructive"
          style={{
            left: pct(allocated, scale),
            // Borné à ce qui reste de l'échelle : la barre ne déborde jamais
            // de son cadre, quelle que soit l'échelle qu'on lui donne.
            width: pct(Math.min(depassement, scale - allocated), scale),
          }}
        />
      )}
      <div
        className="absolute -top-1 h-[30px] w-0.5 bg-foreground"
        style={{ left: pct(allocated, scale) }}
      />
    </div>
  )
}

interface RailEnveloppeProps {
  consumed: number
  engaged: number
  justified: number
  allocated: number
  /** Seuils d'alerte de la configuration, en pourcentage (80, 90, 100). */
  thresholds: number[]
  /** Libellés des seuils, dans le même ordre. */
  thresholdLabels: string[]
  title: string
}

/**
 * L'enveloppe d'un pays sur toute la largeur, avec ses seuils d'alerte
 * gradués dessus et le montant justifié en pointillé. À la différence de
 * `BarreEnveloppe`, l'échelle est l'enveloppe elle-même : on lit un
 * remplissage, pas une comparaison.
 */
export function RailEnveloppe({
  consumed,
  engaged,
  justified,
  allocated,
  thresholds,
  thresholdLabels,
  title,
}: RailEnveloppeProps) {
  const dansEnveloppe = Math.min(consumed, allocated)
  const engage = Math.max(Math.min(engaged, allocated - dansEnveloppe), 0)
  // Comme `BarreEnveloppe` : consommé et engagé, la définition du serveur.
  const depassement = Math.max(consumed + engaged - allocated, 0)
  return (
    <div>
      <div className="relative">
        <span className="sr-only">{title}</span>
        <div className="relative h-9 overflow-hidden rounded-md bg-muted">
          <div
            className="absolute inset-y-0 left-0 bg-marque"
            style={{ width: pct(dansEnveloppe, allocated) }}
          />
          <div
            className="absolute inset-y-0 bg-marque-clair"
            style={{ left: pct(dansEnveloppe, allocated), width: pct(engage, allocated) }}
          />
          {depassement > 0 && (
            <div className="absolute inset-y-0 right-0 w-1.5 bg-destructive" />
          )}
          <div
            className="absolute inset-y-0 left-0 border-r-2 border-dashed border-marque-fort/60"
            style={{ width: pct(justified, allocated) }}
          />
        </div>
        {/* Le plafond est le bord de l'enveloppe, pas un simple avertissement :
            il se gradue en corail, les seuils intermédiaires en ambre. */}
        {thresholds.map((seuil) => (
          <div
            key={seuil}
            className={cn(
              "absolute -top-1.5 -bottom-1.5 w-0.5",
              seuil >= 100
                ? "-translate-x-full bg-destructive"
                : "-translate-x-1/2 bg-statut-attente",
            )}
            style={{ left: `${Math.min(seuil, 100)}%` }}
          />
        ))}
      </div>
      <div className="relative mt-1.5 h-4">
        {thresholds.map((seuil, index) => (
          <span
            key={seuil}
            className={cn(
              "absolute whitespace-nowrap text-[0.5938rem] font-medium",
              seuil >= 100 ? "text-destructive" : "text-muted-foreground",
            )}
            style={{
              left: `${Math.min(seuil, 100)}%`,
              transform: seuil >= 100 ? "translateX(-100%)" : "translateX(-50%)",
            }}
          >
            {thresholdLabels[index]}
          </span>
        ))}
      </div>
    </div>
  )
}

interface BarreEcartProps {
  amount: number
  justified: number
  title: string
  className?: string
}

/**
 * Une ligne de dépense en barre : la part justifiée en azur, l'écart en
 * corail. Une ligne pas encore soumise n'a rien à montrer — la barre reste
 * vide plutôt que de suggérer un écart.
 */
export function BarreEcart({ amount, justified, title, className }: BarreEcartProps) {
  const ecart = Math.max(amount - justified, 0)
  return (
    <div
      className={cn("relative flex h-2 flex-1 overflow-hidden rounded-full bg-muted", className)}
    >
      <span className="sr-only">{title}</span>
      <div className="bg-marque" style={{ width: pct(justified, amount) }} />
      <div className="bg-destructive" style={{ width: pct(ecart, amount) }} />
    </div>
  )
}

interface LegendeProps {
  /** Une pastille et son libellé ; `dashed` pour un repère en pointillé. */
  items: { tone: string; label: string; dashed?: boolean }[]
  className?: string
}

/** Légende d'un graphique : pastille carrée, libellé, le tout sur une ligne. */
export function Legende({ items, className }: LegendeProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5", className)}>
      {items.map((item) => (
        <span
          key={item.label}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <span
            aria-hidden
            className={cn(
              "inline-block",
              item.dashed ? "h-0 w-2.5 border-t-2 border-dashed" : "h-2.5 w-2.5 rounded-[2px]",
              item.tone,
            )}
          />
          {item.label}
        </span>
      ))}
    </div>
  )
}
