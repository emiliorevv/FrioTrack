/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base de la API. En desarrollo, si falta, se usa http://127.0.0.1:8000/api.
   * En producción es obligatoria: sin ella no se abre el stream y se registra
   * un error en consola.
   */
  readonly VITE_API_URL?: string
  /** `1` muestra la pista de cuentas demo en builds que no son de desarrollo. */
  readonly VITE_MOSTRAR_DEMO?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
