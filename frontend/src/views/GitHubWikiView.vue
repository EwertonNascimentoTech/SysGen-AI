<script setup lang="ts">
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import { marked, type Token, type Tokens } from "marked";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { hasLinkedGithubRepo, parseGithubRepoDisplaySlug } from "@/utils/githubRepo";
import { wikiDocumentDisplayName } from "@/utils/wikiDocDisplayName";

type Project = {
  id: number;
  name: string;
  github_repo_url: string | null;
  github_tag: string | null;
};

type WikiDoc = { path: string; title: string; markdown: string; kind?: "markdown" | "bpmn-xml" };

type WikiResp = {
  wiki_id?: number;
  tag?: string | null;
  status?: string | null;
  error_message?: string | null;
  wiki_created_at?: string | null;
  detail?: string;
  documents?: WikiDoc[];
};

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const projects = ref<Project[]>([]);
const projectsLoaded = ref(false);
const selectedId = ref<number | null>(null);

const routeProjectId = computed(() => {
  const raw = route.params.projectId;
  if (raw == null || Array.isArray(raw)) return null;
  const n = Number(String(raw));
  return Number.isFinite(n) && n > 0 ? n : null;
});
const wiki = ref<WikiResp | null>(null);
const err = ref("");
const msg = ref("");
const treeSearch = ref("");
/** Pastas (caminho de apresentação sem docs/) recolhidas na árvore */
const collapsedDirPaths = ref<Set<string>>(new Set());
const selectedPath = ref<string | null>(null);
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null);
const bpmnEl = ref<HTMLElement | null>(null);
const bpmnErr = ref("");
const wikiMarkdownHostRef = ref<HTMLElement | null>(null);
/** Após navegar para outro .md, rolar até o id gerado a partir deste fragmento (#âncora). */
const pendingWikiHash = ref<string | null>(null);
let bpmnViewer: NavigatedViewer | null = null;
let bpmnResizeRo: ResizeObserver | null = null;

const wikiHeadingSlugCounts = new Map<string, number>();

function wikiHeadingSlug(text: string): string {
  const n = text.normalize("NFD").replace(/\p{M}/gu, "");
  const s = n
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return s || "secao";
}

function allocWikiHeadingId(plainTitle: string): string {
  const base = wikiHeadingSlug(plainTitle);
  const c = wikiHeadingSlugCounts.get(base) ?? 0;
  wikiHeadingSlugCounts.set(base, c + 1);
  if (c === 0) return base;
  return `${base}-${c}`;
}

function escapeHtmlAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

marked.use({
  renderer: {
    heading(this: { parser: { parseInline: (t: Token[]) => string } }, { tokens, depth, text }: Tokens.Heading) {
      const id = allocWikiHeadingId(text);
      const body = this.parser.parseInline(tokens);
      return `<h${depth} id="${escapeHtmlAttr(id)}">${body}</h${depth}>\n`;
    },
  },
});

function docKind(d: WikiDoc | null): "markdown" | "bpmn-xml" {
  if (!d) return "markdown";
  if (d.kind === "bpmn-xml") return "bpmn-xml";
  if (d.kind === "markdown") return "markdown";
  return d.path.toLowerCase().endsWith(".xml") ? "bpmn-xml" : "markdown";
}

function destroyBpmn() {
  if (bpmnResizeRo) {
    bpmnResizeRo.disconnect();
    bpmnResizeRo = null;
  }
  if (bpmnViewer) {
    bpmnViewer.destroy();
    bpmnViewer = null;
  }
}

function zoomBpmnFit() {
  if (!bpmnViewer) return;
  try {
    const canvas = bpmnViewer.get("canvas") as { zoom: (level: string) => void };
    canvas.zoom("fit-viewport");
  } catch {
    /* ignore */
  }
}

async function renderBpmn() {
  bpmnErr.value = "";
  const d = selectedDoc.value;
  if (!d || docKind(d) !== "bpmn-xml") {
    destroyBpmn();
    return;
  }
  const xml = d.markdown;
  await nextTick();
  if (!bpmnEl.value) {
    await nextTick();
  }
  if (!bpmnEl.value) return;
  destroyBpmn();
  try {
    bpmnViewer = new NavigatedViewer({ container: bpmnEl.value });
    const { warnings } = await bpmnViewer.importXML(xml);
    if (warnings?.length) console.warn(warnings);
    zoomBpmnFit();
    requestAnimationFrame(() => zoomBpmnFit());
    if (typeof ResizeObserver !== "undefined") {
      bpmnResizeRo = new ResizeObserver(() => zoomBpmnFit());
      bpmnResizeRo.observe(bpmnEl.value);
    }
  } catch (e) {
    destroyBpmn();
    bpmnErr.value = e instanceof Error ? e.message : "Não foi possível interpretar o diagrama BPMN 2.0.";
  }
}

