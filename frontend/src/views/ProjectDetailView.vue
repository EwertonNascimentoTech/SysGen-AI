<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { api, ApiError, type GovernanceNoticePayload } from "@/api/client";
import ProjectTaskBoard from "@/components/ProjectTaskBoard.vue";
import { useAuthStore } from "@/stores/auth";

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
  | "desenvolvimento";

type MainTab = "resumo" | "kanban" | "anexos" | "auditoria" | "prd" | "prototipo" | "desenvolvimento" | "configuracoes";
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
const govFixLinks = ref<GovernanceNoticePayload[]>([]);
const govWarnLinks = ref<GovernanceNoticePayload[]>([]);
/** Movimentações macro Kanban (auditoria), ordenadas do mais antigo ao mais recente */
const kanbanMoveAudits = ref<AuditItem[]>([]);
const attachType = ref("evidencia");
const fileEl = ref<HTMLInputElement | null>(null);
const activeTab = ref<DetailTab>("resumo");
/** OAuth GitHub configurado no servidor (client id/secret). */
const ghOAuthConfigured = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;
const showDeleteModal = ref(false);
const deleting = ref(false);
/** Evita cliques repetidos enquanto o macro Kanban valida regras e grava o movimento. */
const movingKanbanToColumnId = ref<number | null>(null);
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

const ALL_DETAIL_TABS: DetailTab[] = [
  "resumo",
  "kanban",
  "prd",
  "prototipo",
  "desenvolvimento",
  "anexos",
  "auditoria",
  "github",
  "wiki",
  "cursor",
];

const allMainTabs = [
  { id: "resumo" as const, label: "Resumo" },
  { id: "kanban" as const, label: "Kanban" },
  { id: "prd" as const, label: "PRD" },
  { id: "prototipo" as const, label: "Protótipo" },
  { id: "desenvolvimento" as const, label: "Desenvolvimento" },
  { id: "anexos" as const, label: "Anexos" },
  { id: "auditoria" as const, label: "Auditoria" },
  { id: "configuracoes" as const, label: "Configurações" },
];

const allConfigTabs = [
  { id: "github" as const, label: "GitHub" },
  { id: "wiki" as const, label: "Wiki" },
  { id: "cursor" as const, label: "Cursor Hub" },
];

function applyTabFromRoute() {
  const raw = route.query.tab;
  const t = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : undefined;
  const allowed: DetailTab[] = [...ALL_DETAIL_TABS];
  if (t && (allowed as string[]).includes(t)) activeTab.value = t as typeof activeTab.value;
}

const visibleDetailTabs = computed<DetailTab[]>(() => {
  const currentColId = project.value?.current_column_id;
  if (!currentColId) return [...ALL_DETAIL_TABS];
  const col = templateCols.value.find((c) => c.id === currentColId);
  const raw = (col?.visible_detail_tabs ?? []).map((x) => String(x).toLowerCase()) as DetailTab[];
  const filtered = ALL_DETAIL_TABS.filter((k) => raw.includes(k));
  return filtered.length ? filtered : [...ALL_DETAIL_TABS];
});

const configTabs = computed(() => allConfigTabs.filter((t) => visibleDetailTabs.value.includes(t.id)));
const mainTabs = computed(() =>
  allMainTabs.filter((t) =>
    t.id === "configuracoes" ? configTabs.value.length > 0 : visibleDetailTabs.value.includes(t.id as DetailTab),
  ),
);

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

function parseKanbanAuditColumnTitle(detail: string | null): string | null {
  if (!detail || !detail.startsWith("coluna=")) return null;
  const t = detail.slice("coluna=".length).trim();
  return t || null;
}

async function loadKanbanTimelineAudits() {
  kanbanMoveAudits.value = [];
  if (!project.value || !canSeeAudit.value) return;
  try {
    const all = await api<AuditItem[]>("/audit");
    const pid = project.value.id;
    kanbanMoveAudits.value = all
      .filter((a) => a.entity_type === "project" && a.entity_id === pid && a.action === "project.kanban.move")
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  } catch {
    kanbanMoveAudits.value = [];
  }
}

const lastVisitByColumnTitle = computed(() => {
  const m = new Map<string, string>();
  for (const a of kanbanMoveAudits.value) {
    const title = parseKanbanAuditColumnTitle(a.detail);
    if (title) m.set(title, a.created_at);
  }
  return m;
});

type TimelinePhase = {
  col: Col;
  index: number;
  total: number;
  status: "completed" | "current" | "upcoming";
  visitedAt: string | null;
  detailPrimary: string;
  detailSecondary: string;
};

