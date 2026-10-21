import { nextTick } from 'vue'

/**
 * Consultas sobre el DOM para tests de componentes/páginas: buscan como lo
 * haría el usuario, por texto visible. Solo tests; Nuxt no auto-importa `app/testing/`.
 */

/** Espera a que se asienten promesas y renders encadenados. */
export async function flushAll(rounds = 3) {
  for (let round = 0; round < rounds; round++) {
    for (let i = 0; i < 5; i++) await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
}

/** Textos de los botones visibles de un contenedor. */
export function buttonTexts(root: ParentNode): string[] {
  return [...root.querySelectorAll('button')].map((el) => el.textContent?.trim() ?? '')
}

/** Botón con ese texto visible (el primero), o `null`. */
export function findButton(root: ParentNode, text: string): HTMLButtonElement | null {
  return [...root.querySelectorAll('button')].find((el) => el.textContent?.trim() === text) ?? null
}
