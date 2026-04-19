<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { api, apiBlob, apiText } from "@/api/client";
import { prepareStitchExportHtmlForViewer } from "@/utils/stitchExportHtml";
import PrdChatPanel from "@/components/PrdChatPanel.vue";
import PrdVersionsPanel from "@/components/PrdVersionsPanel.vue";
import PrototipoVersionsPanel from "@/components/PrototipoVersionsPanel.vue";
import ProjectTaskBoard from "@/components/ProjectTaskBoard.vue";
import PlanejamentoRoadmapView from "@/components/PlanejamentoRoadmapView.vue";
import { useAuthStore } from "@/stores/auth";

/** Google Stitch — o URL pode ser substituído em build (VITE_STITCH_URL). */
const STITCH_APP_URL =
  (import.meta.env.VITE_STITCH_URL as string | undefined)?.trim() || "https://stitch.withgoogle.com/";

type Project = {
  id: number;
  name: string;
  product_owner: string;
  directory_id: number;
  directory_name: string | null;
  methodology: string;
  current_column_id: number;
  current_column_title: string | null;
  template_id: number;
  github_repo_url: string | null;
  github_tag: string | null;
  /** ISO; última gravação do PRD (MD) a partir do chat. */
  prd_markdown_saved_at?: string | null;
  /** Última versão registada em `project_prd_versions`. */
  prd_current_version?: number | null;
  prototipo_prompt_saved_at?: string | null;
  prototipo_current_version?: number | null;
  /** Última gravação do JSON de planejamento técnico (agente Azure). */
  planejamento_json_saved_at?: string | null;
  planejamento_json_approved_at?: string | null;
  planned_start: string;
  planned_end: string;
  ended_at: string | null;
};

type DetailTab =
  | "resumo"
  | "kanban"
  | "github"
  | "wiki"
  | "anexos"
  | "cursor"
  | "auditoria"
  | "prd"
  | "prototipo"
  | "planejamento";

type MainTab =
  | "resumo"
  | "kanban"
  | "anexos"
  | "auditoria"
  | "prd"
  | "prototipo"
  | "planejamento"
  | "configuracoes";
type ConfigTab = "github" | "wiki" | "cursor";

type Col = { id: number; title: string; position: number; visible_detail_tabs?: string[] };
type Tpl = { id: number; columns: Col[] };
type Dir = { id: number; name: string };

type WikiResp = {
  documents?: { title: string; markdown: string; path: string }[];
  detail?: string;
  status?: string | null;
  error_message?: string | null;
};

type AuditItem = {
  id: number;
  created_at: string;
  actor_email: string;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  detail: string | null;
};

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const project = ref<Project | null>(null);
const templateCols = ref<Col[]>([]);
const tags = ref<string[]>([]);
const wiki = ref<WikiResp | null>(null);
const auditFeed = ref<AuditItem[]>([]);
const repoUrl = ref("");
const customRef = ref("");
const msg = ref("");
const err = ref("");
const attachType = ref("evidencia");
const fileEl = ref<HTMLInputElement | null>(null);
const activeTab = ref<DetailTab>("resumo");
/** OAuth GitHub configurado no servidor (client id/secret). */
const ghOAuthConfigured = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;
const prdVersionsPanelRef = ref<{ reload: () => void | Promise<void> } | null>(null);
const prototipoVersionsPanelRef = ref<{ reload: () => void | Promise<void> } | null>(null);
const projectTaskBoardRef = ref<{ reload: () => void | Promise<void> } | null>(null);
const prototipoGenerating = ref(false);
const prototipoPrompt = ref("");
const prototipoPromptErr = ref("");
const prototipoPromptMsg = ref("");
const prototipoPromptVersion = ref<number | null>(null);
const prototipoPrdVersion = ref<number | null>(null);
const planejamentoAgentLoading = ref(false);
const planejamentoAgentErr = ref("");
const planejamentoAgentWarnings = ref<string[]>([]);
const planejamentoAgentOutput = ref("");
/** Raiz JSON parseada (array ou object); null se a resposta não for JSON estruturado. */
const planejamentoAgentParsed = ref<unknown>(null);
/** Caminho JSON (`JSON.stringify` de `(string|number)[]`) do nó seleccionado na árvore. */
const planejamentoSelectedPathKey = ref<string | null>(null);
/** Nós com filhos expandidos na árvore de planejamento (chave = `planejamentoPathKey`). */
const planejamentoExpanded = ref<Record<string, boolean>>({});
const planejamentoApprovalLoading = ref(false);
const planejamentoApprovalMsg = ref("");
/** Stack + ambiente devolvidos por GET /planejamento (campo `context`). */
type PlanejamentoContext = {
  stack_documentada: string;
  methodology: string;
  github_repo_url: string | null;
  github_tag: string | null;
  s3_configured: boolean;
  github_oauth_configured: boolean;
  stitch_api_configured: boolean;
  azure_planejador_ready: boolean;
};
const planejamentoContext = ref<PlanejamentoContext | null>(null);
/** API MCP Google Stitch (backend + STITCH_API_KEY) — alternativa ao site web. */
const stitchApiReady = ref(false);
const stitchApiDetail = ref("");
const stitchApiGenerating = ref(false);
const stitchApproveExporting = ref(false);
/** Ficheiros relativos listados no MinIO (último export aprovado) — usado pelas galerias Entregas. */
const stitchMinioFiles = ref<string[]>([]);
/** Metadados por pasta (`meta.json` no MinIO): ordem do export e título legível. */
const stitchMinioFolderMeta = ref<Record<string, { exportOrder?: number; title?: string; htmlUrl?: string }>>({});
const stitchApiResult = ref<{
  html_url: string;
  image_url: string;
  stitch_project_id: string;
  screen_id: string;
  approved_at?: string | null;
  approved_by_email?: string | null;
  export_storage_prefix?: string | null;
} | null>(null);
const showDeleteModal = ref(false);
const deleting = ref(false);
const directories = ref<Dir[]>([]);
const editingProcess = ref(false);
const savingProcess = ref(false);
const editDraft = ref({
  name: "",
  product_owner: "",
  directory_id: 0,
  methodology: "prd" as "prd" | "base44",
  planned_start: "",
  planned_end: "",
  ended_at: "",
});

const canMove = computed(() => auth.hasRole("admin", "coordenador"));
const canSeeAudit = computed(() => auth.hasRole("admin", "coordenador"));
const canEditPrototipoPrompt = computed(() => auth.hasRole("admin", "coordenador", "po"));

type PlanejPath = (string | number)[];

type PlanejTreeRow = {
  pathKey: string;
  path: PlanejPath;
  label: string;
  preview: string;
  depth: number;
  hasChildren: boolean;
};

function summarizePlanejamentoValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v.length > 100 ? `${v.slice(0, 100)}…` : v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `Array (${v.length} itens)`;
  if (typeof v === "object") {
    const keys = Object.keys(v as Record<string, unknown>);
    if (keys.length === 0) return "Object (vazio)";
    const head = keys.slice(0, 4).join(", ");
    return keys.length > 4 ? `{ ${head}, … }` : `{ ${head} }`;
  }
  return String(v);
}

function planejamentoPathKey(path: PlanejPath): string {
  return JSON.stringify(path);
}

function getValueAtPlanejPath(root: unknown, path: PlanejPath): unknown {
  let cur: unknown = root;
  for (const seg of path) {
    if (cur === null || cur === undefined) return undefined;
    if (typeof seg === "number" && Array.isArray(cur)) {
      cur = cur[seg];
    } else if (typeof seg === "string" && typeof cur === "object" && !Array.isArray(cur)) {
      cur = (cur as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return cur;
}

function initPlanejamentoExpanded(root: unknown): Record<string, boolean> {
  const ex: Record<string, boolean> = {};
  if (root === null || typeof root !== "object") return ex;
  if (Array.isArray(root)) {
    root.forEach((item, i) => {
      if (item !== null && typeof item === "object") {
        ex[planejamentoPathKey([i])] = true;
      }
    });
  } else {
    for (const k of Object.keys(root as Record<string, unknown>)) {
      const child = (root as Record<string, unknown>)[k];
      if (child !== null && typeof child === "object") {
        ex[planejamentoPathKey([k])] = true;
      }
    }
  }
  return ex;
}

function appendPlanejChildren(
  value: unknown,
  basePath: PlanejPath,
  depth: number,
  expanded: Record<string, boolean>,
  out: PlanejTreeRow[],
) {
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item, i) => {
      const path = [...basePath, i];
      const pathKey = planejamentoPathKey(path);
      const hasChildren =
        item !== null &&
        typeof item === "object" &&
        (Array.isArray(item) ? item.length > 0 : Object.keys(item as object).length > 0);
      out.push({
        pathKey,
        path,
        label: `[${i}]`,
        preview: summarizePlanejamentoValue(item),
        depth,
        hasChildren,
      });
      if (hasChildren && expanded[pathKey]) {
        appendPlanejChildren(item, path, depth + 1, expanded, out);
      }
    });
  } else {
    const keys = Object.keys(value as Record<string, unknown>).sort((a, b) => a.localeCompare(b, "pt"));
    for (const k of keys) {
      const path = [...basePath, k];
      const pathKey = planejamentoPathKey(path);
      const child = (value as Record<string, unknown>)[k];
      const hasChildren =
        child !== null &&
        typeof child === "object" &&
        (Array.isArray(child) ? child.length > 0 : Object.keys(child as object).length > 0);
      out.push({
        pathKey,
        path,
        label: k,
        preview: summarizePlanejamentoValue(child),
        depth,
        hasChildren,
      });
      if (hasChildren && expanded[pathKey]) {
        appendPlanejChildren(child, path, depth + 1, expanded, out);
      }
    }
  }
}

const planejamentoTreeRows = computed((): PlanejTreeRow[] => {
  const p = planejamentoAgentParsed.value;
  if (p === null || p === undefined) return [];
  if (typeof p !== "object" || p === null) {
    return [
      {
        pathKey: planejamentoPathKey([]),
        path: [],
        label: "Valor",
        preview: summarizePlanejamentoValue(p),
        depth: 0,
        hasChildren: false,
      },
    ];
  }
  const rows: PlanejTreeRow[] = [];
  appendPlanejChildren(p, [], 0, planejamentoExpanded.value, rows);
  return rows;
});

const planejamentoSelectedDetailJson = computed(() => {
  const p = planejamentoAgentParsed.value;
  const key = planejamentoSelectedPathKey.value;
  if (p === null || p === undefined || key === null) return "";
  try {
    const path = JSON.parse(key) as PlanejPath;
    const v = getValueAtPlanejPath(p, path);
    return JSON.stringify(v, null, 2);
  } catch {
    return "";
  }
});

const planejamentoIsEmptyStructured = computed(() => {
  const p = planejamentoAgentParsed.value;
  if (p === null || p === undefined) return false;
  if (Array.isArray(p)) return p.length === 0;
  if (typeof p === "object") return Object.keys(p as Record<string, unknown>).length === 0;
  return false;
});

function togglePlanejamentoExpand(pathKey: string, ev: MouseEvent) {
  ev.stopPropagation();
  planejamentoExpanded.value = { ...planejamentoExpanded.value, [pathKey]: !planejamentoExpanded.value[pathKey] };
}

function selectPlanejamentoPathKey(pathKey: string) {
  planejamentoSelectedPathKey.value = pathKey;
}

function clearPlanejamentoSelection() {
  planejamentoSelectedPathKey.value = null;
}

watch(planejamentoTreeRows, (rows) => {
  const sel = planejamentoSelectedPathKey.value;
  if (sel === null) return;
  if (!rows.some((r) => r.pathKey === sel)) {
    planejamentoSelectedPathKey.value = null;
  }
});

function stitchMinioFileSortRank(name: string): number {
  const low = name.toLowerCase();
  if (/^ecra\.(html|svg)$/.test(low)) return 0;
  if (low.startsWith("preview.")) return 1;
  if (low === "meta.json") return 2;
  if (low === "get_screen.json") return 3;
  return 4;
}

function sortStitchMinioFiles(files: string[]): string[] {
  return [...files].sort((x, y) => {
    const r = stitchMinioFileSortRank(x) - stitchMinioFileSortRank(y);
    if (r !== 0) return r;
    return x.localeCompare(y, "pt");
  });
}