const canGenerate = computed(() => auth.hasRole("admin", "coordenador"));

const projectsWithRepo = computed(() => projects.value.filter(hasLinkedGithubRepo));

const selectedProject = computed(() => projects.value.find((p) => p.id === selectedId.value) ?? null);

/** Secções de topo em docs/ — README por pasta (nomes no repo: processo, tecnico/técnico, usuario/usuário). */
const WIKI_SECTION_CONFIG = [
  { id: "processo", label: "Processos", folderFolds: ["processo"] },
  { id: "tecnico", label: "Técnicos", folderFolds: ["tecnico"] },
  { id: "usuario", label: "Usuários", folderFolds: ["usuario", "usuário"] },
] as const;

function foldKey(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase();
}

/** Rótulos na UI para as três áreas principais (pastas no Git podem ter grafia diferente). */
function wikiFolderDisplayLabel(folderName: string): string {
  const fk = foldKey(folderName);
  if (fk === foldKey("processo")) return "Processos";
  if (fk === foldKey("tecnico")) return "Técnicos";
  if (fk === foldKey("usuario")) return "Usuários";
  return folderName;
}

function stripDocsRoot(path: string): string {
  return path.replace(/\\/g, "/").replace(/^docs\//i, "");
}

/** Resolve caminho relativo à raiz da doc (sem docs/) para o path real na API. */
function repoPathFromDisplayRelative(rel: string): string | null {
  const docs = wiki.value?.documents ?? [];
  const norm = rel.replace(/\\/g, "/");
  const low = norm.toLowerCase();
  const hit = docs.find((d) => stripDocsRoot(d.path).toLowerCase() === low);
  return hit?.path ?? null;
}

function findSectionReadmePath(docs: WikiDoc[], folderFolds: string[]): string | null {
  const wanted = new Set(folderFolds.map((f) => foldKey(f)));
  for (const d of docs) {
    const rel = stripDocsRoot(d.path);
    const parts = rel.split("/").filter(Boolean);
    if (parts.length !== 2) continue;
    if (parts[1].toLowerCase() !== "readme.md") continue;
    if (wanted.has(foldKey(parts[0]))) return d.path;
  }
  return null;
}

function defaultReadmePathFromDocs(docs: WikiDoc[]): string | null {
  for (const c of WIKI_SECTION_CONFIG) {
    const p = findSectionReadmePath(docs, [...c.folderFolds]);
    if (p) return p;
  }
  return null;
}

type TreeNode = {
  type: "dir" | "file";
  name: string;
  /** Caminho lógico sem prefixo docs/ */
  displayPath: string;
  docPath?: string;
  doc?: WikiDoc;
  children?: TreeNode[];
};

function pathParts(path: string) {
  return path.split("/").filter(Boolean);
}

/** README da pasta (nome do ficheiro no Git). */
function isWikiReadmeFileName(fileName: string): boolean {
  return fileName.toLowerCase() === "readme.md";
}

function wikiTreeFileLabel(node: TreeNode): string {
  if (node.type !== "file") return node.name;
  if (isWikiReadmeFileName(node.name)) return "Principal";
  return wikiDocumentDisplayName(node.name);
}

function buildWikiDocTree(docs: WikiDoc[]): TreeNode[] {
  const root: TreeNode[] = [];
  for (const doc of docs) {
    const parts = pathParts(stripDocsRoot(doc.path));
    let level = root;
    let acc = "";
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i];
      const isLast = i === parts.length - 1;
      acc = acc ? `${acc}/${name}` : name;
      const nl = name.toLowerCase();
      if (isLast && (nl.endsWith(".md") || nl.endsWith(".xml"))) {
        level.push({ type: "file", name, displayPath: acc, docPath: doc.path, doc });
        break;
      }
      let dir = level.find((n) => n.type === "dir" && n.name === name);
      if (!dir) {
        dir = { type: "dir", name, displayPath: acc, children: [] };
        level.push(dir);
      }
      if (!dir.children) dir.children = [];
      level = dir.children;
    }
  }

  /** Em cada pasta: README.md primeiro; depois subpastas; depois restantes ficheiros. */
  function sortKey(n: TreeNode): [number, string] {
    if (n.type === "file" && isWikiReadmeFileName(n.name)) return [0, ""];
    if (n.type === "dir") return [1, n.name.toLowerCase()];
    return [2, n.name.toLowerCase()];
  }

  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      const ka = sortKey(a);
      const kb = sortKey(b);
      if (ka[0] !== kb[0]) return ka[0] - kb[0];
      return ka[1].localeCompare(kb[1], "pt-BR");
    });
    for (const n of nodes) if (n.children?.length) sortNodes(n.children);
  };
  sortNodes(root);
  return root;
}

