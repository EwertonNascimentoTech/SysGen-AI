<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api, ApiError, type GovernanceNoticePayload } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type Project = {
  id: number;
  name: string;
  product_owner: string;
  directory_name: string | null;
  methodology: string;
  current_column_id: number;
  current_column_title: string | null;
  template_id: number;
  github_repo_url: string | null;
  planned_start: string;
  planned_end: string;
  ended_at: string | null;
};

type Col = { id: number; title: string; position: number; color_hex: string };
type Tpl = { id: number; name: string; columns: Col[] };

const auth = useAuthStore();
const route = useRoute();

const templates = ref<Tpl[]>([]);
const selectedTpl = ref<number | null>(null);
const projects = ref<Project[]>([]);
const err = ref("");
const showInsight = ref(true);
/** Projeto vindo de ?project_id= (listagem ou link direto): destaca cartão e painel Consultoria IA */
const focusedProjectId = ref<number | null>(null);

const canDragCards = computed(() => auth.hasRole("admin", "coordenador"));
const draggingProjectId = ref<number | null>(null);
const dropHoverColumnId = ref<number | null>(null);
const moveMsg = ref("");
const moveErr = ref("");
/** Erros de governança com link para o detalhe do projeto (resposta 400 estruturada). */
const moveGovBlock = ref<GovernanceNoticePayload[]>([]);
const moveGovWarn = ref<GovernanceNoticePayload[]>([]);
const movingProjectId = ref<number | null>(null);

const today = new Date();
today.setHours(0, 0, 0, 0);

const cols = computed(() => {
  const t = templates.value.find((x) => x.id === selectedTpl.value);
  return (t?.columns ?? []).slice().sort((a, b) => a.position - b.position);
});

const grouped = computed(() => {
  const m = new Map<number, Project[]>();
  for (const c of cols.value) m.set(c.id, []);
  for (const p of projects.value) {
    const arr = m.get(p.current_column_id);
    if (arr) arr.push(p);
  }
  return m;
});

