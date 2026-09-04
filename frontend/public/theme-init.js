// Posé avant le premier rendu : React monte trop tard, et le fond clair
// apparaîtrait un instant à chaque chargement en thème sombre.
// Cette duplication est volontaire : un module ES serait chargé après
// le premier rendu et annulerait l'intérêt du script anti-flash.
//
// Le script vit dans un fichier et non dans index.html : la politique de
// sécurité de contenu servie par nginx (`script-src 'self'`) bloque tout
// script en ligne, et le thème sombre flashait en production sans que rien
// ne le dise — hormis la console, que les captures de la CI relèvent.
;(function () {
  try {
    var choix = localStorage.getItem("justi_theme") || "system"
    var sombre =
      choix === "dark" ||
      (choix === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches)
    if (sombre) {
      document.documentElement.classList.add("dark")
      document.documentElement.style.colorScheme = "dark"
    }
  } catch {
    // Un stockage indisponible replie la page sur le thème clair.
  }
})()