const timelinePhases = computed((): TimelinePhase[] => {
  const p = project.value;
  const cols = templateCols.value;
  if (!p || !cols.length) return [];
  const curId = p.current_column_id;
  const currentIdx = Math.max(
    0,
    cols.findIndex((c) => c.id === curId),
  );
  const visits = lastVisitByColumnTitle.value;
  const total = cols.length;

  return cols.map((c, i) => {
    let status: TimelinePhase["status"];
    if (i < currentIdx) status = "completed";
    else if (i === currentIdx) status = "current";
    else status = "upcoming";

    const visitedAt = visits.get(c.title) ?? null;
    let detailPrimary = "";
    let detailSecondary = "";
    if (status === "current") {
      detailPrimary = "Etapa atual do fluxo macro do projeto.";
      detailSecondary = visitedAt
        ? `Registo em auditoria: entrada nesta coluna em ${formatAuditDateTime(visitedAt)} (${relTime(visitedAt)}).`
        : "Sem registo de movimentação em auditoria (conta sem permissão ou histórico indisponível).";
      if (p.planned_end) {
        detailSecondary += ` Previsão de entrega do projeto: ${formatHeroDate(p.planned_end)}.`;
      }
    } else if (status === "completed") {
      detailPrimary = "Etapa já ultrapassada neste processo.";
      detailSecondary = visitedAt
        ? `Última movimentação registada para esta coluna: ${formatAuditDateTime(visitedAt)}.`
        : "Sem detalhe de data na auditoria para esta coluna.";
    } else {
      detailPrimary = "Etapa prevista após o avanço do Kanban macro.";
      detailSecondary = "Ainda não alcançada. Depende da conclusão das etapas anteriores e das regras de governança.";
    }

    return {
      col: c,
      index: i + 1,
      total,
      status,
      visitedAt,
      detailPrimary,
      detailSecondary,
    };
  });
});

