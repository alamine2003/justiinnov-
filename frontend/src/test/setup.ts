import "@testing-library/jest-dom/vitest"
import i18n from "@/i18n"

// Les tests s'exécutent en français, la langue par défaut de l'interface :
// jsdom se présente en « en-US », et le détecteur suivrait le navigateur.
await i18n.changeLanguage("fr")