function filterWikiDocs(docs: WikiDoc[], q: string): WikiDoc[] {
  const s = q.trim().toLowerCase();
  if (!s) return docs;
  return docs.filter(
    (d) => stripDocsRoot(d.path).toLowerCase().includes(s) || d.title.toLowerCase().includes(s),
  );
}

const filteredWikiDocs = computed(() => filterWikiDocs(wiki.value?.documents ?? [], treeSearch.value));

const docTree = computed(() => buildWikiDocTree(filteredWikiDocs.value));

type FlatRow = { node: TreeNode; depth: number };
const flatTree = computed((): FlatRow[] => {
  const out: FlatRow[] = [];
  function walk(nodes: TreeNode[], depth: number) {
    for (const n of nodes) {
      out.push({ node: n, depth });
      if (n.type === "dir" && n.children?.length && !collapsedDirPaths.value.has(n.displayPath)) {
        walk(n.children, depth + 1);
      }
    }
  }
  walk(docTree.value, 0);
  return out;
});

function toggleDirCollapse(displayPath: string) {
  const next = new Set(collapsedDirPaths.value);
  if (next.has(displayPath)) next.delete(displayPath);
  else next.add(displayPath);
  collapsedDirPaths.value = next;
}

function isDirCollapsed(displayPath: string): boolean {
  return collapsedDirPaths.value.has(displayPath);
}

function selectTreeFile(node: TreeNode) {
  if (node.type === "file" && node.docPath) selectedPath.value = node.docPath;
}

const selectedDoc = computed(() => {
  const p = selectedPath.value;
  if (!p || !wiki.value?.documents) return null;
  return wiki.value.documents.find((d) => d.path === p) ?? null;
});

const renderedHtml = computed(() => {
  const d = selectedDoc.value;
  if (!d || docKind(d) === "bpmn-xml") return "";
  const md = d.markdown ?? "";
  if (!md) return "";
  try {
    wikiHeadingSlugCounts.clear();
    return marked.parse(md, { async: false }) as string;
  } catch {
    return `<pre class="text-sm whitespace-pre-wrap">${escapeHtml(md)}</pre>`;
  }
});

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function normalizePathParts(parts: string[]): string {
  const stack: string[] = [];
  for (const p of parts) {
    if (!p || p === ".") continue;
    if (p === "..") stack.pop();
    else stack.push(p);
  }
  return stack.join("/");
}

/** Caminho de documento na wiki que existe na lista atual (preserva capitalização do repo). */
function findExistingDocPath(resolved: string): string | null {
  const docs = wiki.value?.documents ?? [];
  if (docs.some((d) => d.path === resolved)) return resolved;
  const rlow = resolved.toLowerCase();
  const hit = docs.find((d) => d.path.toLowerCase() === rlow);
  return hit?.path ?? null;
}

/** Breadcrumb sem prefixo docs/: pasta → README; ficheiro → doc. */
function breadcrumbTargetForIndex(parts: string[], index: number, docs: WikiDoc[]): string | null {
  if (!docs.length || index < 0 || index >= parts.length) return null;
  const sub = parts.slice(0, index + 1);
  const last = sub[sub.length - 1]!;
  const joined = sub.join("/");

  if (last.toLowerCase().endsWith(".md") || last.toLowerCase().endsWith(".xml")) {
    return repoPathFromDisplayRelative(joined);
  }

  const viaReadme = repoPathFromDisplayRelative(`${joined}/README.md`);
  if (viaReadme) return viaReadme;

  if (index === 0 && parts.length === 1) return defaultReadmePathFromDocs(docs);
  return null;
}

type WikiLinkTarget = { docPath: string | null; hash: string | null };

function parseHrefPathAndHash(href: string): { pathPart: string; hash: string | null } {
  const raw = href.trim();
  const i = raw.indexOf("#");
  if (i === -1) return { pathPart: raw, hash: null };
  const after = raw.slice(i + 1);
  const hash = after.length ? decodeURIComponent(after.replace(/\+/g, " ")) : null;
  return { pathPart: raw.slice(0, i).trim(), hash };
}

/**
 * Resolve href de Markdown: outro ficheiro em docs/, âncora no mesmo doc (#secao) ou ambos.
 * Suporta caminhos relativos e URLs blob do GitHub.
 */