const timelineGridStyle = computed(() => {
  const n = timelinePhases.value.length;
  if (!n) return {};
  return {
    gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`,
  };
});

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
  await loadKanbanTimelineAudits();
  applyTabFromRoute();
  scrollToRouteHash();
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

async function moveTo(colId: number) {
  if (!canMove.value || !project.value) return;
  if (movingKanbanToColumnId.value != null) return;
  const id = project.value.id;
  err.value = "";
  msg.value = "";
  govFixLinks.value = [];
  govWarnLinks.value = [];
  movingKanbanToColumnId.value = colId;
  try {
    const res = await api<{ project: Project; governance_warnings?: GovernanceNoticePayload[] }>(`/projects/${id}/kanban/move`, {
      method: "POST",
      body: JSON.stringify({ target_column_id: colId }),
    });
    project.value = res.project;
    const w = (res.governance_warnings ?? []).filter((x) => x?.message);
    govWarnLinks.value = w;
    msg.value = w.length ? "Coluna atualizada. Ver avisos de governança." : "Coluna atualizada.";
    await loadAuditFeed();
    await loadKanbanTimelineAudits();
  } catch (e) {
    if (e instanceof ApiError && e.governance?.length) {
      govFixLinks.value = e.governance;
      err.value = "";
    } else {
      err.value = e instanceof Error ? e.message : "Não foi possível mover.";
      govFixLinks.value = [];
    }
  } finally {
    movingKanbanToColumnId.value = null;
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

      <!-- Kanban: macro fluxo + quadro de tarefas -->
      <div v-show="activeTab === 'kanban'" class="w-full min-w-0 max-w-none space-y-6">
        <!-- Feedback imediato (regras de avanço / API); evita parecer que «Mover para aqui» não faz nada -->
        <div v-if="govFixLinks.length || govWarnLinks.length || err || msg" class="space-y-2">
          <div
            v-if="govFixLinks.length"
            class="rounded-lg border border-error/25 bg-error-container/15 p-3 text-sm font-body text-error space-y-2"
          >
            <p class="text-xs font-bold uppercase tracking-wide font-label">Não foi possível avançar — regras de governança</p>
            <p class="text-xs text-on-surface-variant font-body">
              A coluna de destino tem regras de avanço configuradas. Corrija as pendências abaixo e tente de novo.
            </p>
            <div v-for="(g, i) in govFixLinks" :key="i" class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span>{{ g.message }}</span>
              <RouterLink
                v-if="g.href"
                :to="g.href"
                class="text-xs font-bold uppercase tracking-wide text-primary underline hover:opacity-90 shrink-0"
              >
                Corrigir
              </RouterLink>
            </div>
          </div>
          <div
            v-if="govWarnLinks.length"
            class="rounded-lg border border-outline-variant/20 bg-surface-container-low/80 p-3 text-sm font-body text-on-surface space-y-2"
          >
            <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant font-label">Avisos de governança</p>
            <div v-for="(g, i) in govWarnLinks" :key="i" class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span>{{ g.message }}</span>
              <RouterLink
                v-if="g.href"
                :to="g.href"
                class="text-xs font-bold uppercase tracking-wide text-primary underline hover:opacity-90 shrink-0"
              >
                Corrigir
              </RouterLink>
            </div>
          </div>
          <p v-if="msg" class="text-on-tertiary-container text-sm font-body">{{ msg }}</p>
          <p v-else-if="err" class="text-error text-sm font-body">{{ err }}</p>
        </div>
        <div class="rounded-xl bg-surface-container-low p-5 md:p-8">
          <div class="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h3 class="text-lg font-bold font-headline text-on-surface">Linha do tempo do processo</h3>
              <p class="mt-1 text-xs text-on-surface-variant font-body">
                Fases do template Kanban macro. Administradores e coordenadores podem mover o processo para outra coluna.
              </p>
            </div>
            <p v-if="project.planned_end" class="text-xs font-medium text-on-surface-variant font-body">
              Prazo planejado:
              <span class="text-on-surface">{{ formatHeroDate(project.planned_end) }}</span>
            </p>
          </div>

          <!-- Mobile: lista vertical -->
          <div class="flex flex-col gap-4 md:hidden">
            <div
              v-for="phase in timelinePhases"
              :key="phase.col.id"
              class="relative rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-4 pl-5"
              :class="
                phase.status === 'current'
                  ? 'ring-2 ring-primary ring-offset-2 ring-offset-surface-container-low'
                  : ''
              "
            >
              <div
                class="absolute left-0 top-4 bottom-4 w-1 rounded-full"
                :class="
                  phase.status === 'completed'
                    ? 'bg-tertiary-fixed-dim'
                    : phase.status === 'current'
                      ? 'bg-primary'
                      : 'bg-outline-variant/40'
                "
              />
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold font-headline"
                  :class="
                    phase.status === 'completed'
                      ? 'bg-tertiary-container text-on-tertiary-container'
                      : phase.status === 'current'
                        ? 'bg-primary text-on-primary'
                        : 'bg-surface-container-high text-on-surface-variant'
                  "
                >
                  <span v-if="phase.status === 'completed'" class="material-symbols-outlined text-[18px]">check</span>
                  <span v-else>{{ phase.index }}</span>
                </span>
                <span
                  class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide font-label"
                  :class="
                    phase.status === 'completed'
                      ? 'bg-tertiary-container/15 text-on-tertiary-container'
                      : phase.status === 'current'
                        ? 'bg-primary/10 text-on-surface'
                        : 'bg-surface-container-high text-on-surface-variant'
                  "
                >
                  {{ phase.status === "completed" ? "Concluída" : phase.status === "current" ? "Atual" : "Pendente" }}
                </span>
              </div>
              <h4 class="mt-3 font-headline text-base font-bold text-on-surface">{{ phase.col.title }}</h4>
              <p class="mt-2 text-sm font-medium text-on-surface font-body">{{ phase.detailPrimary }}</p>
              <p class="mt-1 text-xs leading-relaxed text-on-surface-variant font-body">{{ phase.detailSecondary }}</p>
              <p class="mt-2 text-[10px] font-label uppercase tracking-wider text-on-surface-variant">
                Fase {{ phase.index }} de {{ phase.total }} · ordem {{ phase.col.position }}
              </p>
              <button
                v-if="canMove && phase.status !== 'current'"
                type="button"
                class="mt-3 w-full rounded-lg border border-outline-variant/30 py-2 text-xs font-semibold text-on-surface hover:bg-surface-container-high font-body disabled:opacity-50 disabled:pointer-events-none"
                :disabled="movingKanbanToColumnId != null"
                @click="moveTo(phase.col.id)"
              >
                {{
                  movingKanbanToColumnId === phase.col.id
                    ? "A validar regras e a gravar…"
                    : "Mover processo para esta coluna"
                }}
              </button>
            </div>
          </div>

          <!-- Desktop: grelha com linha de tempo -->
          <div class="relative hidden md:block px-1">
            <div
              class="pointer-events-none absolute left-6 right-6 top-5 z-0 h-0.5 bg-outline-variant/25"
              aria-hidden="true"
            />
            <div class="relative z-10 grid w-full min-w-0 gap-3 lg:gap-4" :style="timelineGridStyle">
              <div
                v-for="phase in timelinePhases"
                :key="'d-' + phase.col.id"
                class="flex min-w-0 flex-col items-center"
              >
                <div
                  class="mb-3 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-4 border-surface-container-low text-sm font-bold font-headline shadow-sm"
                  :class="
                    phase.status === 'completed'
                      ? 'border-tertiary-fixed-dim bg-tertiary-container text-on-tertiary-container'
                      : phase.status === 'current'
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-surface-container-high bg-surface-container-lowest text-on-surface-variant'
                  "
                >
                  <span v-if="phase.status === 'completed'" class="material-symbols-outlined text-[22px]">check</span>
                  <span v-else>{{ phase.index }}</span>
                </div>
                <div
                  class="flex w-full min-h-[200px] flex-col rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-4 shadow-[0_2px_12px_-4px_rgba(0,0,0,0.06)]"
                  :class="
                    phase.status === 'current'
                      ? 'ring-2 ring-primary ring-offset-2 ring-offset-surface-container-low'
                      : ''
                  "
                >
                  <div class="text-center">
                    <span
                      class="inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide font-label"
                      :class="
                        phase.status === 'completed'
                          ? 'bg-tertiary-container/15 text-on-tertiary-container'
                          : phase.status === 'current'
                            ? 'bg-primary/10 text-on-surface'
                            : 'bg-surface-container-high text-on-surface-variant'
                      "
                    >
                      {{ phase.status === "completed" ? "Concluída" : phase.status === "current" ? "Atual" : "Pendente" }}
                    </span>
                  </div>
                  <h4 class="mt-2 text-center font-headline text-sm font-bold leading-snug text-on-surface">
                    {{ phase.col.title }}
                  </h4>
                  <p class="mt-3 text-center text-xs font-medium leading-snug text-on-surface font-body">
                    {{ phase.detailPrimary }}
                  </p>
                  <p class="mt-2 flex-1 text-center text-[11px] leading-relaxed text-on-surface-variant font-body">
                    {{ phase.detailSecondary }}
                  </p>
                  <p class="mt-3 text-center text-[10px] font-label uppercase tracking-wider text-on-surface-variant">
                    {{ phase.index }}/{{ phase.total }} · pos. {{ phase.col.position }}
                  </p>
                  <button
                    v-if="canMove && phase.status !== 'current'"
                    type="button"
                    class="mt-3 rounded-lg bg-surface-container-high py-2 text-[11px] font-semibold text-on-surface hover:bg-surface-variant font-body disabled:opacity-50 disabled:pointer-events-none"
                    :disabled="movingKanbanToColumnId != null"
                    @click="moveTo(phase.col.id)"
                  >
                    {{
                      movingKanbanToColumnId === phase.col.id ? "A validar…" : "Mover para aqui"
                    }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <ProjectTaskBoard :project-id="project.id" :project-name="project.name" :can-mutate="canMove" />
      </div>

      <!-- PRD -->
      <div v-show="activeTab === 'prd'" class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-4xl">
        <h3 class="text-lg font-bold font-headline">PRD</h3>
        <p class="text-sm text-on-surface-variant leading-relaxed font-body">
          Espaço reservado para requisitos funcionais, critérios de aceite e decisões de produto deste projeto.
        </p>
      </div>

      <!-- Protótipo -->
      <div v-show="activeTab === 'prototipo'" class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-4xl">
        <h3 class="text-lg font-bold font-headline">Protótipo</h3>
        <p class="text-sm text-on-surface-variant leading-relaxed font-body">
          Registre aqui links e observações dos protótipos de UX/UI relacionados ao fluxo de trabalho.
        </p>
      </div>

      <!-- Desenvolvimento -->
      <div
        v-show="activeTab === 'desenvolvimento'"
        class="bg-surface-container-low rounded-lg p-6 md:p-8 space-y-4 max-w-4xl"
      >
        <h3 class="text-lg font-bold font-headline">Desenvolvimento</h3>
        <p class="text-sm text-on-surface-variant leading-relaxed font-body">
          Área para acompanhamento técnico da implementação, apontamentos de arquitetura e decisões de engenharia.
        </p>
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
        <div v-if="govFixLinks.length" class="text-error text-sm font-body space-y-2 rounded-lg border border-error/25 bg-error-container/15 p-3">
          <div v-for="(g, i) in govFixLinks" :key="i" class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span>{{ g.message }}</span>
            <RouterLink
              v-if="g.href"
              :to="g.href"
              class="text-xs font-bold uppercase tracking-wide text-primary underline hover:opacity-90 shrink-0"
            >
              Corrigir
            </RouterLink>
          </div>
        </div>
        <p v-else-if="err" class="text-error text-sm font-body">{{ err }}</p>
        <div
          v-if="govWarnLinks.length"
          class="text-on-tertiary-container text-sm font-body space-y-2 rounded-lg border border-outline-variant/20 bg-surface-container-low/60 p-3"
        >
          <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant font-label">Avisos de governança</p>
          <div v-for="(g, i) in govWarnLinks" :key="i" class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span>{{ g.message }}</span>
            <RouterLink
              v-if="g.href"
              :to="g.href"
              class="text-xs font-bold uppercase tracking-wide text-primary underline hover:opacity-90 shrink-0"
            >
              Corrigir
            </RouterLink>
          </div>
        </div>
      </template>
    </section>

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