/** Agrupa caminhos por primeira pasta; ordena ecrãs por `exportOrder` em `meta.json` quando existir. */
const stitchMinioGrouped = computed(() => {
  const map = new Map<string, string[]>();
  for (const rel of stitchMinioFiles.value) {
    const i = rel.indexOf("/");
    const folder = i === -1 ? "(raiz)" : rel.slice(0, i);
    const file = i === -1 ? rel : rel.slice(i + 1);
    if (!map.has(folder)) map.set(folder, []);
    map.get(folder)!.push(file);
  }
  const meta = stitchMinioFolderMeta.value;
  return [...map.entries()]
    .map(([folder, files]) => {
      const m = meta[folder];
      const displayTitle = (m?.title && m.title.trim()) || folder;
      return {
        folder,
        files: sortStitchMinioFiles(files),
        displayTitle,
        exportOrder: typeof m?.exportOrder === "number" ? m.exportOrder : undefined,
      };
    })
    .sort((a, b) => {
      const ao = a.exportOrder;
      const bo = b.exportOrder;
      if (ao != null && bo != null && ao !== bo) return ao - bo;
      if (ao != null && bo == null) return -1;
      if (ao == null && bo != null) return 1;
      return a.folder.localeCompare(b.folder, "pt");
    });
});

/** PNG do export MinIO — ordem do protótipo invertida (último ecrã primeiro). */
const stitchDeliveriesPngRelsOrdered = computed(() => {
  const pngs = stitchMinioFiles.value.filter((r) => /\.png$/i.test(r));
  const foldersOrder = stitchMinioGrouped.value.map((g) => g.folder);
  const folderRank = new Map(foldersOrder.map((f, i) => [f, i]));
  const sorted = [...pngs].sort((a, b) => {
    const fa = a.includes("/") ? a.slice(0, a.indexOf("/")) : "(raiz)";
    const fb = b.includes("/") ? b.slice(0, b.indexOf("/")) : "(raiz)";
    const ra = folderRank.get(fa) ?? 999;
    const rb = folderRank.get(fb) ?? 999;
    if (ra !== rb) return ra - rb;
    return a.localeCompare(b, "pt");
  });
  return sorted.slice().reverse();
});

/** `ecra.html` / `ecra.svg` por pasta — ordem invertida (último ecrã primeiro). */
const stitchDeliveriesEcraRelsOrdered = computed(() => {
  const list: string[] = [];
  for (const g of stitchMinioGrouped.value) {
    if (g.folder === "(raiz)") continue;
    for (const f of g.files) {
      if (/^ecra\.(html|svg)$/i.test(f)) list.push(`${g.folder}/${f}`);
    }
  }
  for (const rel of stitchMinioFiles.value) {
    const i = rel.indexOf("/");
    if (i === -1 && /^ecra\.(html|svg)$/i.test(rel)) list.push(rel);
  }
  return list.slice().reverse();
});

const STITCH_SLIDE_EXTERNAL_IMAGE = "__stitch_external_image__";
const STITCH_SLIDE_EXTERNAL_HTML = "__stitch_external_html__";

const showStitchDeliveriesImageModal = ref(false);
const showStitchDeliveriesHtmlModal = ref(false);
const stitchImgCarouselIndex = ref(0);
const stitchHtmlCarouselIndex = ref(0);
const stitchImgRels = ref<string[]>([]);
const stitchImgSrc = ref<(string | undefined)[]>([]);
const stitchHtmlRels = ref<string[]>([]);
const stitchHtmlSrc = ref<(string | undefined)[]>([]);
const stitchGalleryImgLoading = ref(false);
const stitchGalleryHtmlLoading = ref(false);
const stitchGalleryImgErr = ref("");
const stitchGalleryHtmlErr = ref("");
let stitchImgLoadDepth = 0;
let stitchHtmlLoadDepth = 0;

function cleanupStitchImgBlobs() {
  for (const u of stitchImgSrc.value) {
    if (u && u.startsWith("blob:")) URL.revokeObjectURL(u);
  }
  stitchImgSrc.value = [];
  stitchImgRels.value = [];
}

function cleanupStitchHtmlBlobs() {
  for (const u of stitchHtmlSrc.value) {
    if (u && u.startsWith("blob:")) URL.revokeObjectURL(u);
  }
  stitchHtmlSrc.value = [];
  stitchHtmlRels.value = [];
}

async function loadStitchImgSlide(i: number) {
  if (i < 0 || i >= stitchImgRels.value.length) return;
  if (stitchImgSrc.value[i]) return;
  const rel = stitchImgRels.value[i];
  if (!project.value) return;
  if (rel === STITCH_SLIDE_EXTERNAL_IMAGE) {
    const u = stitchApiResult.value?.image_url;
    if (u) {
      const next = [...stitchImgSrc.value];
      next[i] = u;
      stitchImgSrc.value = next;
    }
    return;
  }
  stitchImgLoadDepth += 1;
  stitchGalleryImgLoading.value = true;
  stitchGalleryImgErr.value = "";
  try {
    const path = `/projects/${project.value.id}/prototipo/stitch-api/export-file?rel=${encodeURIComponent(rel)}`;
    const blob = await apiBlob(path);
    const url = URL.createObjectURL(blob);
    if (i !== stitchImgCarouselIndex.value) {
      URL.revokeObjectURL(url);
      return;
    }
    const next = [...stitchImgSrc.value];
    next[i] = url;
    stitchImgSrc.value = next;
  } catch (e) {
    if (i === stitchImgCarouselIndex.value) {
      stitchGalleryImgErr.value = e instanceof Error ? e.message : "Erro ao carregar imagem.";
    }
  } finally {
    stitchImgLoadDepth = Math.max(0, stitchImgLoadDepth - 1);
    stitchGalleryImgLoading.value = stitchImgLoadDepth > 0;
  }
}

async function loadStitchHtmlSlide(i: number) {
  if (i < 0 || i >= stitchHtmlRels.value.length) return;
  if (stitchHtmlSrc.value[i]) return;
  const rel = stitchHtmlRels.value[i];
  if (!project.value) return;
  if (rel === STITCH_SLIDE_EXTERNAL_HTML) {
    const u = stitchApiResult.value?.html_url;
    if (u) {
      const next = [...stitchHtmlSrc.value];
      next[i] = u;
      stitchHtmlSrc.value = next;
    }
    return;
  }
  stitchHtmlLoadDepth += 1;
  stitchGalleryHtmlLoading.value = true;
  stitchGalleryHtmlErr.value = "";
  try {
    const path = `/projects/${project.value.id}/prototipo/stitch-api/export-file?rel=${encodeURIComponent(rel)}`;
    let url: string;
    if (/\.html?$/i.test(rel)) {
      const raw = await apiText(path);
      const withViewer = prepareStitchExportHtmlForViewer(raw, project.value.id, rel);
      url = URL.createObjectURL(new Blob([withViewer], { type: "text/html;charset=utf-8" }));
    } else {
      const blob = await apiBlob(path);
      url = URL.createObjectURL(blob);
    }
    if (i !== stitchHtmlCarouselIndex.value) {
      URL.revokeObjectURL(url);
      return;
    }
    const next = [...stitchHtmlSrc.value];
    next[i] = url;
    stitchHtmlSrc.value = next;
  } catch (e) {
    if (i === stitchHtmlCarouselIndex.value) {
      stitchGalleryHtmlErr.value = e instanceof Error ? e.message : "Erro ao carregar HTML.";
    }
  } finally {
    stitchHtmlLoadDepth = Math.max(0, stitchHtmlLoadDepth - 1);
    stitchGalleryHtmlLoading.value = stitchHtmlLoadDepth > 0;
  }
}

async function openStitchDeliveriesImageModal() {
  stitchGalleryImgErr.value = "";
  let rels = stitchDeliveriesPngRelsOrdered.value;
  if (stitchApiResult.value?.export_storage_prefix && stitchMinioFiles.value.length === 0) {
    await loadStitchMinioFileList();
    rels = stitchDeliveriesPngRelsOrdered.value;
  }
  if (rels.length === 0 && stitchApiResult.value?.image_url) {
    stitchImgRels.value = [STITCH_SLIDE_EXTERNAL_IMAGE];
  } else if (rels.length === 0) {
    prototipoPromptErr.value =
      "Não há PNG no export MinIO. Aprove o protótipo ou recarregue a página para sincronizar a lista.";
    return;
  } else {
    stitchImgRels.value = [...rels];
  }
  stitchImgCarouselIndex.value = 0;
  stitchImgSrc.value = stitchImgRels.value.map(() => undefined);
  showStitchDeliveriesImageModal.value = true;
  await loadStitchImgSlide(0);
}

async function openStitchDeliveriesHtmlModal() {
  stitchGalleryHtmlErr.value = "";
  let rels = stitchDeliveriesEcraRelsOrdered.value;
  if (stitchApiResult.value?.export_storage_prefix && stitchMinioFiles.value.length === 0) {
    await loadStitchMinioFileList();
    rels = stitchDeliveriesEcraRelsOrdered.value;
  }
  if (rels.length === 0 && stitchApiResult.value?.html_url) {
    stitchHtmlRels.value = [STITCH_SLIDE_EXTERNAL_HTML];
  } else if (rels.length === 0) {
    prototipoPromptErr.value =
      "Não há ficheiros ecra.html no export MinIO. Aprove o export ou recarregue a página para sincronizar.";
    return;
  } else {
    stitchHtmlRels.value = [...rels];
  }
  stitchHtmlCarouselIndex.value = 0;
  stitchHtmlSrc.value = stitchHtmlRels.value.map(() => undefined);
  showStitchDeliveriesHtmlModal.value = true;
  await loadStitchHtmlSlide(0);
}

function closeStitchDeliveriesImageModal() {
  showStitchDeliveriesImageModal.value = false;
  cleanupStitchImgBlobs();
  stitchImgCarouselIndex.value = 0;
  stitchGalleryImgErr.value = "";
  stitchImgLoadDepth = 0;
  stitchGalleryImgLoading.value = false;
}

function closeStitchDeliveriesHtmlModal() {
  showStitchDeliveriesHtmlModal.value = false;
  cleanupStitchHtmlBlobs();
  stitchHtmlCarouselIndex.value = 0;
  stitchGalleryHtmlErr.value = "";
  stitchHtmlLoadDepth = 0;
  stitchGalleryHtmlLoading.value = false;
}

function stitchImgCarouselPrev() {
  if (stitchGalleryImgLoading.value) return;
  if (stitchImgCarouselIndex.value <= 0) return;
  stitchImgCarouselIndex.value -= 1;
  void loadStitchImgSlide(stitchImgCarouselIndex.value);
}

function stitchImgCarouselNext() {
  if (stitchGalleryImgLoading.value) return;
  if (stitchImgCarouselIndex.value >= stitchImgRels.value.length - 1) return;
  stitchImgCarouselIndex.value += 1;
  void loadStitchImgSlide(stitchImgCarouselIndex.value);
}

function stitchHtmlCarouselPrev() {
  if (stitchGalleryHtmlLoading.value) return;
  if (stitchHtmlCarouselIndex.value <= 0) return;
  stitchHtmlCarouselIndex.value -= 1;
  void loadStitchHtmlSlide(stitchHtmlCarouselIndex.value);
}

function stitchHtmlCarouselNext() {
  if (stitchGalleryHtmlLoading.value) return;
  if (stitchHtmlCarouselIndex.value >= stitchHtmlRels.value.length - 1) return;
  stitchHtmlCarouselIndex.value += 1;
  void loadStitchHtmlSlide(stitchHtmlCarouselIndex.value);
}

function stitchImgSlideLabel(i: number): string {
  const rel = stitchImgRels.value[i];
  if (rel === STITCH_SLIDE_EXTERNAL_IMAGE) return "Pré-visualização Stitch (API)";
  return rel;
}

function stitchHtmlSlideLabel(i: number): string {
  const rel = stitchHtmlRels.value[i];
  if (rel === STITCH_SLIDE_EXTERNAL_HTML) return "Pré-visualização Stitch (API)";
  return rel;
}

function onStitchGalleryKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (showStitchDeliveriesImageModal.value) closeStitchDeliveriesImageModal();
    if (showStitchDeliveriesHtmlModal.value) closeStitchDeliveriesHtmlModal();
    return;
  }
  if (showStitchDeliveriesImageModal.value) {
    if (e.key === "ArrowLeft") stitchImgCarouselPrev();
    else if (e.key === "ArrowRight") stitchImgCarouselNext();
  } else if (showStitchDeliveriesHtmlModal.value) {
    if (e.key === "ArrowLeft") stitchHtmlCarouselPrev();
    else if (e.key === "ArrowRight") stitchHtmlCarouselNext();
  }
}

watch(
  () => showStitchDeliveriesImageModal.value || showStitchDeliveriesHtmlModal.value,
  (anyOpen) => {
    if (anyOpen) window.addEventListener("keydown", onStitchGalleryKeydown);
    else window.removeEventListener("keydown", onStitchGalleryKeydown);
  },
);

