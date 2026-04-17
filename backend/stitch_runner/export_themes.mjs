/**
 * Lê JSON no stdin: { "projectId": string } — ID Stitch (sem prefixo projects/).
 * Variável: STITCH_API_KEY
 * Escreve JSON no stdout: { ok, stitchProjectId?, project?, designSystems?, screens?, error? }
 * O backend grava só os ecrãs no MinIO; o título da página vem do get_screen.
 */
import { StitchToolClient } from "@google/stitch-sdk";

const chunks = [];
for await (const c of process.stdin) chunks.push(c);

let input;
try {
  input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
} catch {
  console.log(JSON.stringify({ ok: false, error: "JSON inválido no stdin" }));
  process.exit(1);
}

const projectId = String(input.projectId || "").trim();
if (!projectId) {
  console.log(JSON.stringify({ ok: false, error: "projectId é obrigatório" }));
  process.exit(1);
}

function screenIdFrom(item) {
  if (!item || typeof item !== "object") return "";
  let sid = item.screenId || item.id || "";
  if (!sid && item.name) {
    const parts = String(item.name).split("/screens/");
    if (parts.length === 2) sid = parts[1];
  }
  return String(sid || "").trim();
}

async function main() {
  const client = new StitchToolClient();
  try {
    const project = await client.callTool("get_project", {
      name: `projects/${projectId}`,
    });

    const listDs = await client.callTool("list_design_systems", { projectId });
    const designSystems = listDs?.designSystems ?? [];

    const listSc = await client.callTool("list_screens", { projectId });
    const screenList = listSc?.screens || [];

    const screens = [];
    for (const s of screenList) {
      const screenId = screenIdFrom(s);
      if (!screenId) continue;
      const raw = await client.callTool("get_screen", {
        name: `projects/${projectId}/screens/${screenId}`,
        projectId,
        screenId,
      });
      const pageTitle =
        raw?.title ||
        raw?.displayName ||
        raw?.pageTitle ||
        raw?.screenTitle ||
        screenId;
      screens.push({
        screenId,
        htmlUrl: raw?.htmlCode?.downloadUrl || "",
        imageUrl: raw?.screenshot?.downloadUrl || "",
        title: pageTitle,
        raw,
      });
    }

    console.log(
      JSON.stringify({
        ok: true,
        stitchProjectId: projectId,
        project,
        designSystems,
        screens,
      }),
    );
  } finally {
    await client.close();
  }
}

main().catch((e) => {
  console.log(
    JSON.stringify({
      ok: false,
      error: e && e.message ? e.message : String(e),
    }),
  );
  process.exit(1);
});
