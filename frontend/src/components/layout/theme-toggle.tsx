import { Monitor, Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTheme } from "@/context/use-theme"
import { THEME_LABELS, THEMES, type Theme } from "@/lib/theme"

const ICONES = { light: Sun, dark: Moon, system: Monitor }

export function ThemeToggle() {
  const { theme, resolved, setTheme } = useTheme()
  const Icone = resolved === "dark" ? Moon : Sun

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Thème de l'interface">
            <Icone className="h-4 w-4" />
          </Button>
        }
      />
      <DropdownMenuContent align="end">
        {/* Un groupe radio : le choix courant est annoncé comme coché, pas
            seulement souligné par une couleur. */}
        <DropdownMenuRadioGroup
          value={theme}
          onValueChange={(valeur) => setTheme(valeur as Theme)}
        >
          {THEMES.map((valeur) => {
            const IconeOption = ICONES[valeur]
            // Un choix de thème est une action ponctuelle : le menu se
            // referme dès qu'il est fait, sans laisser l'utilisateur devant
            // une liste dont il n'a plus besoin.
            return (
              <DropdownMenuRadioItem key={valeur} value={valeur} closeOnClick>
                <IconeOption className="h-4 w-4" aria-hidden />
                {THEME_LABELS[valeur]}
              </DropdownMenuRadioItem>
            )
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