async function loadStitchMinioFolderMetas() {
  if (!project.value) return;
  const folders = new Set<string>();
  for (const rel of stitchMinioFiles.value) {
    const i = rel.indexOf("/");
    if (i > 0) folders.add(rel.slice(0, i));
  }
  const metaMap: Record<string, { exportOrder?: number; title?: string; htmlUrl?: string }> = {};
  await Promise.all(
    [...folders].map(async (folder) => {
      try {
        const rel = `${folder}/meta.json`;
        const m = await api<Record<string, unknown>>(
          `/projects/${project.value!.id}/prototipo/stitch-api/export-file?rel=${encodeURIComponent(rel)}`,
        );
        metaMap[folder] = {
          exportOrder: typeof m.exportOrder === "number" ? m.exportOrder : undefined,
          title: typeof m.title === "string" ? m.title : undefined,
          htmlUrl: typeof m.htmlUrl === "string" ? m.htmlUrl : undefined,
        };
      } catch {
        metaMap[folder] = {};
      }
    }),
  );
  stitchMinioFolderMeta.value = metaMap;
}

const DEFAULT_DETAIL_TAB_ORDER: DetailTab[] = [
  "resumo",
  "prd",
  "prototipo",
  "planejamento",
  "kanban",
  "anexos",
  "auditoria",
  "github",
  "wiki",
  "cursor",
];

const MAIN_TAB_LABELS: Record<MainTab, string> = {
  resumo: "Resumo",
  prd: "PRD",
  prototipo: "Protótipo",
  planejamento: "Planejamento",
  kanban: "Desenvolvimento",
  anexos: "Anexos",
  auditoria: "Auditoria",
  configuracoes: "Configurações",
};

const CONFIG_TAB_LABELS: Record<ConfigTab, string> = {
  github: "GitHub",
  wiki: "Wiki",
  cursor: "Cursor Hub",
};

/** Na URL usa-se «desenvolvimento» (igual ao título da aba); internamente continua `kanban`. */
const KANBAN_TAB_QUERY_PARAM = "desenvolvimento";

function detailTabToQueryParam(tab: DetailTab): string {
  return tab === "kanban" ? KANBAN_TAB_QUERY_PARAM : tab;
}

function queryParamToDetailTab(raw: string): DetailTab | undefined {
  const low = raw.trim().toLowerCase();
  if (low === KANBAN_TAB_QUERY_PARAM || low === "kanban") return "kanban";
  const valid = new Set<DetailTab>(DEFAULT_DETAIL_TAB_ORDER);
  if (valid.has(low as DetailTab)) return low as DetailTab;
  return undefined;
}

function orderDetailTabsByFlowConfig(rawTabs?: string[]): DetailTab[] {
  if (!rawTabs?.length) return [...DEFAULT_DETAIL_TAB_ORDER];
  const valid = new Set<DetailTab>(DEFAULT_DETAIL_TAB_ORDER);
  const ordered = rawTabs
    .map((x) => String(x).toLowerCase())
    .filter((x): x is DetailTab => valid.has(x as DetailTab))
    .filter((x, i, arr) => arr.indexOf(x) === i);
  return ordered.length ? ordered : [...DEFAULT_DETAIL_TAB_ORDER];
}

function applyTabFromRoute() {
  const raw = route.query.tab;
  const t = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : undefined;
  if (!t) return;
  const parsed = queryParamToDetailTab(t);
  if (!parsed) return;
  const allowed = visibleDetailTabs.value;
  if ((allowed as string[]).includes(parsed)) activeTab.value = parsed;
}

const visibleDetailTabs = computed<DetailTab[]>(() => {
  const currentColId = project.value?.current_column_id;
  if (!currentColId) return [...DEFAULT_DETAIL_TAB_ORDER];
  const col = templateCols.value.find((c) => c.id === currentColId);
  return orderDetailTabsByFlowConfig(col?.visible_detail_tabs ?? []);
});

const configTabs = computed(() =>
  visibleDetailTabs.value
    .filter((tab): tab is ConfigTab => tab === "github" || tab === "wiki" || tab === "cursor")
    .map((id) => ({ id, label: CONFIG_TAB_LABELS[id] })),
);
const mainTabs = computed(() => {
  const orderedMainIds: MainTab[] = [];
  for (const tab of visibleDetailTabs.value) {
    if (tab === "github" || tab === "wiki" || tab === "cursor") continue;
    orderedMainIds.push(tab as Exclude<MainTab, "configuracoes">);
  }
  if (configTabs.value.length) orderedMainIds.push("configuracoes");
  return orderedMainIds.map((id) => ({ id, label: MAIN_TAB_LABELS[id] }));
});

const activeMainTab = computed<MainTab>(() => {
  if (activeTab.value === "github" || activeTab.value === "wiki" || activeTab.value === "cursor") {
    return "configuracoes";
  }
  return activeTab.value as Exclude<DetailTab, ConfigTab>;
});

function setMainTab(tabId: MainTab) {
  if (tabId === "configuracoes") {
    if (activeTab.value !== "github" && activeTab.value !== "wiki" && activeTab.value !== "cursor") {
      activeTab.value = "github";
    }
    return;
  }
  activeTab.value = tabId;
}

function setConfigTab(tabId: ConfigTab) {
  activeTab.value = tabId;
}

function firstVisibleTab(): DetailTab {
  const firstMain = mainTabs.value[0];
  if (!firstMain) return "resumo";
  if (firstMain.id === "configuracoes") {
    return (configTabs.value[0]?.id ?? "resumo") as DetailTab;
  }
  return firstMain.id as DetailTab;
}

