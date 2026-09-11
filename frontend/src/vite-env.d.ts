/// <reference types="vite/client" />

/**
 * Version livrée, figée à la construction (`define` dans `vite.config.ts`) :
 * celle du tag `v*` déployé, sinon celle de `package.json`.
 */
declare const __APP_VERSION__: string
