/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** «1» sirve las pantallas con datos de ejemplo y sin backend. Ver `.env.example`. */
  readonly VITE_SIGREP_EJEMPLOS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