function scrollToRouteHash() {
  const h = (route.hash || "").replace(/^#/, "");
  if (!h) return;
  nextTick(() => {
    document.getElementById(h)?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

onMounted(load);
watch(
  () => route.fullPath,
  () => {
    applyTabFromRoute();
    if (!visibleDetailTabs.value.includes(activeTab.value)) {
      activeTab.value = firstVisibleTab();
    }
    scrollToRouteHash();
  },
);

watch(visibleDetailTabs, (tabs) => {
  if (!tabs.includes(activeTab.value)) {
    activeTab.value = firstVisibleTab();
  }
});

/** Mantém `?tab=` alinhado com a aba ao clicar; «resumo» omite o parâmetro. */
watch(
  activeTab,
  (tab) => {
    const cur =
      typeof route.query.tab === "string"
        ? route.query.tab
        : Array.isArray(route.query.tab)
          ? route.query.tab[0]
          : undefined;
    const desired = tab === "resumo" ? undefined : detailTabToQueryParam(tab);
    if (tab === "resumo" && (cur === undefined || cur === "")) return;
    if (desired !== undefined && cur === desired) return;
    const q = { ...route.query } as Record<string, string | string[] | undefined>;
    if (tab === "resumo") delete q.tab;
    else q.tab = desired;
    void router.replace({ path: route.path, query: q, hash: route.hash });
  },
  { flush: "post" },
);

watch(
  () => [activeTab.value, project.value?.id] as const,
  ([tab]) => {
    if (tab === "prototipo" && project.value) void loadPrototipoDocument();
  },
);

watch(
  () => ({
    sync: route.query.github_sync,
    repo: project.value?.github_repo_url,
    id: project.value?.id,
  }),
  async ({ sync, repo, id }) => {
    const one = typeof sync === "string" ? sync : Array.isArray(sync) ? sync[0] : undefined;
    if (one !== "1" || id == null || !repo?.trim()) return;
    err.value = "";
    try {
      await auth.fetchMe();
      await loadTags();
      msg.value = "Conta GitHub ligada. Tags sincronizadas.";
    } catch {
      /* loadTags ou fetchMe já preenchem err quando aplicável */
    }
    const { github_sync: _drop, ...rest } = route.query;
    await router.replace({ path: route.path, query: rest, hash: route.hash });
  },
  { flush: "post" },
);
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
});

function formatHeroDate(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("pt-BR", { day: "numeric", month: "short", year: "numeric" });
}

function repoDisplayPath(url: string | null) {
  if (!url) return "—";
  try {
    const u = url.replace(/^https?:\/\//i, "").replace(/^www\./, "");
    return u.length > 42 ? u.slice(0, 40) + "…" : u;
  } catch {
    return url;
  }
}

const healthBadge = computed(() => {
  const p = project.value;
  if (!p) return { label: "—", class: "bg-surface-container-high text-on-surface" };
  if (p.ended_at) return { label: "Encerrado", class: "bg-outline-variant text-on-surface" };
  const end = new Date(p.planned_end + "T12:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (end < today) return { label: "Atenção", class: "bg-error-container text-on-error-container" };
  const col = (p.current_column_title ?? "").toLowerCase();
  if (col.includes("conclu")) return { label: "Concluído", class: "bg-tertiary-container text-on-tertiary-container" };
  return { label: "Saudável", class: "bg-tertiary-container text-on-tertiary-container" };
});

const governanceProgress = computed(() => {
  if (wiki.value?.status === "ready") return 94;
  if (wiki.value?.status === "pending") return 62;
  if (project.value?.github_tag) return 78;
  return 55;
});

const initials = computed(() => {
  const po = project.value?.product_owner ?? "";
  const parts = po.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return po.slice(0, 2).toUpperCase() || "PO";
});

function auditTitle(action: string) {
  const m: Record<string, string> = {
    "project.create": "Projeto criado",
    "project.update": "Dados do processo atualizados",
    "project.kanban.move": "Kanban atualizado",
    "project.github.link": "Repositório vinculado",
    "project.github.tag": "Tag ou ref aplicada",
    "project.wiki.generate": "Geração de Wiki solicitada",
    "project.attachment.add": "Anexo adicionado",
    "project.delete": "Projeto excluído",
  };
  return m[action] ?? action.replace(/^project\./, "").replace(/\./g, " ");
}

function auditIcon(action: string) {
  if (action.includes("wiki")) return "auto_awesome";
  if (action.includes("github")) return "terminal";
  if (action.includes("kanban")) return "commit";
  if (action.includes("attachment")) return "attach_file";
  if (action.includes("create")) return "add_task";
  return "person";
}

function relTime(iso: string) {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return "Agora";
  if (h < 24) return `Há ${h} hora${h === 1 ? "" : "s"}`;
  const days = Math.floor(h / 24);
  if (days === 1) return "Ontem";
  return `Há ${days} dias`;
}

function formatAuditDateTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function syncEditDraftFromProject() {
  const p = project.value;
  if (!p) return;
  editDraft.value = {
    name: p.name,
    product_owner: p.product_owner,
    directory_id: p.directory_id,
    methodology: p.methodology === "base44" ? "base44" : "prd",
    planned_start: p.planned_start?.slice(0, 10) ?? "",
    planned_end: p.planned_end?.slice(0, 10) ?? "",
    ended_at: p.ended_at ? p.ended_at.slice(0, 10) : "",
  };
}

async function loadGithubOAuthStatus() {
  try {
    const s = await api<{ oauth_configured: boolean }>("/auth/github/status");
    ghOAuthConfigured.value = s.oauth_configured;
  } catch {
    ghOAuthConfigured.value = false;
  }
}

async function load() {
  err.value = "";
  const id = Number(route.params.id);
  try {
    directories.value = await api<Dir[]>("/directories");
  } catch {
    directories.value = [];
  }
  await loadGithubOAuthStatus();
  project.value = await api<Project>(`/projects/${id}`);
  const all = await api<Tpl[]>("/kanban-templates");
  const tpl = all.find((t) => t.id === project.value!.template_id);
  templateCols.value = (tpl?.columns ?? []).slice().sort((a, b) => a.position - b.position);
  repoUrl.value = project.value.github_repo_url ?? "";
  syncEditDraftFromProject();
  await refreshWiki();
  await loadAuditFeed();
  await loadPlanejamentoStored();
  applyTabFromRoute();
  scrollToRouteHash();
}

function hydratePlanejamentoFromText(source: string) {
  let raw = (source || "").trim();
  raw = raw.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/i, "").trim();
  try {
    const parsed: unknown = JSON.parse(raw);
    planejamentoExpanded.value = initPlanejamentoExpanded(parsed);
    planejamentoAgentParsed.value = parsed;
    planejamentoAgentOutput.value = JSON.stringify(parsed, null, 2);
  } catch {
    planejamentoExpanded.value = {};
    planejamentoAgentParsed.value = null;
    planejamentoAgentOutput.value = raw;
  }
  planejamentoSelectedPathKey.value = null;
}

function planejamentoMethodologyLabel(m: string): string {
  const x = (m || "").toLowerCase();
  if (x === "prd") return "PRD + protótipo (Stitch)";
  if (x === "base44") return "Base44";
  return m?.trim() || "—";
}

function planejamentoSimNao(v: boolean): string {
  return v ? "Sim" : "Não";
}

async function loadPlanejamentoStored() {
  if (!project.value) return;
  try {
    const sto = await api<{
      text: string | null;
      saved_at: string | null;
      approved_at: string | null;
      context: PlanejamentoContext;
    }>(`/projects/${project.value.id}/planejamento`);
    planejamentoContext.value = sto.context ?? null;
    if (sto.text?.trim()) {
      hydratePlanejamentoFromText(sto.text);
    } else {
      planejamentoAgentOutput.value = "";
      planejamentoAgentParsed.value = null;
      planejamentoExpanded.value = {};
      planejamentoSelectedPathKey.value = null;
    }
  } catch {
    planejamentoContext.value = null;
    /* ignora */
  }
}

async function onPrdMarkdownSaved() {
  if (!project.value) return;
  try {
    project.value = await api<Project>(`/projects/${project.value.id}`);
  } catch {
    /* ignora */
  }
}

async function onPrdChatSaved() {
  await onPrdMarkdownSaved();
  await prdVersionsPanelRef.value?.reload?.();
}

async function onPrototipoVersionSavedFromPanel() {
  await loadPrototipoDocument();
}

/** Abre separador vazio no gesto do utilizador; depois de `await` usa-se para navegar ao Stitch (evita bloqueio de pop-up). */
function openStitchPlaceholderTab(): Window | null {
  try {
    return window.open("about:blank", "_blank");
  } catch {
    return null;
  }
}

function closeStitchPlaceholderTab(win: Window | null) {
  if (!win || win.closed) return;
  try {
    win.close();
  } catch {
    /* ignore */
  }
}

/** Copia o texto e envia o separador placeholder para o Stitch (ou abre um novo). Devolve se a cópia funcionou. */
async function copyPromptAndShowStitch(text: string, placeholder: Window | null): Promise<boolean> {
  let copied = true;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    copied = false;
  }
  if (placeholder && !placeholder.closed) {
    try {
      placeholder.location.href = STITCH_APP_URL;
    } catch {
      window.open(STITCH_APP_URL, "_blank", "noopener,noreferrer");
    }
  } else {
    window.open(STITCH_APP_URL, "_blank", "noopener,noreferrer");
  }
  return copied;
}

async function loadPrototipoDocument() {
  if (!project.value) return;
  prototipoPromptErr.value = "";
  prototipoPromptMsg.value = "";
  try {
    const doc = await api<{
      prompt: string;
      version: number | null;
      saved_at: string | null;
      prd_version_used: number | null;
      stitch_latest?: {
        stitch_project_id: string;
        screen_id: string;
        html_url: string;
        image_url: string;
        created_at?: string | null;
        saved_id?: number | null;
        approved_at?: string | null;
        approved_by_email?: string | null;
        export_storage_prefix?: string | null;
      } | null;
    }>(`/projects/${project.value.id}/prototipo`);
    prototipoPrompt.value = doc.prompt ?? "";
    prototipoPromptVersion.value = doc.version ?? null;
    prototipoPrdVersion.value = doc.prd_version_used ?? null;
    if (doc.stitch_latest) {
      stitchApiResult.value = {
        stitch_project_id: doc.stitch_latest.stitch_project_id,
        screen_id: doc.stitch_latest.screen_id,
        html_url: doc.stitch_latest.html_url,
        image_url: doc.stitch_latest.image_url,
        approved_at: doc.stitch_latest.approved_at ?? null,
        approved_by_email: doc.stitch_latest.approved_by_email ?? null,
        export_storage_prefix: doc.stitch_latest.export_storage_prefix ?? null,
      };
    } else {
      stitchApiResult.value = null;
    }
    await loadStitchApiStatus();
    if (doc.stitch_latest?.export_storage_prefix) {
      await loadStitchMinioFileList();
    } else {
      stitchMinioFiles.value = [];
      stitchMinioFolderMeta.value = {};
    }
    void prototipoVersionsPanelRef.value?.reload?.();
  } catch {
    prototipoPrompt.value = "";
    prototipoPromptVersion.value = null;
    prototipoPrdVersion.value = null;
    stitchApiResult.value = null;
    stitchMinioFiles.value = [];
    stitchMinioFolderMeta.value = {};
  }
}

async function loadStitchMinioFileList() {
  if (!project.value) return;
  if (!stitchApiResult.value?.export_storage_prefix) {
    stitchMinioFiles.value = [];
    stitchMinioFolderMeta.value = {};
    return;
  }
  try {
    const m = await api<{ storage_prefix: string; files: string[] }>(
      `/projects/${project.value.id}/prototipo/stitch-api/export-manifest`,
    );
    stitchMinioFiles.value = m.files ?? [];
    await loadStitchMinioFolderMetas();
  } catch {
    stitchMinioFiles.value = [];
    stitchMinioFolderMeta.value = {};
  }
}

async function loadStitchApiStatus() {
  if (!project.value) return;
  try {
    const s = await api<{ ready: boolean; detail: string }>(
      `/projects/${project.value.id}/prototipo/stitch-api/status`,
    );
    stitchApiReady.value = s.ready;
    stitchApiDetail.value = s.detail || "";
  } catch {
    stitchApiReady.value = false;
    stitchApiDetail.value = "";
  }
}

async function generateStitchApiScreen() {
  if (!project.value || !canEditPrototipoPrompt.value) return;
  if (!prototipoPrompt.value.trim()) {
    prototipoPromptErr.value =
      "Não há prompt na última versão. Use o painel «Versões do prompt» ou «Gerar prompt (último PRD)».";
    return;
  }
  stitchApiGenerating.value = true;
  prototipoPromptErr.value = "";
  stitchMinioFiles.value = [];
  stitchMinioFolderMeta.value = {};
  stitchApiResult.value = null;
  try {
    const out = await api<{
      html_url: string;
      image_url: string;
      stitch_project_id: string;
      screen_id: string;
      saved_id?: number | null;
    }>(`/projects/${project.value.id}/prototipo/stitch-api/generate`, { method: "POST", body: "{}" });
    stitchApiResult.value = {
      ...out,
      approved_at: null,
      approved_by_email: null,
      export_storage_prefix: null,
    };
    prototipoPromptMsg.value = `Stitch (API): ecrã ${out.screen_id} gerado. Links abaixo.`;
  } catch (e) {
    prototipoPromptErr.value = e instanceof Error ? e.message : "Falha ao chamar a API Stitch.";
  } finally {
    stitchApiGenerating.value = false;
  }
}

async function approveAndSaveStitchToMinio() {
  if (!project.value || !canEditPrototipoPrompt.value) return;
  if (!stitchApiResult.value?.stitch_project_id) {
    prototipoPromptErr.value = "Não há projeto Stitch na sessão. Gere um ecrã ou recarregue a aba.";
    return;
  }
  stitchApproveExporting.value = true;
  prototipoPromptErr.value = "";
  try {
    await api<{ storage_prefix: string }>(
      `/projects/${project.value.id}/prototipo/stitch-api/approve-and-export`,
      {
        method: "POST",
        body: "{}",
      },
    );
    prototipoPromptMsg.value = "Protótipo aprovado; os ecrãs estão gravados no MinIO.";
    await loadPrototipoDocument();
  } catch (e) {
    prototipoPromptErr.value =
      e instanceof Error ? e.message : "Falha ao aprovar ou ao gravar no MinIO.";
  } finally {
    stitchApproveExporting.value = false;
  }
}

async function generatePrototipoPrompt() {
  if (!project.value || !canEditPrototipoPrompt.value) return;
  const stitchTab = openStitchPlaceholderTab();
  prototipoGenerating.value = true;
  prototipoPromptErr.value = "";
  prototipoPromptMsg.value = "";
  try {
    const out = await api<{
      prompt: string;
      prd_version: number | null;
      prompt_version: number;
    }>(`/projects/${project.value.id}/prototipo/generate-prompt`, { method: "POST", body: "{}" });
    prototipoPrompt.value = out.prompt;
    prototipoPrdVersion.value = out.prd_version ?? null;
    prototipoPromptVersion.value = out.prompt_version;

    const copied = await copyPromptAndShowStitch(out.prompt, stitchTab);
    const stitchHint = copied
      ? " Prompt na área de transferência; no Stitch, Ctrl+V (ou ⌘V) no chat e envie."
      : " Stitch aberto — copie o prompt deste campo (a cópia automática falhou).";
    prototipoPromptMsg.value = `Guardado na versão ${out.prompt_version}.${stitchHint}`;
    if (!copied) {
      prototipoPromptErr.value =
        "Não foi possível copiar automaticamente; copie o texto do campo ou permita acesso à área de transferência.";
    }

    try {
      project.value = await api<Project>(`/projects/${project.value.id}`);
    } catch {
      /* ignora */
    }
    void prototipoVersionsPanelRef.value?.reload?.();
  } catch (e) {
    closeStitchPlaceholderTab(stitchTab);
    prototipoPromptErr.value = e instanceof Error ? e.message : "Não foi possível gerar o prompt.";
  } finally {
    prototipoGenerating.value = false;
  }
}

async function runPlanejamentoAzureAgent() {
  if (!project.value || !canEditPrototipoPrompt.value) return;
  planejamentoAgentLoading.value = true;
  planejamentoAgentErr.value = "";
  planejamentoAgentWarnings.value = [];
  planejamentoAgentOutput.value = "";
  planejamentoAgentParsed.value = null;
  planejamentoExpanded.value = {};
  planejamentoSelectedPathKey.value = null;
  try {
    const out = await api<{
      text: string;
      finish_reason?: string | null;
      warnings?: string[];
    }>(`/projects/${project.value.id}/planejamento/azure-agent`, { method: "POST", body: "{}" });
    planejamentoAgentWarnings.value = out.warnings ?? [];
    hydratePlanejamentoFromText(out.text || "");
    try {
      project.value = await api<Project>(`/projects/${project.value.id}`);
    } catch {
      /* ignora */
    }
    await loadPlanejamentoStored();
  } catch (e) {
    planejamentoAgentErr.value = e instanceof Error ? e.message : "Falha ao contactar o agente.";
  } finally {
    planejamentoAgentLoading.value = false;
  }
}

async function setPlanejamentoApproval(approved: boolean) {
  if (!project.value || !canEditPrototipoPrompt.value) return;
  planejamentoApprovalLoading.value = true;
  planejamentoAgentErr.value = "";
  planejamentoApprovalMsg.value = "";
  try {
    const out = await api<{
      approved_at: string | null;
      tasks_removed: number;
      tasks_created: number;
    }>(`/projects/${project.value.id}/planejamento/approval`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    });
    project.value = await api<Project>(`/projects/${project.value.id}`);
    if (approved) {
      planejamentoApprovalMsg.value =
        out.tasks_created > 0
          ? `${out.tasks_created} tarefa(s) criada(s) na aba Desenvolvimento (primeira raia), na ordem do planejamento.`
          : "Planejamento aprovado. Não foram encontrados itens no JSON para criar tarefas no quadro.";
    } else {
      planejamentoApprovalMsg.value =
        out.tasks_removed > 0
          ? `${out.tasks_removed} tarefa(s) gerada(s) pelo planejamento removida(s) do quadro.`
          : "Aprovação do planejamento anulada.";
    }
    await projectTaskBoardRef.value?.reload?.();
  } catch (e) {
    planejamentoAgentErr.value = e instanceof Error ? e.message : "Falha ao gravar aprovação.";
  } finally {
    planejamentoApprovalLoading.value = false;
  }
}

function cancelEditProcess() {
  editingProcess.value = false;
  syncEditDraftFromProject();
}

async function saveProcess() {
  if (!canMove.value || !project.value) return;
  savingProcess.value = true;
  err.value = "";
  msg.value = "";
  try {
    const id = project.value.id;
    const d = editDraft.value;
    const body = {
      name: d.name.trim(),
      product_owner: d.product_owner.trim(),
      directory_id: d.directory_id,
      methodology: d.methodology,
      planned_start: d.planned_start,
      planned_end: d.planned_end,
      ended_at: d.ended_at.trim() ? d.ended_at : null,
    };
    project.value = await api<Project>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    syncEditDraftFromProject();
    editingProcess.value = false;
    msg.value = "Dados do processo atualizados.";
    await loadAuditFeed();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Não foi possível salvar.";
  } finally {
    savingProcess.value = false;
  }
}

async function loadAuditFeed() {
  auditFeed.value = [];
  if (!canSeeAudit.value || !project.value) return;
  try {
    const all = await api<AuditItem[]>("/audit");
    auditFeed.value = all
      .filter((a) => a.entity_type === "project" && a.entity_id === project.value!.id)
      .slice(0, 6);
  } catch {
    auditFeed.value = [];
  }
}

async function refreshWiki() {
  const id = Number(route.params.id);
  try {
    wiki.value = await api<WikiResp>(`/projects/${id}/wiki`);
  } catch {
    wiki.value = null;
  }
}

function startWikiPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    await refreshWiki();
    const st = wiki.value?.status;
    if (st && st !== "pending") {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
      if (st === "ready") msg.value = "Wiki pronta.";
      if (st === "error") err.value = wiki.value?.error_message || "Erro ao gerar Wiki";
      void loadAuditFeed();
    }
  }, 2000);
}

async function confirmDeleteProject() {
  if (!canMove.value || !project.value) return;
  deleting.value = true;
  err.value = "";
  try {
    await api(`/projects/${project.value.id}`, { method: "DELETE" });
    showDeleteModal.value = false;
    await router.push("/projetos");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Não foi possível excluir o projeto.";
  } finally {
    deleting.value = false;
  }
}

