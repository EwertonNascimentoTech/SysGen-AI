import { marked } from "marked";

/**
 * Converte Markdown da resposta do assistente PRD em HTML seguro para `v-html`
 * (conteúdo gerado pelo backend; mesmo padrão que a Wiki com `marked`).
 */
export function renderPrdAssistantMarkdown(markdown: string): string {
  const s = (markdown ?? "").trim();
  if (!s) return "";
  return marked.parse(s, { async: false, breaks: true, gfm: true }) as string;
}
