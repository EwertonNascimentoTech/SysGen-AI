/** Injeta o viewer de navegação (public/stitch-export-viewer.js) no HTML do export. */
export function prepareStitchExportHtmlForViewer(html: string, projectId: number, currentRel: string): string {
  const base = import.meta.env.BASE_URL || "/";
  const viewerSrc = base.endsWith("/") ? `${base}stitch-export-viewer.js` : `${base}/stitch-export-viewer.js`;
  const cfg = `<script>window.__STITCH_P__=${JSON.stringify(projectId)};window.__STITCH_R__=${JSON.stringify(currentRel)};window.__STITCH_SCRIPT_SRC__=${JSON.stringify(viewerSrc)};<\/script><script src="${viewerSrc.replace(/"/g, "&quot;")}" defer><\/script>`;
  if (html.includes("</head>")) {
    return html.replace("</head>", `${cfg}</head>`);
  }
  return `${cfg}${html}`;
}
