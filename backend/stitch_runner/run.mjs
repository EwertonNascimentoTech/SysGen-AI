/**
 * Lê JSON no stdin: { "prompt": string, "projectId"?: string, "projectTitle"?: string }
 * Variável de ambiente: STITCH_API_KEY (obrigatória)
 * Escreve JSON no stdout: { ok, stitchProjectId?, screenId?, htmlUrl?, imageUrl?, error? }
 */
import { stitch } from "@google/stitch-sdk";

const chunks = [];
for await (const c of process.stdin) chunks.push(c);

let input;
try {
  input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
} catch {
  console.log(JSON.stringify({ ok: false, error: "JSON inválido no stdin" }));
  process.exit(1);
}

const { prompt, projectId, projectTitle } = input;
if (!prompt || !String(prompt).trim()) {
  console.log(JSON.stringify({ ok: false, error: "prompt é obrigatório" }));
  process.exit(1);
}

async function main() {
  let project;
  if (projectId && String(projectId).trim()) {
    project = stitch.project(String(projectId).trim());
  } else {
    project = await stitch.createProject(String(projectTitle || "SysGen prototype").trim());
  }
  const screen = await project.generate(String(prompt).trim(), "DESKTOP");
  const htmlUrl = await screen.getHtml();
  const imageUrl = await screen.getImage();
  console.log(
    JSON.stringify({
      ok: true,
      stitchProjectId: project.projectId,
      screenId: screen.screenId,
      htmlUrl,
      imageUrl,
    }),
  );
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