function resolveWikiNavHref(baseDocPath: string, href: string): WikiLinkTarget | null {
  const { pathPart, hash } = parseHrefPathAndHash(href);
  if (!pathPart) {
    if (hash) return { docPath: null, hash };
    return null;
  }

  let pathOnly = pathPart;
  if (/^[a-z][a-z0-9+.-]*:/i.test(pathOnly)) {
    const ghBlob = pathOnly.match(/github\.com\/[^/]+\/[^/]+\/blob\/[^/]+\/(.+)/i);
    if (ghBlob?.[1]) pathOnly = decodeURIComponent(ghBlob[1].split(/[?#]/)[0] ?? "");
    else return null;
  }

  pathOnly = pathOnly.replace(/^\.\//, "");
  if (!pathOnly) return hash ? { docPath: null, hash } : null;

  let resolved: string;
  if (pathOnly.startsWith("/")) {
    resolved = normalizePathParts(pathOnly.replace(/^\//, "").split("/").filter(Boolean));
  } else {
    const baseDir = baseDocPath.includes("/") ? baseDocPath.slice(0, baseDocPath.lastIndexOf("/")) : "";
    const joined = baseDir ? `${baseDir}/${pathOnly}` : pathOnly;
    resolved = normalizePathParts(joined.split("/").filter(Boolean));
  }

  let found = findExistingDocPath(resolved);
  if (!found) {
    const low = resolved.toLowerCase();
    if (!low.endsWith(".md") && !low.endsWith(".xml")) {
      found = findExistingDocPath(`${resolved}.md`);
    }
  }

  if (!found) return null;
  return { docPath: found, hash };
}

function findWikiAnchorEl(root: HTMLElement, rawFragment: string): HTMLElement | null {
  const decoded = rawFragment.trim();
  if (!decoded) return null;
  const candidates = [decoded, wikiHeadingSlug(decoded)];
  for (const id of candidates) {
    if (!id) continue;
    try {
      const el = root.querySelector(`#${CSS.escape(id)}`);
      if (el) return el as HTMLElement;
    } catch {
      /* id inválido para selector */
    }
  }
  return null;
}

function scrollWikiToAnchor(rawFragment: string) {
  void nextTick(() => {
    void nextTick(() => {
      const root = wikiMarkdownHostRef.value;
      if (!root) return;
      findWikiAnchorEl(root, rawFragment)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function onWikiMarkdownClick(ev: MouseEvent) {
  const el = ev.target as HTMLElement | null;
  const a = el?.closest("a");
  const href = a?.getAttribute("href");
  if (!href || !a) return;

  const base = selectedDoc.value?.path;
  if (!base || docKind(selectedDoc.value) !== "markdown") return;

  const target = resolveWikiNavHref(base, href);
  if (!target) return;

  if (target.docPath === null && target.hash) {
    ev.preventDefault();
    scrollWikiToAnchor(target.hash);
    return;
  }

  if (target.docPath) {
    ev.preventDefault();
    if (target.docPath === base && target.hash) {
      scrollWikiToAnchor(target.hash);
      return;
    }
    pendingWikiHash.value = target.hash ?? null;
    selectedPath.value = target.docPath;
  }
}

const syncBadge = computed(() => {
  const st = wiki.value?.status;
  if (st === "ready") return { label: "SINCRONIZADO", cls: "bg-tertiary-container/10 text-on-tertiary-container" };
  if (st === "pending") return { label: "PROCESSANDO", cls: "bg-secondary-container text-on-secondary-container" };
  if (st === "error") return { label: "ERRO", cls: "bg-error-container text-error" };
  return { label: "SEM WIKI", cls: "bg-surface-container-highest text-on-surface-variant" };
});

const lastSyncLabel = computed(() => {
  const raw = wiki.value?.wiki_created_at;
  if (!raw) return "—";
  try {
    return new Date(raw).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return raw;
  }
});

const breadcrumbParts = computed(() => {
  const d = selectedDoc.value;
  if (!d) return [] as string[];
  return pathParts(stripDocsRoot(d.path));
});

const breadcrumbNavEntries = computed(() => {
  const parts = breadcrumbParts.value;
  const docs = wiki.value?.documents ?? [];
  if (!parts.length) return [] as { part: string; displayPart: string; target: string | null; isLast: boolean }[];
  return parts.map((part, i) => {
    const isLast = i === parts.length - 1;
    const isFile = /\.(md|xml)$/i.test(part);
    return {
      part,
      displayPart: isFile
        ? isWikiReadmeFileName(part)
          ? "Principal"
          : wikiDocumentDisplayName(part)
        : wikiFolderDisplayLabel(part),
      target: breadcrumbTargetForIndex(parts, i, docs),
      isLast,
    };
  });
});

function onBreadcrumbRootClick() {
  const docs = wiki.value?.documents ?? [];
  if (!docs.length) return;
  if (docKind(selectedDoc.value) === "bpmn-xml") {
    const rel = stripDocsRoot(selectedDoc.value?.path ?? "");
    const first = rel.split("/")[0];
    let dest: string | null = null;
    if (first) {
      const fk = foldKey(first);
      for (const c of WIKI_SECTION_CONFIG) {
        if (c.folderFolds.some((f) => foldKey(f) === fk)) {
          dest = findSectionReadmePath(docs, [...c.folderFolds]);
          break;
        }
      }
    }
    if (!dest) dest = defaultReadmePathFromDocs(docs);
    if (dest) selectedPath.value = dest;
    return;
  }
  const dest = defaultReadmePathFromDocs(docs);
  if (dest) selectedPath.value = dest;
}

function onBreadcrumbSegmentClick(target: string | null) {
  if (target) selectedPath.value = target;
}

async function loadProjects() {
  err.value = "";
  projectsLoaded.value = false;
  try {
    projects.value = await api<Project[]>("/projects");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  } finally {
    projectsLoaded.value = true;
  }
}

watch(
  [projectsWithRepo, routeProjectId, projectsLoaded, err],
  ([list, rid, loaded]) => {
    if (rid == null) {
      void router.replace({ name: "wiki" });
      return;
    }
    if (!loaded) return;
    if (err.value) return;
    if (!list.some((p) => p.id === rid)) {
      void router.replace({ name: "wiki" });
      return;
    }
    if (selectedId.value !== rid) selectedId.value = rid;
  },
  { immediate: true },
);

async function refreshWiki() {
  if (selectedId.value == null) {
    wiki.value = null;
    return;
  }
  try {
    wiki.value = await api<WikiResp>(`/projects/${selectedId.value}/wiki`);
    const docs = wiki.value.documents ?? [];
    const fallback = defaultReadmePathFromDocs(docs) ?? docs[0]?.path ?? null;
    if (docs.length && selectedPath.value == null) selectedPath.value = fallback;
    if (selectedPath.value && !docs.some((d) => d.path === selectedPath.value)) {
      selectedPath.value = fallback;
    }
  } catch {
    wiki.value = null;
  }
}

function stopPoll() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value);
    pollTimer.value = null;
  }
}

function startPoll() {
  stopPoll();
  pollTimer.value = setInterval(async () => {
    await refreshWiki();
    if (wiki.value?.status !== "pending") stopPoll();
  }, 2500);
}

watch(selectedId, async () => {
  selectedPath.value = null;
  treeSearch.value = "";
  collapsedDirPaths.value = new Set();
  await refreshWiki();
  if (wiki.value?.status === "pending") startPoll();
});

function expandAncestorsForPath(repoPath: string | null) {
  if (!repoPath) return;
  const parts = pathParts(stripDocsRoot(repoPath));
  if (parts.length <= 1) return;
  const next = new Set(collapsedDirPaths.value);
  let acc = "";
  for (let i = 0; i < parts.length - 1; i++) {
    acc = acc ? `${acc}/${parts[i]}` : parts[i]!;
    next.delete(acc);
  }
  collapsedDirPaths.value = next;
}

watch(
  () => selectedPath.value,
  (p) => expandAncestorsForPath(p),
);

watch(
  () => treeSearch.value,
  (q) => {
    const s = q.trim();
    if (!s) return;
    const next = new Set(collapsedDirPaths.value);
    for (const d of filteredWikiDocs.value) {
      const parts = pathParts(stripDocsRoot(d.path));
      let acc = "";
      for (let i = 0; i < parts.length - 1; i++) {
        acc = acc ? `${acc}/${parts[i]}` : parts[i]!;
        next.delete(acc);
      }
    }
    collapsedDirPaths.value = next;
  },
);

watch(
  () => wiki.value?.status,
  (st) => {
    if (st === "pending") startPoll();
    else stopPoll();
  },
);

watch(
  () => [selectedPath.value, selectedDoc.value?.markdown, selectedDoc.value?.path, wiki.value?.wiki_id] as const,
  () => {
    void renderBpmn();
  },
  { flush: "post" },
);

watch(
  () => [selectedPath.value, renderedHtml.value] as const,
  async () => {
    const h = pendingWikiHash.value;
    if (h === null || h === "") return;
    await nextTick();
    await nextTick();
    const root = wikiMarkdownHostRef.value;
    if (root) findWikiAnchorEl(root, h)?.scrollIntoView({ behavior: "smooth", block: "start" });
    pendingWikiHash.value = null;
  },
  { flush: "post" },
);

onMounted(() => {
  void loadProjects();
});

onUnmounted(() => {
  stopPoll();
  destroyBpmn();
});

async function forceRegenerate() {
  if (selectedId.value == null || !canGenerate.value) return;
  err.value = "";
  msg.value = "";
  try {
    await api(`/projects/${selectedId.value}/wiki/generate`, { method: "POST" });
    msg.value = "Geração da Wiki solicitada (pull da pasta docs/ no ref atual).";
    await refreshWiki();
    if (wiki.value?.status === "pending") startPoll();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

function commitPlaceholder() {
  window.alert("Commit de alterações para o GitHub: funcionalidade planeada (RF futuro).");
}
</script>

<template>
  <div class="-mx-2 md:-mx-4 flex flex-col flex-1 min-h-[calc(100vh-6rem)]">
    <section class="shrink-0 px-2 md:px-6 lg:px-10 py-6 border-b border-outline-variant/10 bg-surface">
      <div class="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div class="space-y-3">
          <div class="flex flex-wrap items-center gap-3">
            <div class="w-8 h-8 bg-primary rounded flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined text-on-primary text-lg">menu_book</span>
            </div>
            <h2 class="font-headline font-bold text-2xl tracking-tight text-on-surface">
              {{ parseGithubRepoDisplaySlug(selectedProject?.github_repo_url ?? null) }}
            </h2>
            <span
              class="px-3 py-1 rounded-full text-[10px] font-bold flex items-center gap-1 font-label"
              :class="syncBadge.cls"
            >
              <span class="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
              {{ syncBadge.label }}
            </span>
          </div>
          <div class="flex flex-wrap gap-6 items-center">
            <div class="flex flex-col">
              <span class="text-[10px] uppercase font-bold text-outline tracking-wider font-label">Projeto</span>
              <span class="text-sm font-medium text-on-surface font-body">{{ selectedProject?.name ?? "—" }}</span>
            </div>
            <div class="w-px h-8 bg-outline-variant/20 hidden sm:block" />
            <div class="flex flex-col min-w-[8rem]">
              <span class="text-[10px] uppercase font-bold text-outline tracking-wider font-label">Tag / ref</span>
              <span class="text-sm font-medium font-mono text-secondary">{{ selectedProject?.github_tag ?? "—" }}</span>
            </div>
            <div class="w-px h-8 bg-outline-variant/20 hidden sm:block" />
            <div class="flex flex-col">
              <span class="text-[10px] uppercase font-bold text-outline tracking-wider font-label">Última sincronização</span>
              <span class="text-sm font-medium text-on-surface font-body">{{ lastSyncLabel }}</span>
            </div>
          </div>
          <div class="max-w-md flex flex-col gap-1">
            <span class="text-[10px] uppercase font-bold text-outline tracking-wider font-label">Navegação</span>
            <RouterLink
              :to="{ name: 'wiki' }"
              class="inline-flex items-center gap-2 text-sm font-semibold text-primary font-body hover:underline w-fit"
            >
              <span class="material-symbols-outlined text-base" aria-hidden="true">arrow_back</span>
              Lista de projetos (Wiki Explorer)
            </RouterLink>
          </div>
        </div>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="bg-surface-container-high px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 hover:bg-surface-container-highest transition-colors font-body disabled:opacity-50"
            :disabled="!selectedId || !canGenerate"
            @click="forceRegenerate"
          >
            <span class="material-symbols-outlined text-lg">sync</span>
            Forçar pull (regenerar Wiki)
          </button>
          <button
            type="button"
            class="bg-primary text-on-primary px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 font-body opacity-60 cursor-not-allowed"
            disabled
            title="Em breve"
            @click="commitPlaceholder"
          >
            <span class="material-symbols-outlined text-lg">edit_note</span>
            Commitar alterações
          </button>
        </div>
      </div>
      <p v-if="msg" class="text-sm text-on-tertiary-container mt-3 font-body">{{ msg }}</p>
      <p v-if="err" class="text-sm text-error mt-3 font-body">{{ err }}</p>
      <p v-if="wiki?.status === 'error' && wiki.error_message" class="text-sm text-error mt-2 font-body">{{ wiki.error_message }}</p>
      <p v-if="selectedProject && !selectedProject.github_tag" class="text-sm text-on-surface-variant mt-3 font-body">
        Defina uma tag no
        <RouterLink :to="`/projetos/${selectedProject.id}`" class="text-primary font-semibold underline">detalhe do projeto</RouterLink>
        antes de gerar a Wiki.
      </p>
    </section>

    <div
      v-if="projects.length > 0 && !projectsWithRepo.length"
      class="px-6 md:px-10 py-16 text-center bg-surface-container-low rounded-xl border border-outline-variant/10 mx-2 md:mx-4"
    >
      <p class="text-on-surface-variant font-body max-w-md mx-auto">
        Nenhum projeto tem <strong class="text-on-surface">repositório GitHub</strong> vinculado. Abra um projeto e associe a URL do repo para
        visualizar a Wiki aqui.
      </p>
      <RouterLink to="/projetos" class="inline-block mt-4 text-primary font-semibold underline font-body">Ir à listagem de projetos</RouterLink>
    </div>

    <section
      v-else-if="projectsWithRepo.length && selectedId != null"
      class="flex flex-1 min-h-0 overflow-hidden border-b border-outline-variant/10"
    >
      <div class="w-72 shrink-0 bg-surface-container-low border-r border-outline-variant/10 overflow-y-auto px-4 py-6 min-h-0 self-stretch">
        <h3 class="text-[10px] uppercase font-extrabold text-outline tracking-[0.2em] mb-3 px-2 font-label">Árvore</h3>
        <p class="text-[10px] text-on-surface-variant px-2 mb-3 font-body leading-snug">
          Caminhos relativos a <strong class="text-on-surface">docs/</strong> (prefixo oculto). Áreas
          <strong class="text-on-surface">Processos</strong>, <strong class="text-on-surface">Técnicos</strong> e
          <strong class="text-on-surface">Usuários</strong> correspondem às pastas
          <span class="font-mono text-[10px]">processo</span>,
          <span class="font-mono text-[10px]">tecnico</span>/<span class="font-mono text-[10px]">técnico</span> e
          <span class="font-mono text-[10px]">usuario</span>/<span class="font-mono text-[10px]">usuário</span>.
        </p>
        <div class="relative mb-4">
          <span class="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg pointer-events-none"
            >search</span
          >
          <input
            v-model="treeSearch"
            type="search"
            class="w-full bg-surface-container-lowest border border-outline-variant/10 rounded-lg pl-9 pr-2 py-2 text-xs outline-none font-body focus:ring-1 focus:ring-primary/30"
            placeholder="Filtrar por nome ou caminho…"
            autocomplete="off"
            aria-label="Filtrar ficheiros da documentação"
          />
        </div>
        <ul v-if="flatTree.length" class="space-y-0.5">
          <li v-for="{ node, depth } in flatTree" :key="node.type === 'file' ? node.docPath : `dir:${node.displayPath}`">
            <button
              v-if="node.type === 'dir'"
              type="button"
              class="flex items-center gap-0.5 px-2 py-2 w-full text-left rounded-lg cursor-pointer transition-colors text-sm font-semibold font-body text-on-surface-variant hover:bg-surface-container-highest focus-visible:outline focus-visible:ring-2 focus-visible:ring-primary/30"
              :style="{ paddingLeft: `${4 + depth * 12}px` }"
              :aria-expanded="!isDirCollapsed(node.displayPath)"
              @click="toggleDirCollapse(node.displayPath)"
            >
              <span
                class="material-symbols-outlined text-base shrink-0 text-on-surface-variant transition-transform duration-150"
                :class="isDirCollapsed(node.displayPath) ? '' : 'rotate-90'"
                aria-hidden="true"
              >chevron_right</span>
              <span class="material-symbols-outlined text-lg shrink-0">folder_open</span>
              <span class="truncate">{{ wikiFolderDisplayLabel(node.name) }}</span>
            </button>
            <button
              v-else
              type="button"
              class="flex items-center gap-2 px-2 py-2 w-full text-left rounded-lg cursor-pointer transition-colors text-sm font-medium font-body focus-visible:outline focus-visible:ring-2 focus-visible:ring-primary/30"
              :class="
                selectedPath === node.docPath
                  ? 'bg-white shadow-sm border border-outline-variant/10 text-primary'
                  : 'text-on-surface-variant hover:bg-surface-container-highest border border-transparent'
              "
              :style="{ paddingLeft: `${8 + depth * 12}px` }"
              @click="selectTreeFile(node)"
            >
              <span
                class="material-symbols-outlined text-lg shrink-0"
                :class="selectedPath === node.docPath ? 'text-primary' : ''"
              >{{ node.name.toLowerCase().endsWith('.xml') ? 'account_tree' : 'description' }}</span>
              <span class="truncate" :title="`${wikiTreeFileLabel(node)} — ${node.displayPath}`">{{ wikiTreeFileLabel(node) }}</span>
            </button>
          </li>
        </ul>
        <p v-else class="text-xs text-on-surface-variant px-2 font-body leading-relaxed">
          {{ wiki?.detail ?? "Gere a Wiki a partir da pasta docs/ no repositório." }}
        </p>
        <div class="mt-8">
          <h3 class="text-[10px] uppercase font-extrabold text-outline tracking-[0.2em] mb-4 px-2 font-label">Insights</h3>
          <div class="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/10 space-y-4">
            <div>
              <div class="flex justify-between items-center mb-1">
                <span class="text-[10px] font-bold text-outline font-label">COBERTURA DOC</span>
                <span class="text-[10px] font-bold text-on-tertiary-container font-label">{{
                  wiki?.documents?.length ? Math.min(100, 70 + wiki.documents.length * 5) : 0
                }}%</span>
              </div>
              <div class="w-full h-1.5 bg-surface-container rounded-full overflow-hidden">
                <div
                  class="h-full bg-on-tertiary-container transition-all"
                  :style="{ width: (wiki?.documents?.length ? Math.min(100, 70 + wiki.documents.length * 5) : 0) + '%' }"
                />
              </div>
            </div>
            <p class="text-[11px] text-on-surface-variant leading-relaxed font-body">
              <strong class="text-on-surface">Processos</strong>, <strong class="text-on-surface">Técnicos</strong> e
              <strong class="text-on-surface">Usuários</strong> na árvore. Pastas
              <strong class="text-on-surface">expandidas ou recolhidas</strong>; a pesquisa revela resultados. Ficheiros
              <strong class="text-on-surface">.md</strong> e <strong class="text-on-surface">BPMN .xml</strong>. “Forçar pull” após alterações no Git.
            </p>
          </div>
        </div>
      </div>

      <div class="flex-1 min-w-0 min-h-0 bg-surface-container-lowest flex flex-col overflow-hidden">
        <div v-if="selectedDoc" class="flex flex-1 min-h-0 flex-col overflow-hidden px-4 md:px-8 lg:px-10 py-5 min-w-0">
          <nav
            class="flex flex-wrap items-center gap-x-2 gap-y-1 shrink-0 mb-4 text-on-surface-variant text-xs font-bold tracking-widest font-label"
            aria-label="Localização na documentação"
          >
            <button
              type="button"
              class="bg-transparent border-0 p-0 m-0 cursor-pointer text-inherit font-inherit tracking-widest rounded hover:text-primary hover:underline focus-visible:outline focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1"
              @click="onBreadcrumbRootClick"
            >
              {{ docKind(selectedDoc) === "bpmn-xml" ? "PROCESSO BPMN 2.0" : "DOCUMENTAÇÃO" }}
            </button>
            <template v-for="(row, i) in breadcrumbNavEntries" :key="i">
              <span class="flex items-center gap-2 min-w-0">
                <span class="material-symbols-outlined text-sm shrink-0" aria-hidden="true">chevron_right</span>
                <button
                  v-if="row.target"
                  type="button"
                  class="bg-transparent border-0 p-0 m-0 cursor-pointer text-left font-inherit tracking-widest truncate rounded min-w-0 hover:text-primary hover:underline focus-visible:outline focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1"
                  :class="row.isLast ? 'text-primary' : 'text-on-surface-variant'"
                  @click="onBreadcrumbSegmentClick(row.target)"
                >
                  {{ row.displayPart }}
                </button>
                <span v-else class="truncate min-w-0" :class="row.isLast ? 'text-primary' : ''">{{ row.displayPart }}</span>
              </span>
            </template>
          </nav>
          <div v-if="docKind(selectedDoc) === 'bpmn-xml'" class="flex flex-1 min-h-0 flex-col gap-2 min-w-0">
            <p v-if="bpmnErr" class="shrink-0 text-sm text-error font-body">{{ bpmnErr }}</p>
            <p v-else class="shrink-0 text-xs text-on-surface-variant font-body">
              Diagrama interativo (zoom e deslocar com o rato). XML válido BPMN 2.0.
            </p>
            <div
              ref="bpmnEl"
              class="bpmn-viewer-host flex-1 min-h-[24rem] w-full min-w-0 rounded-lg border border-outline-variant/15 bg-white overflow-hidden"
            />
          </div>
          <div
            v-else
            ref="wikiMarkdownHostRef"
            class="wiki-markdown-content font-body flex-1 min-h-0 overflow-auto max-w-[min(100%,56rem)] xl:max-w-[min(100%,72rem)] mx-auto w-full"
            @click.capture="onWikiMarkdownClick"
            v-html="renderedHtml"
          />
        </div>
        <div v-else class="flex-1 overflow-y-auto max-w-2xl mx-auto text-center text-on-surface-variant py-16 font-body px-6">
          <span class="material-symbols-outlined text-5xl text-outline-variant mb-4 block">menu_book</span>
          <p>Selecione um ficheiro na <strong class="text-on-surface">árvore</strong> à esquerda ou gere a Wiki no detalhe do projeto.</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.bpmn-viewer-host :deep(.djs-container) {
  height: 100% !important;
}
.bpmn-viewer-host :deep(.bjs-container) {
  height: 100% !important;
}
</style>
