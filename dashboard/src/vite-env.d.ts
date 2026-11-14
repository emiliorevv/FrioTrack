/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base de la API; la demo cae a http://127.0.0.1:8000/api si no está definida. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
