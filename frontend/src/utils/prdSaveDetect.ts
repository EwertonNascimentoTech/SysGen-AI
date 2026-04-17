/** Alinhado a `looks_like_prd_document` no backend (fallback sem marcador ::PRD::). */
export function looksLikePrdMarkdown(content: string): boolean {
  const t = content.trim();
  if (t.length < 400 || !t.includes("##")) return false;
  const low = t.toLowerCase();
  const signals = [
    "requisitos",
    "critério",
    "aceite",
    "âmbito",
    "ambito",
    "fora de âmbito",
    "prd",
    "product requirements",
    "objetivo",
    "métrica",
    "stakeholder",
  ];
  return signals.filter((s) => low.includes(s)).length >= 2;
}