function normalizeColumnHex(c: Col): string {
  const raw = (c.color_hex ?? "").trim() || "#64748b";
  if (/^#[0-9A-Fa-f]{6}$/.test(raw)) return raw;
  if (/^[0-9A-Fa-f]{6}$/.test(raw)) return `#${raw}`;
  return "#64748b";
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

/** Cores das etapas vindas do template (`color_hex` na API). */
function columnBarStyle(c: Col) {
  return { backgroundColor: normalizeColumnHex(c) };
}

function columnBadgeStyle(c: Col) {
  const hex = normalizeColumnHex(c);
  const rgb = hexToRgb(hex);
  if (!rgb) return { backgroundColor: "rgba(100, 116, 139, 0.2)" };
  return { backgroundColor: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.22)` };
}

const insightProject = computed(() => {
  if (focusedProjectId.value != null) {
    for (const c of cols.value) {
      const list = grouped.value.get(c.id) ?? [];
      const hit = list.find((x) => x.id === focusedProjectId.value);
      if (hit) return { project: hit, column: c.title };
    }
  }
  for (const c of cols.value) {
    const list = grouped.value.get(c.id) ?? [];
    if (list.length) return { project: list[0], column: c.title };
  }
  return null;
});

function parseProjectIdFromRoute(): number | null {
  const raw = route.query.project_id;
  const s = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
  const n = Number(s);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function scrollKanbanCardIntoView(projectId: number) {
  window.requestAnimationFrame(() => {
    document.querySelector(`[data-kanban-card="${projectId}"]`)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    });
  });
}

async function applyFocusFromProjectId(projectId: number) {
  err.value = "";
  const proj = await api<Project>(`/projects/${projectId}`);
  const tplExists = templates.value.some((t) => t.id === proj.template_id);
  if (!tplExists) {
    err.value = "O template deste projeto não está disponível neste quadro.";
    focusedProjectId.value = null;
    return;
  }
  selectedTpl.value = proj.template_id;
  moveErr.value = "";
  moveMsg.value = "";
  await reloadBoard();
  focusedProjectId.value = projectId;
  showInsight.value = true;
  await nextTick();
  scrollKanbanCardIntoView(projectId);
}

onMounted(async () => {
  try {
    templates.value = await api<Tpl[]>("/kanban-templates");
    const pid = parseProjectIdFromRoute();
    if (pid != null) {
      await applyFocusFromProjectId(pid);
    } else {
      focusedProjectId.value = null;
      if (templates.value[0]) {
        selectedTpl.value = templates.value[0].id;
        await reloadBoard();
      }
    }
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
});

watch(
  () => route.query.project_id,
  async () => {
    if (route.name !== "kanban") return;
    const pid = parseProjectIdFromRoute();
    if (pid == null) {
      focusedProjectId.value = null;
      return;
    }
    try {
      await applyFocusFromProjectId(pid);
    } catch (e) {
      err.value = e instanceof Error ? e.message : "Erro ao focar projeto";
    }
  },
);

async function reloadBoard() {
  if (!selectedTpl.value) return;
  projects.value = await api<Project[]>(`/projects/board/kanban?template_id=${selectedTpl.value}`);
}

async function onTemplateChange() {
  moveErr.value = "";
  moveMsg.value = "";
  focusedProjectId.value = null;
  await reloadBoard();
}

/** Cartão tratado como concluído: data de encerramento ou coluna de “Concluído”. */
function isCompletedKanbanCard(p: Project, colTitle: string) {
  return Boolean(p.ended_at) || isDoneColumn(colTitle);
}

function onCardDragStart(e: DragEvent, p: Project) {
  draggingProjectId.value = p.id;
  e.dataTransfer?.setData("text/plain", String(p.id));
  if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
}

function onCardDragEnd() {
  draggingProjectId.value = null;
  dropHoverColumnId.value = null;
}

function columnPositionIndex(colId: number) {
  return cols.value.findIndex((x) => x.id === colId);
}

/** Permite apenas coluna adjacente: anterior ou seguinte (uma raia). */
function isAdjacentColumnMove(fromIdx: number, toIdx: number) {
  if (fromIdx < 0 || toIdx < 0) return false;
  return toIdx === fromIdx + 1 || toIdx === fromIdx - 1;
}

function sourceColumnTitle(proj: Project) {
  const c = cols.value.find((x) => x.id === proj.current_column_id);
  return c?.title ?? proj.current_column_title ?? "";
}

/** Concluídos só voltam uma coluna; demais podem avançar ou voltar (adjacente). */
function isAllowedKanbanDrop(proj: Project, fromIdx: number, toIdx: number) {
  if (!isAdjacentColumnMove(fromIdx, toIdx)) return false;
  const title = sourceColumnTitle(proj);
  if (isCompletedKanbanCard(proj, title)) {
    return toIdx === fromIdx - 1;
  }
  return true;
}

function onDragOverColumn(e: DragEvent, colId: number) {
  if (!draggingProjectId.value) return;
  e.preventDefault();
  const proj = projects.value.find((x) => x.id === draggingProjectId.value);
  if (!proj) return;
  const fromIdx = columnPositionIndex(proj.current_column_id);
  const toIdx = columnPositionIndex(colId);
  const ok = isAllowedKanbanDrop(proj, fromIdx, toIdx);
  if (e.dataTransfer) e.dataTransfer.dropEffect = ok ? "move" : "none";
  dropHoverColumnId.value = ok ? colId : null;
}

async function onDropOnColumn(targetColumnId: number) {
  const id = draggingProjectId.value;
  if (!id) return;
  const proj = projects.value.find((x) => x.id === id);
  if (!proj) return;
  if (proj.current_column_id === targetColumnId) {
    moveErr.value = "";
    return;
  }
  const fromIdx = columnPositionIndex(proj.current_column_id);
  const toIdx = columnPositionIndex(targetColumnId);
  if (!isAllowedKanbanDrop(proj, fromIdx, toIdx)) {
    const title = sourceColumnTitle(proj);
    if (isCompletedKanbanCard(proj, title) && isAdjacentColumnMove(fromIdx, toIdx)) {
      moveErr.value =
        "Projetos concluídos só podem voltar uma coluna (reabrir no fluxo). Avançar ou pular fases: use o detalhe do projeto.";
    } else {
      moveErr.value =
        "Solte o cartão apenas na coluna imediatamente ao lado (anterior ou seguinte). Para pular fases, use o detalhe do projeto.";
    }
    return;
  }
  moveErr.value = "";
  moveMsg.value = "";
  moveGovBlock.value = [];
  moveGovWarn.value = [];
  movingProjectId.value = id;
  try {
    const moveRes = await api<{ project: Project; governance_warnings?: GovernanceNoticePayload[] }>(`/projects/${id}/kanban/move`, {
      method: "POST",
      body: JSON.stringify({ target_column_id: targetColumnId }),
    });
    const warns = (moveRes.governance_warnings ?? []).filter((w) => w?.message);
    moveGovWarn.value = warns;
    moveMsg.value = warns.length
      ? "Cartão movido. Há avisos de governança — use os links para corrigir."
      : "Cartão movido. Governança validada para a coluna de destino.";
    await reloadBoard();
    window.setTimeout(() => {
      moveMsg.value = "";
      moveGovWarn.value = [];
    }, 8000);
  } catch (e) {
    if (e instanceof ApiError && e.governance?.length) {
      moveGovBlock.value = e.governance;
      moveErr.value = "";
    } else {
      moveErr.value = e instanceof Error ? e.message : "Não foi possível mover o cartão.";
      moveGovBlock.value = [];
    }
  } finally {
    movingProjectId.value = null;
  }
}

function methodologyLabel(m: string) {
  if (m === "base44") return "Base 44";
  if (m === "prd") return "PRD";
  return m.toUpperCase();
}

function poShort(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "—";
  if (parts.length === 1) return `${parts[0].slice(0, 8)}.`;
  return `${parts[0]} ${parts[parts.length - 1][0]}.`;
}

function poInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase() || "PO";
}

function cardProgress(p: Project, colIndex: number, totalCols: number) {
  const base = Math.round(((colIndex + 0.5) / Math.max(1, totalCols)) * 100);
  const jitter = (p.id * 7) % 23;
  return Math.min(100, Math.max(8, base + jitter - 10));
}

function progressBarStyle(c: Col) {
  return { backgroundColor: normalizeColumnHex(c) };
}

function isDoneColumn(title: string) {
  return title.toLowerCase().includes("conclu");
}

function cardFooterStatus(p: Project, colTitle: string) {
  if (p.ended_at || isDoneColumn(colTitle)) {
    return { label: "Encerrado", textClass: "text-on-surface-variant", dotClass: "bg-outline-variant" };
  }
  const end = new Date(p.planned_end + "T12:00:00");
  if (end < today) {
    return { label: "Risco crítico", textClass: "text-error", dotClass: "bg-error" };
  }
  const t = colTitle.toLowerCase();
  if (t.includes("homolog") || t.includes("revisão") || t.includes("revisao")) {
    return { label: "Revisão final", textClass: "text-on-tertiary-container", dotClass: "bg-tertiary-fixed-dim" };
  }
  if (t.includes("desenvolv")) {
    return { label: "No prazo", textClass: "text-on-tertiary-container", dotClass: "bg-tertiary-fixed-dim" };
  }
  if (t.includes("backlog")) {
    return { label: "Backlog", textClass: "text-on-surface-variant", dotClass: "bg-outline-variant" };
  }
  return { label: "Estável", textClass: "text-secondary", dotClass: "bg-secondary" };
}

function cardSubtitle(p: Project) {
  const dir = p.directory_name ?? "Diretoria não informada";
  return `${dir} · governança e entregas alinhadas ao template.`;
}

function cardExtraClass(p: Project, colTitle: string, c: Col) {
  if (p.ended_at || isDoneColumn(colTitle)) {
    return "opacity-90 border border-dashed border-outline-variant grayscale-[0.3]";
  }
  return "";
}

function cardAccentBorderStyle(p: Project, colTitle: string, c: Col) {
  if (p.ended_at || isDoneColumn(colTitle)) return {};
  return { borderLeftWidth: "4px", borderLeftStyle: "solid" as const, borderLeftColor: normalizeColumnHex(c) };
}
</script>

<template>
  <div class="-mx-2 md:-mx-4 flex flex-col min-h-[calc(100vh-8rem)] overflow-hidden">
    <!-- Cabeçalho (protótipo fluxo_operacional_kanban_pt_br) -->
    <div class="flex flex-col lg:flex-row lg:justify-between lg:items-end gap-4 mb-8 px-2 md:px-4 shrink-0">
      <div class="max-w-2xl">
        <h2 class="font-headline text-3xl font-extrabold tracking-tight text-on-surface mb-2">Quadro de governança</h2>
        <p class="text-on-surface-variant text-sm tracking-wide font-body">
          Alinhamento estratégico e velocidade operacional entre os níveis organizacionais.
          <span v-if="canDragCards" class="block mt-2 text-xs text-on-surface-variant/90">
            Arraste pelo ícone <span class="material-symbols-outlined align-middle text-base opacity-70">drag_indicator</span> para a
            <strong class="font-semibold">coluna ao lado</strong> (voltar ou avançar uma raia).
            <strong class="font-semibold">Projetos concluídos</strong> só podem ser arrastados para trás, uma coluna; ao voltar, a data de
            encerramento é limpa. A API valida a governança da fase de destino.
          </span>
        </p>
        <div class="mt-4 flex flex-col gap-2">
          <div v-if="focusedProjectId && insightProject" class="flex flex-wrap items-center gap-2 text-sm font-body">
            <span class="material-symbols-outlined text-primary text-lg">center_focus_strong</span>
            <span class="text-on-surface-variant">Acompanhando:</span>
            <strong class="text-on-surface font-headline">{{ insightProject.project.name }}</strong>
            <span class="text-on-surface-variant">· {{ insightProject.column }}</span>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider font-label flex items-center gap-2">
              Template
              <select
                v-model.number="selectedTpl"
                class="rounded-md bg-surface-container-low border-none text-sm font-semibold text-on-surface px-3 py-2 font-body focus:ring-1 focus:ring-primary"
                @change="onTemplateChange"
              >
                <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
              </select>
            </label>
          </div>
        </div>
      </div>
      <RouterLink
        to="/projetos/novo"
        class="editorial-gradient text-on-primary px-6 py-2.5 rounded-md flex items-center shadow-lg hover:opacity-90 transition-all shrink-0 font-body"
      >
        <span class="material-symbols-outlined mr-2">add</span>
        <span class="font-bold text-sm tracking-tight">ADICIONAR PROJETO</span>
      </RouterLink>
    </div>

    <p v-if="err" class="text-error text-sm font-body px-2 md:px-4 shrink-0">{{ err }}</p>
    <div
      v-if="moveGovBlock.length"
      class="text-error text-sm font-body px-2 md:px-4 shrink-0 bg-error-container/20 rounded-lg py-3 border border-error/20 space-y-2"
    >
      <div v-for="(g, i) in moveGovBlock" :key="i" class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span>{{ g.message }}</span>
        <RouterLink
          v-if="g.href"
          :to="g.href"
          class="text-xs font-bold uppercase tracking-wide text-primary underline hover:opacity-90 shrink-0"
        >
          Corrigir no projeto
        </RouterLink>
      </div>
    </div>
    <p
      v-else-if="moveErr"
      class="text-error text-sm font-body px-2 md:px-4 shrink-0 bg-error-container/20 rounded-lg py-2 border border-error/20"
    >
      {{ moveErr }}
    </p>
    <p v-if="moveMsg" class="text-on-tertiary-container text-sm font-body px-2 md:px-4 shrink-0">{{ moveMsg }}</p>
    <div
      v-if="moveGovWarn.length"
      class="text-on-tertiary-container text-sm font-body px-2 md:px-4 shrink-0 space-y-2 border border-outline-variant/15 rounded-lg py-3 bg-surface-container-low/50"
    >
      <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant font-label">Avisos de governança</p>
      <div v-for="(g, i) in moveGovWarn" :key="i" class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span>{{ g.message }}</span>
        <RouterLink
          v-if="g.href"
          :to="g.href"
          class="text-xs font-bold uppercase tracking-wide text-primary underline hover:opacity-90 shrink-0"
        >
          Abrir correção
        </RouterLink>
      </div>
    </div>

    <!-- Board -->
    <div class="flex-1 overflow-x-auto pb-6 kanban-board-scroll px-2 md:px-4 min-h-0">
      <div class="flex space-x-6 h-full items-start">
        <div
          v-for="(c, colIdx) in cols"
          :key="c.id"
          class="kanban-column flex flex-col h-full max-h-[calc(100vh-14rem)]"
        >
          <div class="flex items-center justify-between mb-4 px-2 shrink-0">
            <div class="flex items-center min-w-0">
              <span class="w-1.5 h-6 rounded-full mr-3 shrink-0" :style="columnBarStyle(c)" />
              <h3 class="font-headline font-bold text-sm tracking-tight text-on-surface uppercase truncate">{{ c.title }}</h3>
              <span
                class="ml-3 text-[10px] px-1.5 py-0.5 rounded font-bold shrink-0 font-label text-on-surface"
                :style="columnBadgeStyle(c)"
              >
                {{ String(grouped.get(c.id)?.length ?? 0).padStart(2, "0") }}
              </span>
            </div>
            <span class="material-symbols-outlined text-outline cursor-pointer hover:text-primary transition-colors shrink-0">more_horiz</span>
          </div>
          <div
            class="flex-1 bg-surface-container-low/40 rounded-lg p-2 space-y-4 overflow-y-auto min-h-[200px] transition-[box-shadow,background-color] duration-150"
            :class="
              dropHoverColumnId === c.id && draggingProjectId
                ? 'ring-2 ring-primary ring-inset bg-primary/5'
                : ''
            "
            @dragover="onDragOverColumn($event, c.id)"
            @drop.prevent="onDropOnColumn(c.id)"
          >
            <div
              v-for="p in grouped.get(c.id) ?? []"
              :key="p.id"
              :data-kanban-card="p.id"
              class="flex rounded-xl shadow-sm border transition-all text-left bg-surface-container-lowest overflow-hidden"
              :style="cardAccentBorderStyle(p, c.title, c)"
              :class="[
                cardExtraClass(p, c.title, c),
                focusedProjectId === p.id
                  ? 'border-primary ring-2 ring-primary/35 shadow-md'
                  : 'border-transparent hover:border-outline-variant/30',
                draggingProjectId === p.id ? 'opacity-60 scale-[0.99]' : '',
                movingProjectId === p.id ? 'pointer-events-none opacity-70' : '',
              ]"
            >
              <div
                v-if="canDragCards"
                class="flex items-stretch shrink-0 w-9 justify-center bg-surface-container/60 hover:bg-surface-container-high cursor-grab active:cursor-grabbing border-r border-outline-variant/10"
                draggable="true"
                title="Arrastar para outra coluna"
                @dragstart="onCardDragStart($event, p)"
                @dragend="onCardDragEnd"
              >
                <span class="material-symbols-outlined text-on-surface-variant text-lg self-center">drag_indicator</span>
              </div>
              <RouterLink
                :to="`/projetos/${p.id}?tab=desenvolvimento`"
                class="block flex-1 min-w-0 p-4 cursor-pointer"
              >
              <div v-if="!(p.ended_at || isDoneColumn(c.title))" class="flex justify-between items-start mb-3">
                <span
                  class="text-[10px] font-bold tracking-widest text-on-surface-variant uppercase bg-surface-container-high px-2 py-0.5 rounded-full font-label"
                  >{{ methodologyLabel(p.methodology) }}</span
                >
                <div class="flex -space-x-2">
                  <div
                    class="w-5 h-5 rounded-full border-2 border-surface-container-lowest bg-surface-variant flex items-center justify-center text-[8px] font-bold text-on-surface"
                  >
                    {{ poInitials(p.product_owner).slice(0, 1) }}
                  </div>
                  <div
                    class="w-5 h-5 rounded-full border-2 border-surface-container-lowest bg-primary-container flex items-center justify-center text-[8px] text-white font-bold"
                  >
                    {{ poInitials(p.product_owner).slice(1, 2) || "·" }}
                  </div>
                </div>
              </div>
              <h4
                class="font-headline text-sm font-bold text-on-surface mb-1"
                :class="p.ended_at || isDoneColumn(c.title) ? 'line-through text-on-surface/60' : ''"
              >
                {{ p.name }}
              </h4>
              <p
                class="text-xs text-on-surface-variant line-clamp-2 mb-4 font-body"
                :class="p.ended_at ? 'text-on-surface-variant/60' : ''"
              >
                {{ p.ended_at ? `Encerrado · prazo ${p.planned_end}` : cardSubtitle(p) }}
              </p>
              <div v-if="!(p.ended_at || isDoneColumn(c.title))" class="flex items-center space-x-3 text-outline-variant mb-4">
                <span
                  class="material-symbols-outlined text-sm"
                  :class="p.github_repo_url ? 'text-primary' : ''"
                  title="GitHub"
                  >hub</span
                >
                <span class="material-symbols-outlined text-sm" title="Documentação no detalhe">description</span>
              </div>
              <div v-if="!(p.ended_at || isDoneColumn(c.title))" class="space-y-1.5">
                <div class="flex justify-between text-[10px] font-bold text-on-surface-variant uppercase tracking-tighter font-label">
                  <span>Progresso</span>
                  <span>{{ cardProgress(p, colIdx, cols.length) }}%</span>
                </div>
                <div class="w-full h-1 bg-surface-container rounded-full overflow-hidden">
                  <div
                    class="h-full transition-all"
                    :style="{ width: `${cardProgress(p, colIdx, cols.length)}%`, ...progressBarStyle(c) }"
                  />
                </div>
              </div>
              <div class="mt-4 pt-4 border-t border-surface-container flex items-center justify-between gap-2">
                <div
                  class="flex items-center text-[10px] font-semibold uppercase tracking-tight font-label"
                  :class="cardFooterStatus(p, c.title).textClass"
                >
                  <span class="w-2 h-2 rounded-full mr-2 shrink-0" :class="cardFooterStatus(p, c.title).dotClass" />
                  {{ cardFooterStatus(p, c.title).label }}
                </div>
                <span class="text-[10px] font-bold text-on-surface-variant font-body shrink-0">PO: {{ poShort(p.product_owner) }}</span>
              </div>
              </RouterLink>
            </div>
            <p v-if="(grouped.get(c.id) ?? []).length === 0" class="text-xs text-on-surface-variant/70 text-center py-8 font-body italic">
              Nenhum projeto nesta coluna
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Rodapé meta -->
    <footer class="mt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-t border-outline-variant/10 pt-4 px-2 md:px-4 shrink-0">
      <div class="flex flex-wrap items-center gap-6">
        <div class="flex items-center text-[10px] font-bold text-on-surface-variant uppercase tracking-widest font-label">
          <span class="material-symbols-outlined text-sm mr-2">filter_alt</span>
          Filtros:
          <span class="text-primary ml-1">Template ativo</span>
        </div>
        <div class="flex items-center text-[10px] font-bold text-on-surface-variant uppercase tracking-widest font-label">
          <span class="material-symbols-outlined text-sm mr-2">sort</span>
          Ordenar:
          <span class="text-primary ml-1">Nome (A–Z)</span>
        </div>
      </div>
      <div class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest flex items-center font-label">
        <span class="w-2 h-2 rounded-full bg-tertiary-fixed-dim animate-pulse mr-2" />
        Sincronização de governança ativa
      </div>
    </footer>

    <!-- Consultoria IA (flutuante) -->
    <div
      v-if="showInsight && insightProject"
      class="fixed bottom-8 right-8 w-80 max-w-[calc(100vw-2rem)] p-[1px] rounded-lg bg-gradient-to-br from-tertiary-fixed via-primary to-primary-container shadow-2xl z-40"
    >
      <div class="bg-surface-container-lowest rounded-[calc(0.5rem-1px)] p-5">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center space-x-2">
            <span class="material-symbols-outlined text-tertiary-fixed-dim" style="font-variation-settings: 'FILL' 1">auto_awesome</span>
            <span class="font-headline font-bold text-xs tracking-tight">CONSULTORIA IA</span>
          </div>
          <button type="button" class="material-symbols-outlined text-outline-variant text-sm cursor-pointer" aria-label="Fechar" @click="showInsight = false">
            close
          </button>
        </div>
        <p class="text-xs text-on-surface font-medium leading-relaxed mb-4 font-body">
          “<strong>{{ insightProject.project.name }}</strong>” está em
          <span class="font-bold">{{ insightProject.column }}</span>. Abra o cartão para GitHub, Wiki e movimentação no quadro.
        </p>
        <div class="flex space-x-3">
          <RouterLink
            :to="`/projetos/${insightProject.project.id}`"
            class="flex-1 bg-primary text-on-primary py-2 rounded text-[10px] font-bold uppercase tracking-wider text-center font-label hover:opacity-90"
          >
            Abrir projeto
          </RouterLink>
          <button
            type="button"
            class="px-3 bg-surface-container-high text-on-surface-variant py-2 rounded text-[10px] font-bold uppercase tracking-wider font-label"
            @click="showInsight = false"
          >
            Ocultar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