async function saveGithub() {
  msg.value = "";
  err.value = "";
  try {
    const id = Number(route.params.id);
    project.value = await api<Project>(`/projects/${id}/github`, {
      method: "PATCH",
      body: JSON.stringify({ repo_url: repoUrl.value }),
    });
    tags.value = await api<string[]>(`/projects/${id}/github/tags`);
    msg.value = "Repositório vinculado. Tags da API listadas abaixo.";
    await loadAuditFeed();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

async function loadTags() {
  try {
    const id = Number(route.params.id);
    tags.value = await api<string[]>(`/projects/${id}/github/tags`);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

async function syncWithGitHub() {
  err.value = "";
  msg.value = "";
  if (!ghOAuthConfigured.value) {
    err.value = "GitHub OAuth não está configurado no servidor.";
    return;
  }
  if (!project.value?.github_repo_url?.trim()) {
    err.value = "Indique o URL do repositório e guarde com «Vincular» antes de sincronizar.";
    activeTab.value = "github";
    return;
  }
  await auth.fetchMe();
  if (!auth.me?.has_github) {
    const pid = project.value.id;
    const next = `/projetos/${pid}?tab=github&github_sync=1`;
    window.location.href = `/api/auth/github/authorize?next=${encodeURIComponent(next)}`;
    return;
  }
  await loadTags();
  msg.value = "Sincronização concluída: tags do repositório atualizadas.";
}

async function pickTag(t: string) {
  const id = Number(route.params.id);
  project.value = await api<Project>(`/projects/${id}/github/tag`, {
    method: "PATCH",
    body: JSON.stringify({ tag: t }),
  });
  await loadAuditFeed();
}

async function applyCustomRef() {
  if (!customRef.value.trim()) return;
  await pickTag(customRef.value.trim());
  customRef.value = "";
}

async function genWiki() {
  msg.value = "";
  err.value = "";
  try {
    const id = Number(route.params.id);
    await api(`/projects/${id}/wiki/generate`, { method: "POST" });
    msg.value = "Geração da Wiki enfileirada (ou processada em linha se Redis indisponível).";
    await refreshWiki();
    if (wiki.value?.status === "pending") startWikiPoll();
    await loadAuditFeed();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

async function uploadAttachment() {
  const id = Number(route.params.id);
  const f = fileEl.value?.files?.[0];
  if (!f) {
    err.value = "Selecione um arquivo.";
    return;
  }
  const fd = new FormData();
  fd.append("attachment_type", attachType.value || "arquivo");
  fd.append("file", f);
  await api(`/projects/${id}/attachments`, { method: "POST", body: fd });
  msg.value = "Anexo enviado.";
  if (fileEl.value) fileEl.value.value = "";
  await loadAuditFeed();
}

function methodologyLabel(m: string) {
  if (m === "base44") return "Base 44";
  if (m === "prd") return "PRD";
  return m;
}
</script>

<template>
  <div v-if="project" class="w-full min-w-0 max-w-none">
    <!-- Hero (protótipo detalhe_do_projeto_pt_br) -->
    <section class="px-0 sm:px-1 pt-2 pb-6">
      <div class="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <div class="flex items-center flex-wrap gap-3 mb-2">
            <span class="text-xs font-bold tracking-[0.1em] text-on-surface-variant uppercase font-label"
              >ID do projeto: SL-{{ String(project.id).padStart(4, "0") }}</span
            >
            <span class="h-1.5 w-1.5 rounded-full bg-tertiary-container shrink-0" />
            <span class="px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider font-label" :class="healthBadge.class">{{
              healthBadge.label
            }}</span>
          </div>
          <h1 id="governance-nome" class="text-4xl md:text-5xl font-extrabold font-headline tracking-tighter text-on-surface mb-4 scroll-mt-24">
            {{ project.name }}
          </h1>
          <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-outline text-lg">calendar_today</span>
              <span class="text-sm font-medium text-on-surface-variant font-body"
                >Prazo: <span class="text-on-surface">{{ formatHeroDate(project.planned_end) }}</span></span
              >
            </div>
            <div id="governance-po" class="flex items-center gap-2 scroll-mt-24">
              <span class="material-symbols-outlined text-outline text-lg">person</span>
              <span class="text-sm font-medium text-on-surface-variant font-body"
                >Líder: <span class="text-on-surface">{{ project.product_owner }}</span></span
              >
            </div>
            <div id="governance-metodologia" class="flex -space-x-2 scroll-mt-24">
              <div
                class="h-6 w-6 rounded-full border-2 border-surface bg-surface-container-high flex items-center justify-center text-[9px] font-bold text-on-surface"
              >
                {{ initials.slice(0, 1) }}
              </div>
              <div
                class="h-6 w-6 rounded-full border-2 border-surface bg-secondary-fixed-dim flex items-center justify-center text-[9px] font-bold text-on-secondary-fixed"
              >
                {{ initials.slice(1, 2) || "·" }}
              </div>
              <div
                class="h-6 w-6 rounded-full border-2 border-surface bg-surface-container-high flex items-center justify-center text-[8px] font-bold text-on-surface-variant"
              >
                {{ methodologyLabel(project.methodology).slice(0, 1) }}
              </div>
            </div>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <button
            v-if="canMove"
            type="button"
            class="border border-error/40 text-error px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-error-container/30 transition-colors font-body"
            @click="showDeleteModal = true"
          >
            Excluir projeto
          </button>
        </div>
      </div>

      <!-- Abas -->
      <div class="mt-10 border-b border-outline-variant/15 font-body">
        <div class="flex flex-wrap gap-x-8 gap-y-2">
          <button
            v-for="t in mainTabs"
            :key="t.id"
            type="button"
            class="pb-4 text-sm transition-colors inline-flex items-center gap-1"
            :class="
              activeMainTab === t.id
                ? 'text-black font-bold border-b-2 border-black -mb-px'
                : 'text-on-surface-variant hover:text-black font-medium'
            "
            @click="setMainTab(t.id)"
          >
            {{ t.label }}
            <span
              v-if="t.id === 'configuracoes'"
              class="material-symbols-outlined text-base transition-transform"
              :class="activeMainTab === 'configuracoes' ? 'rotate-180' : ''"
            >
              expand_more
            </span>
          </button>
        </div>
        <div v-if="activeMainTab === 'configuracoes'" class="flex flex-wrap gap-x-6 gap-y-2 pt-3 pb-4 border-t border-outline-variant/10">
          <button
            v-for="t in configTabs"
            :key="t.id"
            type="button"
            class="text-sm transition-colors"
            :class="
              activeTab === t.id
                ? 'text-black font-semibold underline decoration-2 underline-offset-4'
                : 'text-on-surface-variant hover:text-black'
            "
            @click="setConfigTab(t.id)"
          >
            {{ t.label }}
          </button>
        </div>
      </div>
    </section>

    <!-- Conteúdo por aba -->
    <section class="px-0 sm:px-1 pb-20 space-y-6 w-full min-w-0 max-w-none">
      <!-- Resumo -->
      <div v-show="activeTab === 'resumo'" class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div class="lg:col-span-8 space-y-6">
          <div
            v-if="canMove"
            class="bg-surface-container-low border border-outline-variant/10 rounded-lg p-6 md:p-8 space-y-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h3 class="text-lg font-bold font-headline">Dados do processo</h3>
              <button
                v-if="!editingProcess"
                type="button"
                class="text-sm font-semibold text-primary hover:opacity-90 font-body"
                @click="editingProcess = true"
              >
                Editar
              </button>
              <div v-else class="flex flex-wrap gap-2">
                <button
                  type="button"
                  class="text-sm font-medium text-on-surface-variant hover:text-on-surface font-body"
                  :disabled="savingProcess"
                  @click="cancelEditProcess"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  form="form-dados-processo"
                  class="text-sm font-semibold text-primary hover:opacity-90 font-body disabled:opacity-50"
                  :disabled="savingProcess"
                >
                  {{ savingProcess ? "Salvando…" : "Salvar" }}
                </button>
              </div>
            </div>
            <p class="text-xs text-on-surface-variant font-body">
              Nome, responsável, diretoria, metodologia, previsões e encerramento. O fluxo Kanban (template e coluna atual) não é alterado aqui.
            </p>
            <dl v-if="!editingProcess" class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm font-body">
              <div>
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Nome</dt>
                <dd class="mt-1 text-on-surface">{{ project.name }}</dd>
              </div>
              <div>
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Líder / PO</dt>
                <dd class="mt-1 text-on-surface">{{ project.product_owner }}</dd>
              </div>
              <div>
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Diretoria</dt>
                <dd class="mt-1 text-on-surface">{{ project.directory_name ?? "—" }}</dd>
              </div>
              <div>
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Metodologia</dt>
                <dd class="mt-1 text-on-surface">{{ methodologyLabel(project.methodology) }}</dd>
              </div>
              <div>
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Previsão início</dt>
                <dd class="mt-1 text-on-surface">{{ formatHeroDate(project.planned_start) }}</dd>
              </div>
              <div>
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Previsão entrega</dt>
                <dd class="mt-1 text-on-surface">{{ formatHeroDate(project.planned_end) }}</dd>
              </div>
              <div class="sm:col-span-2">
                <dt class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Encerrado em</dt>
                <dd class="mt-1 text-on-surface">{{ project.ended_at ? formatHeroDate(project.ended_at) : "— (ativo)" }}</dd>
              </div>
            </dl>
            <form
              v-else
              id="form-dados-processo"
              class="grid grid-cols-1 sm:grid-cols-2 gap-4"
              @submit.prevent="saveProcess"
            >
              <label class="block text-sm font-body sm:col-span-2">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Nome</span>
                <input
                  v-model="editDraft.name"
                  required
                  class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-container font-body"
                />
              </label>
              <label class="block text-sm font-body">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Líder / PO</span>
                <input
                  v-model="editDraft.product_owner"
                  required
                  class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-container font-body"
                />
              </label>
              <label class="block text-sm font-body">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Diretoria</span>
                <select
                  v-model.number="editDraft.directory_id"
                  required
                  class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body"
                >
                  <option v-for="dir in directories" :key="dir.id" :value="dir.id">{{ dir.name }}</option>
                </select>
              </label>
              <label class="block text-sm font-body">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Metodologia</span>
                <select v-model="editDraft.methodology" class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body">
                  <option value="prd">PRD</option>
                  <option value="base44">Base 44</option>
                </select>
              </label>
              <label class="block text-sm font-body">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Previsão início</span>
                <input
                  v-model="editDraft.planned_start"
                  type="date"
                  required
                  class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body"
                />
              </label>
              <label class="block text-sm font-body">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Previsão entrega</span>
                <input
                  v-model="editDraft.planned_end"
                  type="date"
                  required
                  class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body"
                />
              </label>
              <label class="block text-sm font-body sm:col-span-2">
                <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Encerrado em (opcional)</span>
                <input
                  v-model="editDraft.ended_at"
                  type="date"
                  class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body"
                />
                <span class="mt-1 block text-[0.65rem] text-on-surface-variant">Deixe em branco para manter ou reabrir o processo (sem data de encerramento).</span>
              </label>
            </form>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-surface-container-lowest p-6 rounded-lg shadow-sm border border-outline-variant/10">
              <div class="flex justify-between items-start mb-8">
                <div class="p-2 bg-primary-container rounded-md">
                  <span class="material-symbols-outlined text-primary-fixed">policy</span>
                </div>
                <span class="text-[10px] font-bold text-on-tertiary-container px-2 py-1 bg-tertiary-container/10 rounded uppercase font-label"
                  >Check do sistema</span
                >
              </div>
              <h3 class="text-xl font-bold font-headline mb-2">Alinhamento de governança</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed mb-6 font-body">
                Metodologia {{ methodologyLabel(project.methodology) }} · Diretoria {{ project.directory_name ?? "—" }} · Coluna Kanban:
                <strong class="text-on-surface">{{ project.current_column_title ?? "—" }}</strong>.
              </p>
              <div class="w-full bg-surface-container rounded-full h-1.5 mb-2">
                <div class="bg-tertiary-fixed-dim h-1.5 rounded-full transition-all" :style="{ width: `${governanceProgress}%` }" />
              </div>
              <div class="flex justify-between text-[10px] font-bold text-on-surface-variant uppercase font-label">
                <span>{{ governanceProgress }}% maturidade</span>
                <span v-if="project.github_tag">Ref: {{ project.github_tag }}</span>
                <span v-else>Sem ref GitHub</span>
              </div>
            </div>
            <div class="bg-primary-container p-6 rounded-lg text-white relative overflow-hidden min-h-[200px]">
              <div class="relative z-10">
                <div class="flex justify-between items-start mb-8">
                  <div class="p-2 bg-white/10 rounded-md">
                    <span class="material-symbols-outlined text-tertiary-fixed">auto_awesome</span>
                  </div>
                </div>
                <h3 class="text-xl font-bold font-headline mb-2">Recomendação</h3>
                <p class="text-sm text-primary-fixed/80 leading-relaxed font-body">
                  Gere a Wiki a partir da pasta <code class="text-tertiary-fixed/90">docs/</code> após vincular o repositório e escolher uma tag
                  válida. Use o separador Wiki para acompanhar o processamento.
                </p>
                <button
                  type="button"
                  class="mt-8 text-xs font-bold text-tertiary-fixed border-b border-tertiary-fixed pb-0.5 hover:text-white hover:border-white transition-all uppercase font-label"
                  @click="activeTab = 'wiki'"
                >
                  Abrir Wiki
                </button>
              </div>
              <div class="absolute inset-0 bg-gradient-to-br from-primary-container to-black/40 opacity-50 pointer-events-none" />
            </div>
          </div>

          <div class="bg-surface-container-low p-8 rounded-lg">
            <h3 class="text-sm font-bold uppercase tracking-widest text-on-surface-variant mb-6 font-label">Integrações ativas</h3>
            <div class="space-y-4">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-surface-container-lowest rounded-md">
                <div class="flex items-center gap-4 min-w-0">
                  <div class="h-10 w-10 bg-surface-container-high rounded flex items-center justify-center shrink-0">
                    <span class="material-symbols-outlined">terminal</span>
                  </div>
                  <div class="min-w-0">
                    <h4 class="text-sm font-bold font-body">Repositório principal</h4>
                    <p class="text-xs text-on-surface-variant truncate font-body">{{ repoDisplayPath(project.github_repo_url) }}</p>
                  </div>
                </div>
                <div class="flex items-center gap-4 shrink-0">
                  <span class="text-xs font-mono text-on-tertiary-container bg-tertiary-container px-2 py-0.5 rounded-full">{{
                    project.github_tag ?? "—"
                  }}</span>
                  <a
                    v-if="project.github_repo_url"
                    :href="project.github_repo_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="material-symbols-outlined text-outline text-lg hover:text-primary"
                    >open_in_new</a
                  >
                </div>
              </div>
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-surface-container-lowest rounded-md">
                <div class="flex items-center gap-4 min-w-0">
                  <div class="h-10 w-10 bg-surface-container-high rounded flex items-center justify-center shrink-0">
                    <span class="material-symbols-outlined">data_object</span>
                  </div>
                  <div class="min-w-0">
                    <h4 class="text-sm font-bold font-body">Contexto Cursor Hub</h4>
                    <p class="text-xs text-on-surface-variant font-body">Regras e artefatos publicados — SysGen AI</p>
                  </div>
                </div>
                <div class="flex items-center gap-4 shrink-0">
                  <button
                    type="button"
                    class="text-xs font-mono text-on-secondary-container bg-secondary-container px-2 py-0.5 rounded-full"
                    @click="activeTab = 'cursor'"
                  >
                    Gerir
                  </button>
                  <span class="material-symbols-outlined text-outline text-lg">sync</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="lg:col-span-4 bg-surface-container-low p-8 rounded-lg h-fit">
          <div class="flex items-center justify-between mb-8">
            <h3 class="text-sm font-bold uppercase tracking-widest text-on-surface-variant font-label">Fluxo de atividade</h3>
            <RouterLink
              v-if="canSeeAudit"
              to="/auditoria"
              class="material-symbols-outlined text-outline hover:text-primary text-lg"
              title="Auditoria global"
              >open_in_new</RouterLink
            >
          </div>
          <div v-if="!auditFeed.length" class="text-sm text-on-surface-variant font-body py-4">
            Nenhum evento de auditoria para este projeto{{
              canSeeAudit ? "." : " (visível para administradores e coordenadores)."
            }}
          </div>
          <div v-else class="space-y-8 relative">
            <div class="absolute left-[11px] top-2 bottom-2 w-0.5 bg-outline-variant/20" />
            <div v-for="a in auditFeed" :key="a.id" class="relative pl-10">
              <div
                class="absolute left-0 top-1.5 h-6 w-6 rounded-full bg-surface-container-lowest flex items-center justify-center shadow-sm border border-outline-variant/10"
              >
                <span class="material-symbols-outlined text-xs">{{ auditIcon(a.action) }}</span>
              </div>
              <p class="text-xs font-bold text-on-surface font-body">{{ auditTitle(a.action) }}</p>
              <p class="text-xs text-on-surface-variant mt-1 leading-relaxed font-body">
                {{ a.detail || a.actor_email }}
              </p>
              <span class="text-[10px] text-outline font-medium block mt-2 uppercase font-label">{{ relTime(a.created_at) }}</span>
            </div>
          </div>
          <RouterLink
            v-if="canSeeAudit"
            to="/auditoria"
            class="w-full mt-10 py-3 text-xs font-bold text-on-surface-variant hover:text-black border border-outline-variant/30 rounded-md transition-all uppercase text-center block font-label"
          >
            Ver registro completo
          </RouterLink>
        </div>
      </div>

      <!-- Desenvolvimento (quadro de tarefas; id interno: kanban) -->
      <div v-show="activeTab === 'kanban'" class="w-full min-w-0 max-w-none space-y-6">
        <div v-if="err || msg" class="space-y-2">
          <p v-if="msg" class="text-on-tertiary-container text-sm font-body">{{ msg }}</p>
          <p v-else-if="err" class="text-error text-sm font-body">{{ err }}</p>
        </div>
        <ProjectTaskBoard
          ref="projectTaskBoardRef"
          :project-id="project.id"
          :project-name="project.name"
          :can-mutate="canMove"
        />
      </div>

      <!-- PRD — chat ocupa o espaço útil até à coluna de versões (sem max-width que afaste o ledger) -->
      <div
        v-show="activeTab === 'prd'"
        class="flex w-full min-w-0 max-w-none flex-col gap-8 xl:flex-row xl:items-start xl:justify-start xl:gap-5 2xl:gap-6"
      >
        <div class="flex min-w-0 w-full flex-1 flex-col gap-6">
          <PrdChatPanel
            v-if="project"
            :project-id="project.id"
            :prd-tab-active="activeTab === 'prd'"
            @prd-saved="onPrdChatSaved"
          />
        </div>
        <div
          v-if="project"
          class="w-full min-w-0 xl:w-[400px] xl:shrink-0 xl:sticky xl:top-28 xl:self-start"
        >
          <PrdVersionsPanel
            ref="prdVersionsPanelRef"
            :project-id="project.id"
            :tab-active="activeTab === 'prd'"
            @prd-saved="onPrdMarkdownSaved"
          />
        </div>
      </div>

      <!-- Protótipo (layout alinhado a stitch_gest_o_governan_a_projetos_ia (2) — Sovereign Ledger) -->
      <div
        v-show="activeTab === 'prototipo'"
        class="flex w-full min-w-0 max-w-none flex-col gap-8 xl:flex-row xl:items-start xl:justify-start xl:gap-5 2xl:gap-6"
      >
        <div class="flex min-w-0 w-full flex-1 flex-col gap-6">
        <section>
          <header class="flex flex-col gap-1">
            <h2 class="font-headline text-2xl font-extrabold tracking-tight text-on-surface md:text-3xl">Protótipo</h2>
            <p class="font-body text-sm font-medium text-on-surface-variant">
              <strong class="text-on-surface font-semibold">Versões do prompt</strong> ao lado; gere a partir do último PRD e
              use a API Stitch ou o export MinIO após aprovar.
            </p>
          </header>
        </section>

        <!-- Cartões: Gerar prompt → API Stitch → Aprovar MinIO -->
        <section>
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-6">
            <button
              v-if="canEditPrototipoPrompt"
              type="button"
              class="flex flex-col items-start p-6 bg-surface-container-low rounded-xl hover:bg-surface-container-high transition-all border border-transparent hover:border-outline-variant/30 text-left group disabled:opacity-50"
              :disabled="prototipoGenerating || !project"
              title="Gera o prompt de protótipo a partir do último PRD guardado"
              @click="generatePrototipoPrompt"
            >
              <span class="material-symbols-outlined text-primary mb-3 text-3xl" aria-hidden="true">psychology</span>
              <span class="font-bold text-on-surface font-body">Gerar prompt (último PRD)</span>
              <span class="text-xs text-on-surface-variant mt-1 font-body"
                >Cria a última versão a partir do PRD; edite depois no painel ao lado.</span
              >
            </button>
            <template v-if="canEditPrototipoPrompt">
              <button
                v-if="prototipoPrompt.trim().length > 0"
                type="button"
                class="flex flex-col items-start p-6 rounded-xl text-left transition-all border border-transparent"
                :class="
                  stitchApiReady && !stitchApiGenerating && !prototipoGenerating
                    ? 'bg-surface-container-low hover:bg-surface-container-high hover:border-outline-variant/30 group'
                    : 'bg-surface-container-low opacity-60 cursor-not-allowed'
                "
                :disabled="!stitchApiReady || stitchApiGenerating || prototipoGenerating"
                :title="stitchApiDetail || 'API MCP Stitch no backend'"
                @click="generateStitchApiScreen"
              >
                <span
                  class="material-symbols-outlined mb-3 text-3xl"
                  :class="stitchApiReady ? 'text-primary' : 'text-on-surface-variant'"
                  aria-hidden="true"
                  >auto_awesome</span
                >
                <span class="font-bold font-body" :class="stitchApiReady ? 'text-on-surface' : 'text-on-surface-variant'"
                  >Gerar ecrã (API Stitch)</span
                >
                <span class="text-xs mt-1 font-body" :class="stitchApiReady ? 'text-on-surface-variant' : 'italic text-on-surface-variant'">
                  {{
                    stitchApiReady
                      ? "Gera ecrã no projeto Stitch a partir deste prompt."
                      : stitchApiDetail || "API indisponível no servidor."
                  }}
                </span>
              </button>
              <button
                v-else
                type="button"
                disabled
                class="flex flex-col items-start p-6 bg-surface-container-low rounded-xl opacity-60 cursor-not-allowed text-left"
              >
                <span class="material-symbols-outlined text-on-surface-variant mb-3 text-3xl" aria-hidden="true">auto_awesome</span>
                <span class="font-bold text-on-surface-variant font-body">Gerar ecrã (API Stitch)</span>
                <span class="text-xs text-on-surface-variant mt-1 italic font-body"
                  >É necessário um prompt na última versão (cartão «Gerar prompt» ou painel ao lado).</span
                >
              </button>
              <button
                v-if="canEditPrototipoPrompt && stitchApiResult && stitchApiReady"
                type="button"
                class="flex flex-col items-start p-6 bg-surface-container-low rounded-xl hover:bg-surface-container-high transition-all border border-transparent hover:border-outline-variant/30 text-left group disabled:opacity-50"
                :disabled="stitchApproveExporting || stitchApiGenerating || prototipoGenerating"
                title="Marca como aprovado e grava os ecrãs no MinIO"
                @click="approveAndSaveStitchToMinio"
              >
                <span class="material-symbols-outlined text-primary mb-3 text-3xl" aria-hidden="true">cloud_upload</span>
                <span class="font-bold text-on-surface font-body">{{
                  stitchApproveExporting ? "A gravar…" : "Aprovar e gravar no MinIO"
                }}</span>
                <span class="text-xs text-on-surface-variant mt-1 font-body"
                  >Grava o export no bucket após gerar o ecrã por API.</span
                >
              </button>
              <button
                v-else-if="canEditPrototipoPrompt"
                type="button"
                disabled
                class="flex flex-col items-start p-6 bg-surface-container-low rounded-xl opacity-60 cursor-not-allowed text-left"
              >
                <span class="material-symbols-outlined text-on-surface-variant mb-3 text-3xl" aria-hidden="true">cloud_upload</span>
                <span class="font-bold text-on-surface-variant font-body">Aprovar e gravar no MinIO</span>
                <span class="text-xs text-on-surface-variant mt-1 italic font-body"
                  >Gere um ecrã com «Gerar ecrã (API Stitch)» antes de aprovar.</span
                >
              </button>
            </template>
          </div>

          <p v-if="prototipoPromptMsg" class="mt-4 text-sm text-on-tertiary-container font-body">{{ prototipoPromptMsg }}</p>
          <p v-if="prototipoPromptErr" class="mt-4 text-sm text-error font-body">{{ prototipoPromptErr }}</p>

          <!-- Resultado API Stitch -->
          <div
            v-if="stitchApiResult"
            class="mt-8 md:mt-10 bg-surface-container-lowest rounded-xl p-6 md:p-8 border border-outline-variant/10 shadow-sm relative overflow-hidden"
          >
            <div v-if="stitchApiResult.approved_at" class="absolute top-0 right-0 p-4">
              <span
                class="inline-flex items-center px-3 py-1 bg-tertiary-container text-on-tertiary-container text-[11px] font-bold uppercase tracking-wider rounded-full font-label"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-on-tertiary-container mr-2" aria-hidden="true" />
                Aprovado
              </span>
            </div>
            <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant font-label mb-6 md:mb-8">
              Resultado API Stitch
            </p>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div class="space-y-4">
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase font-label tracking-wider"
                    >Projecto Stitch</label
                  >
                  <p class="font-bold text-on-surface font-body break-all">{{ stitchApiResult.stitch_project_id }}</p>
                </div>
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase font-label tracking-wider"
                    >Protótipo</label
                  >
                  <p class="font-bold text-on-surface font-body break-all">{{ stitchApiResult.screen_id }}</p>
                </div>
              </div>
              <div class="space-y-4">
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase font-label tracking-wider"
                    >Entregas</label
                  >
                  <div class="flex flex-wrap items-baseline gap-4">
                    <a
                      :href="`https://stitch.withgoogle.com/projects/${encodeURIComponent(stitchApiResult.stitch_project_id)}`"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-sm font-semibold text-primary underline underline-offset-4 hover:opacity-70 transition-opacity font-body"
                    >
                      Stitch
                    </a>
                    <button
                      type="button"
                      class="text-sm font-semibold text-primary underline underline-offset-4 hover:opacity-70 transition-opacity font-body"
                      @click="openStitchDeliveriesHtmlModal"
                    >
                      Ver HTML
                    </button>
                    <button
                      type="button"
                      class="text-sm font-semibold text-primary underline underline-offset-4 hover:opacity-70 transition-opacity font-body"
                      @click="openStitchDeliveriesImageModal"
                    >
                      Ver imagem
                    </button>
                  </div>
                </div>
                <div v-if="stitchApiResult.approved_at" class="space-y-1">
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase font-label tracking-wider"
                    >Metadados</label
                  >
                  <p class="text-xs text-on-surface-variant font-body">
                    Aprovado
                    {{ new Date(stitchApiResult.approved_at).toLocaleString("pt-PT") }}
                    <template v-if="stitchApiResult.approved_by_email">
                      por <span class="font-medium text-on-surface">{{ stitchApiResult.approved_by_email }}</span>
                    </template>
                  </p>
                </div>
              </div>
              <div
                v-if="stitchApiResult.export_storage_prefix"
                class="bg-surface-container-low rounded-lg p-4 self-start"
              >
                <label class="text-[10px] font-bold text-on-surface-variant uppercase font-label tracking-wider block mb-2"
                  >Caminho MinIO</label
                >
                <code class="font-mono text-xs text-secondary leading-relaxed break-all">{{ stitchApiResult.export_storage_prefix }}</code>
              </div>
            </div>
          </div>
        </section>
        </div>
        <div
          v-if="project"
          class="w-full min-w-0 xl:w-[400px] xl:shrink-0 xl:sticky xl:top-28 xl:self-start"
        >
          <PrototipoVersionsPanel
            ref="prototipoVersionsPanelRef"
            :project-id="project.id"
            :tab-active="activeTab === 'prototipo'"
            @prototipo-saved="onPrototipoVersionSavedFromPanel"
          />
        </div>
      </div>

      <!-- Planejamento — largura útil como PRD/Protótipo (sem max-width) -->
      <div
        v-show="activeTab === 'planejamento'"
        class="w-full min-w-0 max-w-none bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4"
      >
        <h3 class="text-lg font-bold font-headline">Planejamento</h3>
        <p class="text-sm text-on-surface-variant leading-relaxed font-body">
          Área para cronogramas, marcos, capacidade e dependências entre equipas. Use esta secção para alinhar entregas com o PRD e o protótipo.
        </p>
        <div v-if="project?.planejamento_json_saved_at || project?.planejamento_json_approved_at" class="text-xs text-on-surface font-body pt-1 space-y-1">
          <p v-if="project?.planejamento_json_saved_at">
            Último planejamento guardado:
            <time class="font-medium" :datetime="project.planejamento_json_saved_at">{{
              formatAuditDateTime(project.planejamento_json_saved_at)
            }}</time>
          </p>
          <p
            v-if="project?.planejamento_json_approved_at"
            class="text-emerald-800 dark:text-emerald-200 font-semibold"
          >
            Aprovado em
            <time :datetime="project.planejamento_json_approved_at">{{
              formatAuditDateTime(project.planejamento_json_approved_at)
            }}</time>
          </p>
        </div>
        <div
          v-if="planejamentoContext"
          class="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4 md:p-5 space-y-3"
        >
          <h4 class="text-sm font-bold font-headline text-on-surface">Stack e configuração do ambiente</h4>
          <p class="text-sm leading-relaxed text-on-surface-variant font-body">
            {{ planejamentoContext.stack_documentada }}
          </p>
          <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-xs font-body">
            <div class="sm:col-span-2">
              <dt class="font-label uppercase tracking-wider text-on-surface-variant">Metodologia do projecto</dt>
              <dd class="mt-0.5 text-on-surface font-medium">
                {{ planejamentoMethodologyLabel(planejamentoContext.methodology) }}
              </dd>
            </div>
            <div v-if="planejamentoContext.github_repo_url" class="sm:col-span-2">
              <dt class="font-label uppercase tracking-wider text-on-surface-variant">Repositório GitHub</dt>
              <dd class="mt-0.5 break-all text-on-surface">
                <a
                  :href="planejamentoContext.github_repo_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-primary underline font-medium"
                  >{{ planejamentoContext.github_repo_url }}</a
                >
                <span v-if="planejamentoContext.github_tag" class="text-on-surface-variant">
                  · tag <code class="text-[11px] bg-surface-container-low px-1 rounded">{{ planejamentoContext.github_tag }}</code>
                </span>
              </dd>
            </div>
            <div>
              <dt class="font-label uppercase tracking-wider text-on-surface-variant">MinIO / S3 (export)</dt>
              <dd class="mt-0.5 text-on-surface">{{ planejamentoSimNao(planejamentoContext.s3_configured) }}</dd>
            </div>
            <div>
              <dt class="font-label uppercase tracking-wider text-on-surface-variant">OAuth GitHub (servidor)</dt>
              <dd class="mt-0.5 text-on-surface">{{ planejamentoSimNao(planejamentoContext.github_oauth_configured) }}</dd>
            </div>
            <div>
              <dt class="font-label uppercase tracking-wider text-on-surface-variant">API Stitch (STITCH_API_KEY)</dt>
              <dd class="mt-0.5 text-on-surface">{{ planejamentoSimNao(planejamentoContext.stitch_api_configured) }}</dd>
            </div>
            <div>
              <dt class="font-label uppercase tracking-wider text-on-surface-variant">Agente Azure planejador</dt>
              <dd class="mt-0.5 text-on-surface">{{ planejamentoSimNao(planejamentoContext.azure_planejador_ready) }}</dd>
            </div>
          </dl>
        </div>
        <div v-if="canEditPrototipoPrompt" class="space-y-3 pt-2">
          <button
            type="button"
            class="px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold font-body disabled:opacity-50 disabled:pointer-events-none"
            :disabled="planejamentoAgentLoading || !project"
            @click="runPlanejamentoAzureAgent"
          >
            {{ planejamentoAgentLoading ? "A contactar o agente…" : "Gerar planejamento técnico (Azure)" }}
          </button>
          <p class="text-xs text-on-surface-variant font-body">
            Envia o PRD guardado (Markdown) e do último export no MinIO apenas ficheiros HTML e PNG ao agente
            configurado em <code class="text-[11px]">AZURE_AI_AGENT_PLANEJADOR_ID</code>. O resultado é
            <span class="font-semibold text-on-surface">gravado na base</span> — ao reabrir o projeto o JSON
            carrega automaticamente; use o botão só para regenerar. O JSON inclui
            <span class="font-semibold text-on-surface">preparacao</span> (ambiente, arquitetura, Cursor) antes das
            <span class="font-semibold text-on-surface">fases</span> de entrega.
          </p>
          <p v-if="planejamentoAgentErr" class="text-sm text-error font-body">{{ planejamentoAgentErr }}</p>
          <ul
            v-if="planejamentoAgentWarnings.length"
            class="text-xs text-on-surface-variant font-body list-disc pl-5 space-y-1"
          >
            <li v-for="(w, i) in planejamentoAgentWarnings" :key="i">{{ w }}</li>
          </ul>
        </div>
        <div v-if="planejamentoAgentOutput" class="space-y-3 pt-2">
            <h4 class="text-sm font-bold font-headline">Resultado</h4>
            <div v-if="planejamentoTreeRows.length" class="space-y-3">
              <PlanejamentoRoadmapView
                :parsed="planejamentoAgentParsed"
                :tree-rows="planejamentoTreeRows"
                :expanded="planejamentoExpanded"
                :selected-path-key="planejamentoSelectedPathKey"
                :detail-json="planejamentoSelectedDetailJson"
                @select="selectPlanejamentoPathKey"
                @toggle-expand="togglePlanejamentoExpand"
                @close-detail="clearPlanejamentoSelection"
              />
              <div
                v-if="canEditPrototipoPrompt && planejamentoAgentOutput"
                class="flex flex-wrap gap-2 pt-1 border-t border-outline-variant/10"
              >
                <button
                  type="button"
                  class="px-3 py-2 rounded-md text-sm font-semibold font-body bg-emerald-700 text-white hover:opacity-90 disabled:opacity-50"
                  :disabled="planejamentoApprovalLoading || !!project?.planejamento_json_approved_at"
                  @click="setPlanejamentoApproval(true)"
                >
                  Aprovar planejamento
                </button>
                <button
                  type="button"
                  class="px-3 py-2 rounded-md text-sm font-semibold font-body border border-outline-variant/30 hover:bg-surface-container-high disabled:opacity-50"
                  :disabled="planejamentoApprovalLoading || !project?.planejamento_json_approved_at"
                  @click="setPlanejamentoApproval(false)"
                >
                  Anular aprovação
                </button>
              </div>
              <p
                v-if="planejamentoApprovalMsg"
                class="text-sm text-emerald-800 dark:text-emerald-200 font-body pt-1"
              >
                {{ planejamentoApprovalMsg }}
              </p>
            </div>
            <p
              v-else-if="planejamentoIsEmptyStructured"
              class="text-sm text-on-surface-variant font-body"
            >
              O JSON devolvido está vazio (objeto sem chaves ou array sem itens).
            </p>
            <div v-else class="space-y-2">
              <p class="text-xs text-on-surface-variant font-body">
                Resposta sem lista navegável (valor JSON primitivo ou texto); conteúdo:
              </p>
              <pre
                class="text-xs font-mono bg-surface-container-lowest text-on-surface rounded-lg border border-outline-variant/15 p-4 max-h-[28rem] overflow-auto whitespace-pre-wrap break-words"
              >{{ planejamentoAgentOutput }}</pre>
            </div>
        </div>
      </div>

      <!-- GitHub -->
      <div v-show="activeTab === 'github'" class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-4xl">
        <h3 class="text-lg font-bold font-headline">GitHub</h3>
        <p class="text-xs text-on-surface-variant font-body">
          Use «Sincronizar com GitHub» para ligar a sua conta (se ainda não ligou) e atualizar as tags do repositório num único passo.
        </p>
        <div class="flex gap-2 flex-wrap items-center">
          <button
            type="button"
            class="px-4 py-2 bg-secondary text-on-secondary rounded-md text-sm font-semibold font-body disabled:opacity-50 disabled:pointer-events-none"
            :disabled="!ghOAuthConfigured"
            @click="syncWithGitHub"
          >
            Sincronizar com GitHub
          </button>
          <span v-if="!ghOAuthConfigured" class="text-xs text-on-surface-variant font-body">OAuth GitHub indisponível neste ambiente.</span>
        </div>
        <div class="flex gap-2 flex-wrap">
          <input
            id="governance-repo-url"
            v-model="repoUrl"
            class="flex-1 min-w-[200px] rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-transparent focus:ring-2 focus:ring-primary-container font-body scroll-mt-24"
            placeholder="https://github.com/org/repo"
          />
          <button type="button" class="px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold font-body" @click="saveGithub">
            Vincular
          </button>
          <button type="button" class="px-4 py-2 bg-surface-container-high rounded-md text-sm font-body" @click="loadTags">Tags API</button>
        </div>
        <div v-if="tags.length" class="flex flex-wrap gap-2">
          <button
            v-for="t in tags"
            :key="t"
            type="button"
            class="text-xs px-3 py-1.5 rounded-full bg-surface-container-lowest border border-outline-variant/15 font-body hover:bg-surface-container-high"
            @click="pickTag(t)"
          >
            {{ t }}
          </button>
        </div>
        <div class="flex gap-2 items-center flex-wrap">
          <input
            id="governance-github-tag"
            v-model="customRef"
            class="flex-1 min-w-[120px] rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body scroll-mt-24"
            placeholder="Outra tag ou branch (ref)"
          />
          <button type="button" class="px-4 py-2 bg-surface-container-high rounded-md text-sm font-body" @click="applyCustomRef">
            Aplicar ref
          </button>
        </div>
        <p class="text-xs text-on-surface-variant font-body">Ref selecionada: <strong class="text-on-surface">{{ project.github_tag ?? "—" }}</strong></p>
      </div>

      <!-- Wiki -->
      <div v-show="activeTab === 'wiki'" class="space-y-4">
        <div class="flex flex-wrap items-center gap-3">
          <button type="button" class="text-sm px-4 py-2 bg-secondary text-on-secondary rounded-md font-semibold font-body" @click="genWiki">
            Gerar Wiki (pasta docs/)
          </button>
          <span v-if="wiki?.status === 'pending'" class="text-sm text-on-surface-variant font-body">Processando no worker…</span>
        </div>
        <div class="bg-surface-container-low rounded-lg p-6 md:p-8">
          <h3 class="text-lg font-bold font-headline mb-2">Wiki</h3>
          <p v-if="wiki?.status === 'error'" class="text-sm text-error mb-2 font-body">{{ wiki.error_message }}</p>
          <div v-if="wiki && wiki.documents?.length" class="prose prose-sm max-w-none font-body space-y-4">
            <div v-for="(d, i) in wiki.documents" :key="i" class="bg-surface-container-lowest rounded-lg p-4 border border-outline-variant/10">
              <p class="text-xs text-on-surface-variant font-mono">{{ d.path }}</p>
              <h4 class="font-headline font-semibold mt-1">{{ d.title }}</h4>
              <pre class="whitespace-pre-wrap text-sm mt-2 text-on-surface">{{ d.markdown }}</pre>
            </div>
          </div>
          <p v-else-if="!wiki?.documents?.length" class="text-sm text-on-surface-variant font-body">{{ wiki?.detail ?? "Nenhuma Wiki ainda." }}</p>
        </div>
      </div>

      <!-- Anexos -->
      <div id="governance-anexos" v-show="activeTab === 'anexos'" class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-4xl scroll-mt-24">
        <h3 class="text-lg font-bold font-headline">Anexos</h3>
        <p class="text-xs text-on-surface-variant font-body">
          Upload para MinIO/S3 quando configurado; senão grava em <code class="bg-surface-container-lowest px-1 rounded">local_storage/</code>.
        </p>
        <div class="flex flex-wrap gap-2 items-center">
          <input
            v-model="attachType"
            class="w-40 rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none font-body"
            placeholder="tipo"
          />
          <input ref="fileEl" type="file" class="text-sm font-body" />
          <button type="button" class="px-4 py-2 bg-surface-container-high rounded-md text-sm font-body" @click="uploadAttachment">
            Enviar
          </button>
        </div>
      </div>

      <!-- Cursor Hub -->
      <div v-show="activeTab === 'cursor'" class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-2xl">
        <h3 class="text-lg font-bold font-headline">Cursor Hub</h3>
        <p class="text-sm text-on-surface-variant leading-relaxed font-body">
          Publique artefatos (regras, skills, MCP) e vincule-os a este projeto na área central do Cursor Hub.
        </p>
        <RouterLink
          to="/cursor-hub"
          class="inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold hover:opacity-90 font-body"
        >
          Abrir Cursor Hub
          <span class="material-symbols-outlined text-base">arrow_forward</span>
        </RouterLink>
      </div>

      <!-- Auditoria -->
      <div v-show="activeTab === 'auditoria'" class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-2xl">
        <h3 class="text-lg font-bold font-headline">Auditoria</h3>
        <p class="text-sm text-on-surface-variant font-body">
          O registro completo de eventos está na área de auditoria. Os itens do painel ao lado listam apenas eventos deste projeto.
        </p>
        <RouterLink
          v-if="canSeeAudit"
          to="/auditoria"
          class="inline-flex items-center gap-2 px-4 py-2 bg-surface-container-high text-on-surface rounded-md text-sm font-semibold hover:bg-surface-variant font-body"
        >
          Ir para auditoria
        </RouterLink>
        <p v-else class="text-sm text-on-surface-variant font-body">Disponível para administradores e coordenadores.</p>
      </div>

      <template v-if="activeTab !== 'kanban'">
        <p v-if="msg" class="text-on-tertiary-container text-sm font-body">{{ msg }}</p>
        <p v-else-if="err" class="text-error text-sm font-body">{{ err }}</p>
      </template>
    </section>

    <!-- Galeria Entregas: PNG — vista minimalista (só conteúdo + barra fina) -->
    <div
      v-if="showStitchDeliveriesImageModal"
      class="fixed inset-0 z-[80] flex items-center justify-center p-2 bg-black/75 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="stitch-gallery-img-title"
      @click.self="closeStitchDeliveriesImageModal"
    >
      <div
        class="flex flex-col w-full max-w-[min(100vw-1rem,1200px)] h-[min(96svh,900px)] bg-zinc-950 rounded-md overflow-hidden border border-zinc-800 shadow-2xl"
        @click.stop
      >
        <div class="flex items-center gap-2 px-3 py-2 shrink-0 border-b border-zinc-800">
          <h3 id="stitch-gallery-img-title" class="text-sm font-semibold text-zinc-100 truncate min-w-0">
            PNG
            <span class="text-zinc-500 font-normal"
              >· {{ stitchImgCarouselIndex + 1 }}/{{ stitchImgRels.length || 1 }}</span
            >
          </h3>
          <p
            class="hidden sm:block text-[11px] text-zinc-500 font-mono truncate flex-1 min-w-0"
            :title="stitchImgSlideLabel(stitchImgCarouselIndex)"
          >
            {{ stitchImgSlideLabel(stitchImgCarouselIndex) }}
          </p>
          <button
            type="button"
            class="p-1.5 rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 shrink-0"
            aria-label="Fechar"
            @click="closeStitchDeliveriesImageModal"
          >
            <span class="material-symbols-outlined text-[22px]" aria-hidden="true">close</span>
          </button>
        </div>
        <p v-if="stitchGalleryImgErr" class="px-3 py-1 text-xs text-red-400 font-body border-b border-zinc-800">{{ stitchGalleryImgErr }}</p>
        <div
          class="relative flex-1 min-h-0 flex items-center justify-center bg-black p-1"
          :aria-busy="stitchGalleryImgLoading"
        >
          <div
            v-if="stitchGalleryImgLoading && !stitchImgSrc[stitchImgCarouselIndex]"
            class="flex flex-col items-center justify-center gap-2 text-zinc-500"
          >
            <span class="material-symbols-outlined text-3xl text-zinc-600 animate-pulse" aria-hidden="true">image</span>
            <span class="text-xs font-body">A carregar…</span>
          </div>
          <img
            v-else-if="stitchImgSrc[stitchImgCarouselIndex]"
            :src="stitchImgSrc[stitchImgCarouselIndex]"
            :alt="stitchImgSlideLabel(stitchImgCarouselIndex)"
            class="max-h-full max-w-full w-auto h-auto object-contain"
          />
          <button
            type="button"
            class="absolute left-1 top-1/2 -translate-y-1/2 p-1.5 rounded-md bg-zinc-900/90 text-zinc-300 hover:bg-zinc-800 disabled:opacity-25"
            :disabled="stitchImgCarouselIndex <= 0 || stitchGalleryImgLoading"
            aria-label="Anterior"
            @click="stitchImgCarouselPrev"
          >
            <span class="material-symbols-outlined text-[22px]" aria-hidden="true">chevron_left</span>
          </button>
          <button
            type="button"
            class="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 rounded-md bg-zinc-900/90 text-zinc-300 hover:bg-zinc-800 disabled:opacity-25"
            :disabled="stitchImgCarouselIndex >= stitchImgRels.length - 1 || stitchGalleryImgLoading"
            aria-label="Seguinte"
            @click="stitchImgCarouselNext"
          >
            <span class="material-symbols-outlined text-[22px]" aria-hidden="true">chevron_right</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Galeria Entregas: HTML — vista minimalista -->
    <div
      v-if="showStitchDeliveriesHtmlModal"
      class="fixed inset-0 z-[80] flex items-center justify-center p-2 bg-black/75 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="stitch-gallery-html-title"
      @click.self="closeStitchDeliveriesHtmlModal"
    >
      <div
        class="flex flex-col w-full max-w-[min(100vw-1rem,1400px)] h-[min(96svh,920px)] bg-zinc-950 rounded-md overflow-hidden border border-zinc-800 shadow-2xl"
        @click.stop
      >
        <div class="flex items-center gap-2 px-3 py-2 shrink-0 border-b border-zinc-800">
          <h3 id="stitch-gallery-html-title" class="text-sm font-semibold text-zinc-100 truncate min-w-0">
            HTML
            <span class="text-zinc-500 font-normal"
              >· {{ stitchHtmlCarouselIndex + 1 }}/{{ stitchHtmlRels.length || 1 }}</span
            >
          </h3>
          <p
            class="hidden sm:block text-[11px] text-zinc-500 font-mono truncate flex-1 min-w-0"
            :title="stitchHtmlSlideLabel(stitchHtmlCarouselIndex)"
          >
            {{ stitchHtmlSlideLabel(stitchHtmlCarouselIndex) }}
          </p>
          <button
            type="button"
            class="p-1.5 rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 shrink-0"
            aria-label="Fechar"
            @click="closeStitchDeliveriesHtmlModal"
          >
            <span class="material-symbols-outlined text-[22px]" aria-hidden="true">close</span>
          </button>
        </div>
        <p v-if="stitchGalleryHtmlErr" class="px-3 py-1 text-xs text-red-400 font-body border-b border-zinc-800">{{ stitchGalleryHtmlErr }}</p>
        <div class="relative flex-1 min-h-0 flex flex-col bg-black" :aria-busy="stitchGalleryHtmlLoading">
          <div
            v-if="stitchGalleryHtmlLoading && !stitchHtmlSrc[stitchHtmlCarouselIndex]"
            class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-zinc-500 z-10 bg-zinc-950/80"
          >
            <span class="material-symbols-outlined text-3xl text-zinc-600 animate-pulse" aria-hidden="true">html</span>
            <span class="text-xs font-body">A carregar…</span>
          </div>
          <iframe
            v-if="stitchHtmlSrc[stitchHtmlCarouselIndex]"
            :src="stitchHtmlSrc[stitchHtmlCarouselIndex]"
            :title="stitchHtmlSlideLabel(stitchHtmlCarouselIndex)"
            class="w-full flex-1 min-h-0 border-0 bg-white"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          />
          <button
            type="button"
            class="absolute left-1 top-1/2 -translate-y-1/2 p-1.5 rounded-md bg-zinc-900/90 text-zinc-300 hover:bg-zinc-800 disabled:opacity-25 z-20"
            :disabled="stitchHtmlCarouselIndex <= 0 || stitchGalleryHtmlLoading"
            aria-label="Anterior"
            @click="stitchHtmlCarouselPrev"
          >
            <span class="material-symbols-outlined text-[22px]" aria-hidden="true">chevron_left</span>
          </button>
          <button
            type="button"
            class="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 rounded-md bg-zinc-900/90 text-zinc-300 hover:bg-zinc-800 disabled:opacity-25 z-20"
            :disabled="stitchHtmlCarouselIndex >= stitchHtmlRels.length - 1 || stitchGalleryHtmlLoading"
            aria-label="Seguinte"
            @click="stitchHtmlCarouselNext"
          >
            <span class="material-symbols-outlined text-[22px]" aria-hidden="true">chevron_right</span>
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showDeleteModal"
      class="fixed inset-0 bg-primary-container/70 backdrop-blur-sm z-[70] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="bg-surface-container-lowest max-w-md w-full rounded-xl p-8 shadow-2xl text-center border border-outline-variant/10">
        <div class="w-16 h-16 bg-error-container rounded-full flex items-center justify-center mx-auto mb-6">
          <span class="material-symbols-outlined text-error text-3xl" style="font-variation-settings: 'FILL' 1">warning</span>
        </div>
        <h3 class="text-xl font-headline font-extrabold text-on-surface mb-2">Excluir este projeto?</h3>
        <p class="text-sm text-on-surface-variant mb-2 font-body">
          <strong class="text-on-surface">{{ project.name }}</strong> e os dados associados (anexos, wiki, vínculos Cursor) serão removidos de forma
          permanente.
        </p>
        <div class="grid grid-cols-2 gap-4 mt-8">
          <button
            type="button"
            class="bg-surface-container-high text-on-surface font-bold py-3 rounded-md hover:bg-surface-container-highest transition-colors font-body"
            :disabled="deleting"
            @click="showDeleteModal = false"
          >
            Cancelar
          </button>
          <button
            type="button"
            class="bg-error text-on-error font-bold py-3 rounded-md hover:opacity-90 transition-colors font-body disabled:opacity-50"
            :disabled="deleting"
            @click="confirmDeleteProject"
          >
            {{ deleting ? "A excluir…" : "Sim, excluir" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
