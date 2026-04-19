<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type ColumnRules = {
  require_description: boolean;
  require_attachment_audit: boolean;
  require_po_assigned: boolean;
  require_github_tag: boolean;
  min_tag_count: number;
};

type Col = {
  id: number;
  title: string;
  position: number;
  color_hex: string;
  rules: ColumnRules;
  applied_rule_ids: number[];
  visible_detail_tabs: string[];
};

type GovernanceCatalogRule = {
  id: number;
  name: string;
  description: string | null;
  rule_key: string;
  min_tags_value: number | null;
  active: boolean;
  on_violation?: "bloqueio" | "alerta";
};

type Tpl = {
  id: number;
  name: string;
  status: string;
  version: number;
  description?: string | null;
  methodology?: string | null;
  columns: Col[];
};

type ProjectBrief = { template_id: number };

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const items = ref<Tpl[]>([]);
const err = ref("");
const msg = ref("");
const searchQ = ref("");
const selectedId = ref<number | null>(null);
const showNewModal = ref(false);
const showEditMetaModal = ref(false);
const showDeleteModal = ref(false);
const pendingDeleteTpl = ref<Tpl | null>(null);
const countByTemplate = ref<Record<number, number>>({});
const saving = ref(false);
const activePhaseId = ref<number | null>(null);
const governanceCatalog = ref<GovernanceCatalogRule[]>([]);

const newName = ref("");
const newDescription = ref("");
const newMethodology = ref("Scrum adaptativo");

const metaDraftName = ref("");
const metaDraftDescription = ref("");
const metaDraftMethodology = ref("");
const metaEditTargetId = ref<number | null>(null);

const METHODOLOGY_PRESETS: Record<string, string[]> = {
  "Scrum adaptativo": ["Backlog", "Em concepção", "Em desenvolvimento", "Revisão", "Concluído"],
  "Kanban clássico (Toyota)": ["Backlog", "Em progresso", "Em revisão", "Concluído"],
  "Gestão de ativos criativos": ["Briefing", "Produção", "Revisão", "Aprovação", "Publicado"],
  "Auditoria de compliance": ["Planejamento", "Evidências", "Análise", "Aprovação", "Encerrado"],
};

const METHODOLOGY_OPTIONS = Object.keys(METHODOLOGY_PRESETS);

const COLOR_SWATCHES = ["#64748b", "#3b82f6", "#0d9488", "#ca8a04", "#9333ea", "#e11d48"];
const DETAIL_TAB_OPTIONS: { value: string; label: string }[] = [
  { value: "resumo", label: "Resumo" },
  { value: "kanban", label: "Desenvolvimento" },
  { value: "prd", label: "PRD" },
  { value: "prototipo", label: "Protótipo" },
  { value: "planejamento", label: "Planejamento" },
  { value: "anexos", label: "Anexos" },
  { value: "auditoria", label: "Auditoria" },
  { value: "github", label: "GitHub" },
  { value: "wiki", label: "Wiki" },
  { value: "cursor", label: "Cursor Hub" },
];
const DETAIL_TAB_DEFAULT_ORDER = DETAIL_TAB_OPTIONS.map((o) => o.value);
const DETAIL_TAB_LABELS = Object.fromEntries(DETAIL_TAB_OPTIONS.map((o) => [o.value, o.label])) as Record<string, string>;

const isFluxoRoute = computed(() => route.name === "templates-fluxo");

const filteredItems = computed(() => {
  const s = searchQ.value.trim().toLowerCase();
  if (!s) return items.value;
  return items.value.filter(
    (t) =>
      t.name.toLowerCase().includes(s) ||
      (t.description ?? "").toLowerCase().includes(s) ||
      (t.methodology ?? "").toLowerCase().includes(s),
  );
});

const selected = computed(() => items.value.find((t) => t.id === selectedId.value) ?? null);

const sortedColumns = computed(() =>
  (selected.value?.columns ?? []).slice().sort((a, b) => a.position - b.position),
);

const canEdit = computed(() => auth.hasRole("admin", "coordenador"));

const stats = computed(() => {
  const total = items.value.length;
  const published = items.value.filter((t) => t.status === "publicado").length;
  let governed = 0;
  for (const t of items.value) governed += countByTemplate.value[t.id] ?? 0;
  const maxV = items.value.reduce((m, t) => Math.max(m, t.version), 0);
  return { total, published, governed, maxVersion: maxV };
});

async function loadListPath() {
  return auth.hasRole("admin", "coordenador") ? "/kanban-templates/all" : "/kanban-templates";
}

async function reloadTemplates() {
  const path = await loadListPath();
  items.value = await api<Tpl[]>(path);
}

async function loadGovernanceCatalog() {
  if (!canEdit.value) return;
  try {
    governanceCatalog.value = await api<GovernanceCatalogRule[]>("/governance-advance-rules");
  } catch {
    governanceCatalog.value = [];
  }
}

onMounted(async () => {
  try {
    await reloadTemplates();
    if (route.name === "templates-fluxo") {
      const tid = Number(route.params.templateId);
      if (!Number.isNaN(tid)) selectedId.value = tid;
      await loadGovernanceCatalog();
    } else if (items.value.length && selectedId.value === null) {
      selectedId.value = items.value[0].id;
    }
    await loadProjectCounts();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
});

watch(
  () => route.params.templateId,
  (tid) => {
    if (route.name !== "templates-fluxo") return;
    const id = Number(tid);
    if (!Number.isNaN(id)) selectedId.value = id;
  },
);

watch(filteredItems, (list) => {
  if (route.name === "templates-fluxo") return;
  if (!list.length) return;
  // Não trocar a seleção só porque o filtro de pesquisa esconde o cartão — isso quebrava "Duplicar selecionado".
  if (selectedId.value != null && items.value.some((t) => t.id === selectedId.value)) return;
  selectedId.value = list[0]?.id ?? null;
});

watch(selected, (t) => {
  if (t) {
    const first = sortedColumns.value[0];
    activePhaseId.value = first?.id ?? null;
  } else {
    activePhaseId.value = null;
  }
});

watch(isFluxoRoute, async (fluxo) => {
  if (fluxo) {
    const tid = Number(route.params.templateId);
    if (!Number.isNaN(tid)) selectedId.value = tid;
    try {
      await reloadTemplates();
      await loadGovernanceCatalog();
      await loadProjectCounts();
    } catch {
      /* ignore */
    }
  }
});

async function loadProjectCounts() {
  try {
    const projs = await api<ProjectBrief[]>("/projects");
    const m: Record<number, number> = {};
    for (const p of projs) m[p.template_id] = (m[p.template_id] ?? 0) + 1;
    countByTemplate.value = m;
  } catch {
    countByTemplate.value = {};
  }
}

function projectCount(tplId: number) {
  return countByTemplate.value[tplId] ?? 0;
}

function statusPill(status: string) {
  if (status === "publicado") {
    return { label: "Ativo", class: "bg-tertiary-container text-on-tertiary-container" };
  }
  return { label: "Rascunho", class: "bg-surface-container-high text-on-surface-variant" };
}

function cardDimmed(t: Tpl) {
  return t.status !== "publicado";
}

function openNewModal() {
  newName.value = "";
  newDescription.value = "";
  newMethodology.value = METHODOLOGY_OPTIONS[0] ?? "Scrum adaptativo";
  showNewModal.value = true;
}

function openEditMeta(t: Tpl) {
  metaEditTargetId.value = t.id;
  metaDraftName.value = t.name;
  metaDraftDescription.value = t.description ?? "";
  metaDraftMethodology.value = t.methodology ?? METHODOLOGY_OPTIONS[0];
  showEditMetaModal.value = true;
}

function openDeleteModal(t: Tpl) {
  pendingDeleteTpl.value = t;
  showDeleteModal.value = true;
}

function templateDescriptionLine(t: Tpl) {
  const d = (t.description ?? "").trim();
  if (d) return d;
  return "Template de fluxo Kanban com regras de governança por fase, alinhado ao movimento no quadro do projeto.";
}

function methodologyLine(t: Tpl) {
  return (t.methodology ?? "").trim() || "Kanban / governança";
}

async function withSave(fn: () => Promise<void>) {
  saving.value = true;
  err.value = "";
  try {
    await fn();
    await loadProjectCounts();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  } finally {
    saving.value = false;
  }
}

async function createDraft() {
  msg.value = "";
  const preset = METHODOLOGY_PRESETS[newMethodology.value];
  const column_titles = preset?.length ? preset : ["Backlog", "Em desenvolvimento", "Concluído"];
  await withSave(async () => {
    if (!newName.value.trim()) throw new Error("Informe o nome do template.");
    const created = await api<Tpl>("/kanban-templates", {
      method: "POST",
      body: JSON.stringify({
        name: newName.value.trim(),
        column_titles,
        description: newDescription.value.trim() || null,
        methodology: newMethodology.value.trim() || null,
      }),
    });
    msg.value = "Template criado.";
    showNewModal.value = false;
    await reloadTemplates();
    selectedId.value = created.id;
  });
}

async function saveMetaDraft() {
  const id = metaEditTargetId.value;
  if (!id || !canEdit.value) return;
  await withSave(async () => {
    await api(`/kanban-templates/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: metaDraftName.value.trim(),
        description: metaDraftDescription.value.trim() || null,
        methodology: metaDraftMethodology.value.trim() || null,
      }),
    });
    await reloadTemplates();
    showEditMetaModal.value = false;
    msg.value = "Dados do template atualizados.";
  });
}

async function publish(id: number) {
  await withSave(async () => {
    await api(`/kanban-templates/${id}/publish`, { method: "POST" });
    await reloadTemplates();
    msg.value = "Template publicado.";
  });
}

async function duplicateTemplate(t: Tpl) {
  if (!canEdit.value) return;
  await withSave(async () => {
    const dup = await api<Tpl>(`/kanban-templates/${t.id}/duplicate`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await reloadTemplates();
    selectedId.value = dup.id;
    msg.value = "Template duplicado como rascunho.";
  });
}

async function duplicateSelected() {
  const t = selected.value;
  if (!t) {
    err.value = "Selecione um template na grelha (clique no cartão) antes de duplicar.";
    return;
  }
  await duplicateTemplate(t);
}

function selectTemplateCard(t: Tpl) {
  err.value = "";
  selectedId.value = t.id;
}

async function confirmDeleteTemplate() {
  const tpl = pendingDeleteTpl.value;
  if (!tpl || !canEdit.value) return;
  await withSave(async () => {
    await api(`/kanban-templates/${tpl.id}`, { method: "DELETE" });
    await reloadTemplates();
    msg.value = "Template excluído.";
    if (selectedId.value === tpl.id) selectedId.value = items.value[0]?.id ?? null;
    showDeleteModal.value = false;
    pendingDeleteTpl.value = null;
    if (route.name === "templates-fluxo" && route.params.templateId === String(tpl.id)) {
      await router.push({ name: "templates" });
    }
  });
}

function goFluxo(t: Tpl) {
  router.push({ name: "templates-fluxo", params: { templateId: String(t.id) } });
}

function backToLibrary() {
  router.push({ name: "templates" });
}

/** Volta à página anterior no histórico; na primeira entrada da sessão, abre Configurações. */
function leaveTemplatesToPrevious() {
  const pos = (window.history.state as { position?: number } | null)?.position;
  if (pos === 1) {
    void router.push({ name: "config" });
    return;
  }
  void router.back();
}

async function builderDiscard() {
  err.value = "";
  try {
    await reloadTemplates();
    msg.value = "Dados recarregados do servidor.";
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

async function builderSaveBar() {
  await reloadTemplates();
  msg.value = "Fluxo sincronizado com o servidor.";
}

async function addPhase() {
  await addPhaseTitled("Nova fase");
}

async function addPhaseTitled(title: string) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns`, {
      method: "POST",
      body: JSON.stringify({ title: title.trim() || "Nova fase" }),
    });
    await reloadTemplates();
    msg.value = "Fase adicionada.";
    const refreshed = items.value.find((x) => x.id === t.id);
    const last = refreshed?.columns?.slice().sort((a, b) => b.position - a.position)[0];
    if (last) activePhaseId.value = last.id;
  });
}

async function deletePhase(col: Col) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  const ok = window.confirm(`Excluir a fase "${col.title}"?`);
  if (!ok) return;
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns/${col.id}`, { method: "DELETE" });
    await reloadTemplates();
    msg.value = "Fase excluída.";
  });
}

async function flushPhaseTitle(col: Col, ev: Event) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  const el = ev.target as HTMLInputElement;
  const title = el.value.trim();
  if (!title || title === col.title) return;
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns/${col.id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    await reloadTemplates();
  });
}

async function setPhaseColor(col: Col, hex: string) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns/${col.id}`, {
      method: "PATCH",
      body: JSON.stringify({ color_hex: hex }),
    });
    await reloadTemplates();
  });
}

async function patchAppliedRuleIds(col: Col, ids: number[]) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns/${col.id}`, {
      method: "PATCH",
      body: JSON.stringify({ applied_rule_ids: ids }),
    });
    await reloadTemplates();
  });
}

function toggleCatalogRule(col: Col, ruleId: number, checked: boolean) {
  const cur = new Set(col.applied_rule_ids ?? []);
  if (checked) cur.add(ruleId);
  else cur.delete(ruleId);
  void patchAppliedRuleIds(col, [...cur].sort((a, b) => a - b));
}

async function patchVisibleDetailTabs(col: Col, tabs: string[]) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns/${col.id}`, {
      method: "PATCH",
      body: JSON.stringify({ visible_detail_tabs: tabs }),
    });
    await reloadTemplates();
  });
}

function visibleDetailTabsForColumn(col: Col) {
  const cur = new Set((col.visible_detail_tabs ?? []).map((x) => x.toLowerCase()));
  if (!cur.size) return DETAIL_TAB_OPTIONS.map((o) => o.value);
  return DETAIL_TAB_OPTIONS.map((o) => o.value).filter((v) => cur.has(v));
}

function orderedDetailTabsForColumn(col: Col) {
  const valid = new Set(DETAIL_TAB_DEFAULT_ORDER);
  const raw = (col.visible_detail_tabs ?? [])
    .map((x) => String(x).toLowerCase())
    .filter((x) => valid.has(x))
    .filter((x, i, arr) => arr.indexOf(x) === i);
  if (!raw.length) return [...DETAIL_TAB_DEFAULT_ORDER];
  return raw;
}

function isDetailTabVisible(col: Col, tab: string) {
  return orderedDetailTabsForColumn(col).includes(tab);
}

function toggleDetailTabVisibility(col: Col, tab: string, checked: boolean) {
  const ordered = orderedDetailTabsForColumn(col);
  if (checked) {
    if (!ordered.includes(tab)) ordered.push(tab);
  } else {
    const idx = ordered.indexOf(tab);
    if (idx >= 0) ordered.splice(idx, 1);
  }
  if (!ordered.length) return;
  void patchVisibleDetailTabs(col, ordered);
}

function detailTabsUnifiedRowsForColumn(col: Col) {
  const orderedVisible = orderedDetailTabsForColumn(col);
  const visibleSet = new Set(orderedVisible);
  const hidden = DETAIL_TAB_DEFAULT_ORDER.filter((tab) => !visibleSet.has(tab));
  return [...orderedVisible, ...hidden];
}

function detailTabLabel(tab: string) {
  return DETAIL_TAB_LABELS[tab] ?? tab;
}

function onDetailTabDragStart(ev: DragEvent, tab: string, col: Col) {
  if (!isDetailTabVisible(col, tab)) return;
  ev.dataTransfer?.setData("text/plain", tab);
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = "move";
}

function onDetailTabDragOver(ev: DragEvent) {
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
}

function onDetailTabDrop(col: Col, toIndex: number, ev: DragEvent) {
  ev.preventDefault();
  if (!canEdit.value || saving.value) return;
  const fromTab = (ev.dataTransfer?.getData("text/plain") ?? "").toLowerCase();
  if (!fromTab) return;
  moveDetailTabByTab(col, fromTab, toIndex);
}

function moveDetailTab(col: Col, fromIndex: number, toIndex: number) {
  const ordered = orderedDetailTabsForColumn(col);
  if (fromIndex < 0 || fromIndex >= ordered.length || toIndex < 0 || toIndex >= ordered.length || fromIndex === toIndex) return;
  const [moved] = ordered.splice(fromIndex, 1);
  ordered.splice(toIndex, 0, moved);
  void patchVisibleDetailTabs(col, ordered);
}

function moveDetailTabByTab(col: Col, fromTab: string, toIndex: number) {
  const ordered = orderedDetailTabsForColumn(col);
  const fromIndex = ordered.indexOf(fromTab);
  if (fromIndex < 0) return;
  moveDetailTab(col, fromIndex, toIndex);
}

function visibleDetailTabIndex(col: Col, tab: string) {
  return orderedDetailTabsForColumn(col).indexOf(tab);
}

function catalogRulesForPhase() {
  return governanceCatalog.value.filter((r) => r.active);
}

function ruleKeyShort(key: string) {
  if (key === "require_description") return "Descrição";
  if (key === "require_attachment_audit") return "Auditoria";
  if (key === "require_po_assigned") return "PO";
  if (key === "require_github_tag") return "Tag GH";
  if (key === "min_tag_count") return "N tags";
  if (key === "require_github_repo") return "Repo GH";
  if (key === "require_methodology_prd") return "PRD";
  if (key === "require_any_attachment") return "Anexo";
  return key;
}

async function movePhase(index: number, delta: number) {
  const t = selected.value;
  if (!t || !canEdit.value) return;
  const colsL = sortedColumns.value;
  const j = index + delta;
  if (j < 0 || j >= colsL.length) return;
  const ids = colsL.map((c) => c.id);
  const [moved] = ids.splice(index, 1);
  ids.splice(j, 0, moved);
  await withSave(async () => {
    await api(`/kanban-templates/${t.id}/columns/reorder`, {
      method: "POST",
      body: JSON.stringify({ ordered_column_ids: ids }),
    });
    await reloadTemplates();
  });
}

function activeRulesCount(col: Col) {
  const ids = col.applied_rule_ids ?? [];
  if (ids.length > 0) return ids.length;
  let n = 0;
  if (col.rules.require_description) n++;
  if (col.rules.require_attachment_audit) n++;
  if (col.rules.require_po_assigned) n++;
  if (col.rules.require_github_tag) n++;
  if ((col.rules.min_tag_count ?? 0) > 0) n++;
  return n;
}
</script>

<template>
  <div class="-mx-2 md:-mx-4 space-y-6 px-2 md:px-4 pb-12">
    <!-- Builder de fases (protótipo: configuração de fases) -->
    <template v-if="isFluxoRoute">
      <div
        v-if="selected"
        class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-outline-variant/15"
      >
        <div class="flex items-center gap-4 min-w-0">
          <button
            type="button"
            class="flex items-center gap-2 text-on-surface-variant hover:text-primary transition-colors shrink-0 font-body text-sm"
            @click="backToLibrary"
          >
            <span class="material-symbols-outlined text-xl">arrow_back</span>
            <span class="font-medium">Voltar para Templates</span>
          </button>
          <div class="h-8 w-px bg-outline-variant/30 hidden sm:block shrink-0" />
          <div class="min-w-0">
            <span class="text-[10px] font-bold tracking-widest text-on-surface-variant uppercase font-label block">Builder</span>
            <span class="text-base font-headline font-bold text-on-surface truncate block">Template: {{ selected.name }}</span>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-4">
          <nav class="flex gap-6 text-sm font-body">
            <span class="pb-1 font-bold border-b-2 border-primary text-on-surface">Configuração</span>
            <span class="pb-1 text-on-surface-variant cursor-not-allowed border-b-2 border-transparent">Previsão</span>
          </nav>
          <button
            v-if="auth.hasRole('admin') && selected.status !== 'publicado'"
            type="button"
            class="bg-primary text-on-primary px-4 py-2 rounded-md text-xs font-bold uppercase tracking-wider font-label hover:opacity-90"
            @click="publish(selected.id)"
          >
            Publicar
          </button>
        </div>
      </div>

      <div v-if="selected" class="max-w-5xl mx-auto">
        <div class="flex flex-col lg:flex-row lg:justify-between lg:items-end gap-6 mb-10">
          <div class="max-w-lg">
            <h2 class="font-headline text-3xl md:text-4xl font-extrabold tracking-tight text-primary mb-2">Estrutura de Fases</h2>
            <p class="text-on-surface-variant leading-relaxed font-body text-sm">
              Defina o ciclo de vida dos projetos. Organize o fluxo, travas de segurança e a governança em cada etapa. As alterações são
              guardadas ao editar cada campo.
            </p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button
              type="button"
              class="px-6 py-2.5 bg-surface-container-high text-on-surface font-semibold rounded-md hover:bg-surface-variant transition-all text-sm font-body"
              @click="builderDiscard"
            >
              Descartar
            </button>
            <button
              type="button"
              class="px-8 py-2.5 bg-primary text-on-primary font-bold rounded-md shadow-lg shadow-primary/10 hover:opacity-95 transition-all text-sm font-body"
              @click="builderSaveBar"
            >
              Salvar alterações do fluxo
            </button>
          </div>
        </div>

        <p v-if="msg" class="text-sm text-on-tertiary-container font-body mb-4">{{ msg }}</p>
        <p v-if="err" class="text-error text-sm font-body mb-4">{{ err }}</p>

        <div class="space-y-6">
          <div
            v-for="(c, idx) in sortedColumns"
            :key="c.id"
            class="group bg-surface-container-low rounded-xl p-1 transition-all hover:bg-surface-container"
            @click="activePhaseId = c.id"
          >
            <div
              class="bg-surface-container-lowest rounded-lg p-6 shadow-sm flex flex-col md:flex-row gap-8 items-start border"
              :class="activePhaseId === c.id ? 'border-primary/25 ring-1 ring-primary/10' : 'border-outline-variant/10'"
            >
              <div class="flex items-center gap-4 shrink-0">
                <div class="cursor-grab text-outline-variant hover:text-on-surface" title="Reordenar">
                  <span class="material-symbols-outlined">drag_indicator</span>
                </div>
                <div class="flex flex-col items-center gap-2">
                  <div class="w-10 h-10 rounded-full bg-primary text-on-primary flex items-center justify-center font-bold text-sm font-headline">
                    {{ String(idx + 1).padStart(2, "0") }}
                  </div>
                  <div class="flex gap-1">
                    <button
                      v-if="canEdit"
                      type="button"
                      class="p-0.5 text-on-surface-variant hover:text-primary disabled:opacity-30"
                      :disabled="idx === 0 || saving"
                      @click.stop="movePhase(idx, -1)"
                    >
                      <span class="material-symbols-outlined text-sm">chevron_left</span>
                    </button>
                    <button
                      v-if="canEdit"
                      type="button"
                      class="p-0.5 text-on-surface-variant hover:text-primary disabled:opacity-30"
                      :disabled="idx >= sortedColumns.length - 1 || saving"
                      @click.stop="movePhase(idx, 1)"
                    >
                      <span class="material-symbols-outlined text-sm">chevron_right</span>
                    </button>
                  </div>
                </div>
              </div>

              <div class="flex-1 grid grid-cols-1 md:grid-cols-12 gap-8 w-full min-w-0">
                <div class="md:col-span-4 space-y-4">
                  <div>
                    <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label"
                      >Nome da fase</label
                    >
                    <input
                      :value="c.title"
                      :disabled="!canEdit"
                      class="w-full bg-surface-container-low border-none rounded-md px-4 py-2.5 font-bold focus:ring-2 focus:ring-primary/20 text-on-surface font-headline text-sm disabled:opacity-70"
                      @change="flushPhaseTitle(c, $event)"
                    />
                  </div>
                  <div>
                    <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label"
                      >Cor do status</label
                    >
                    <div class="flex items-center gap-3 flex-wrap">
                      <input
                        :value="c.color_hex"
                        type="color"
                        :disabled="!canEdit"
                        class="w-9 h-9 rounded-full border-2 border-white shadow-sm cursor-pointer disabled:opacity-50"
                        @input="setPhaseColor(c, ($event.target as HTMLInputElement).value)"
                      />
                      <span class="text-sm font-medium text-on-surface-variant font-mono">{{ c.color_hex }}</span>
                      <div class="flex gap-1">
                        <button
                          v-for="hex in COLOR_SWATCHES"
                          :key="hex"
                          type="button"
                          class="w-6 h-6 rounded-full border border-outline-variant/30"
                          :style="{ backgroundColor: hex }"
                          :disabled="!canEdit || saving"
                          @click.stop="setPhaseColor(c, hex)"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div class="md:col-span-7 min-w-0">
                  <div class="flex flex-wrap justify-between items-center gap-2 mb-3">
                    <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant font-label"
                      >Regras de avanço (catálogo)</label
                    >
                    <div class="flex flex-wrap items-center gap-2">
                      <RouterLink
                        to="/regras-avanco"
                        class="text-[10px] font-bold uppercase tracking-wider text-primary hover:underline font-label"
                      >
                        Gerir catálogo
                      </RouterLink>
                      <span
                        class="px-2 py-0.5 rounded text-[9px] font-bold font-label"
                        :class="activeRulesCount(c) ? 'bg-primary text-on-primary' : 'bg-surface-container-high text-on-surface-variant'"
                      >
                        {{ activeRulesCount(c) }} nesta fase
                      </span>
                    </div>
                  </div>
                  <p class="text-xs text-on-surface-variant font-body mb-3 leading-relaxed">
                    Marque as regras cadastradas em <strong class="font-semibold text-on-surface">Governança de fluxo</strong> que bloqueiam o
                    avanço para esta fase. A validação no Kanban usa exatamente esta seleção.
                  </p>
                  <div
                    v-if="!catalogRulesForPhase().length"
                    class="text-xs text-on-surface-variant italic py-4 px-3 bg-surface-container-low rounded-lg"
                  >
                    Nenhuma regra ativa no catálogo. Crie regras em Regras de avanço ou aguarde a sincronização do servidor.
                  </div>
                  <div v-else class="max-h-64 overflow-y-auto space-y-2 pr-1 rounded-lg">
                    <label
                      v-for="gr in catalogRulesForPhase()"
                      :key="gr.id"
                      class="flex items-start gap-3 p-3 bg-surface-container-low rounded-lg border border-transparent hover:border-outline-variant/30 cursor-pointer transition-all"
                    >
                      <input
                        type="checkbox"
                        class="rounded border-outline text-primary focus:ring-primary mt-0.5 shrink-0"
                        :checked="(c.applied_rule_ids ?? []).includes(gr.id)"
                        :disabled="!canEdit || saving"
                        @change="toggleCatalogRule(c, gr.id, ($event.target as HTMLInputElement).checked)"
                      />
                      <span class="min-w-0 flex-1">
                        <span class="block text-sm font-bold text-on-surface font-headline leading-tight">{{ gr.name }}</span>
                        <span class="flex flex-wrap items-center gap-1.5 mt-0.5">
                          <span class="text-[10px] font-bold text-primary font-label uppercase tracking-tight">{{
                            ruleKeyShort(gr.rule_key)
                          }}</span>
                          <span
                            v-if="gr.on_violation === 'alerta'"
                            class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-secondary-container text-on-secondary-container font-label"
                            >Alerta</span
                          >
                        </span>
                        <span v-if="gr.description" class="block text-xs text-on-surface-variant mt-1 leading-snug">{{ gr.description }}</span>
                        <span
                          v-if="gr.rule_key === 'min_tag_count' && gr.min_tags_value != null"
                          class="block text-[10px] text-on-surface-variant mt-1 font-mono"
                          >Mín. {{ gr.min_tags_value }} tag(s)</span
                        >
                      </span>
                    </label>
                  </div>
                </div>

                <div class="md:col-span-4 min-w-0">
                  <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant font-label"
                      >Menus visíveis no detalhe do projeto</label
                    >
                    <span class="text-[10px] text-on-surface-variant font-label uppercase tracking-wider">
                      Conforme status/fase Kanban
                    </span>
                  </div>
                  <p class="text-xs text-on-surface-variant font-body mb-3 leading-relaxed">
                    Defina quais menus o utilizador pode ver quando o projeto estiver nesta fase.
                  </p>
                  <div class="space-y-1.5">
                    <div class="flex items-center justify-between gap-2 mb-1">
                      <span class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant font-label">Menus e ordem</span>
                      <span class="text-[10px] text-on-surface-variant font-body">Marque e reordene os ativos</span>
                    </div>
                    <div
                      v-for="tab in detailTabsUnifiedRowsForColumn(c)"
                      :key="`${c.id}-menu-${tab}`"
                      class="flex items-center justify-between gap-2 rounded-md bg-surface-container-low px-2.5 py-2 border border-outline-variant/20"
                      :class="isDetailTabVisible(c, tab) && canEdit && !saving ? 'cursor-grab active:cursor-grabbing' : ''"
                      :draggable="isDetailTabVisible(c, tab) && canEdit && !saving"
                      @dragstart="onDetailTabDragStart($event, tab, c)"
                      @dragover="onDetailTabDragOver($event)"
                      @drop="onDetailTabDrop(c, visibleDetailTabIndex(c, tab), $event)"
                    >
                      <label class="flex items-center gap-2 min-w-0 cursor-pointer">
                        <input
                          type="checkbox"
                          class="rounded border-outline text-primary focus:ring-primary shrink-0"
                          :checked="isDetailTabVisible(c, tab)"
                          :disabled="!canEdit || saving"
                          @change="toggleDetailTabVisibility(c, tab, ($event.target as HTMLInputElement).checked)"
                        />
                        <span class="material-symbols-outlined text-sm text-on-surface-variant">drag_indicator</span>
                        <span class="text-xs text-on-surface font-medium truncate">{{ detailTabLabel(tab) }}</span>
                      </label>
                      <div class="flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          class="p-0.5 text-on-surface-variant hover:text-primary disabled:opacity-30"
                          :disabled="
                            !canEdit ||
                            saving ||
                            !isDetailTabVisible(c, tab) ||
                            visibleDetailTabIndex(c, tab) <= 0
                          "
                          title="Mover para cima"
                          @click.stop="moveDetailTab(c, visibleDetailTabIndex(c, tab), visibleDetailTabIndex(c, tab) - 1)"
                        >
                          <span class="material-symbols-outlined text-sm">keyboard_arrow_up</span>
                        </button>
                        <button
                          type="button"
                          class="p-0.5 text-on-surface-variant hover:text-primary disabled:opacity-30"
                          :disabled="
                            !canEdit ||
                            saving ||
                            !isDetailTabVisible(c, tab) ||
                            visibleDetailTabIndex(c, tab) >= orderedDetailTabsForColumn(c).length - 1
                          "
                          title="Mover para baixo"
                          @click.stop="moveDetailTab(c, visibleDetailTabIndex(c, tab), visibleDetailTabIndex(c, tab) + 1)"
                        >
                          <span class="material-symbols-outlined text-sm">keyboard_arrow_down</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="md:col-span-1 flex md:flex-col justify-end gap-2">
                  <button
                    v-if="canEdit"
                    type="button"
                    class="p-2 text-on-surface-variant hover:text-error transition-colors"
                    @click.stop="deletePhase(c)"
                  >
                    <span class="material-symbols-outlined">delete</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div
            class="p-px bg-gradient-to-r from-primary via-primary-container to-tertiary-fixed rounded-xl overflow-hidden shadow-xl shadow-primary/5"
          >
            <div class="bg-surface-container-lowest p-6 flex flex-col sm:flex-row items-center justify-between gap-6">
              <div class="flex items-center gap-4">
                <div class="w-12 h-12 rounded-full bg-tertiary-fixed flex items-center justify-center shrink-0">
                  <span class="material-symbols-outlined text-primary-container" style="font-variation-settings: 'FILL' 1">bolt</span>
                </div>
                <div>
                  <h4 class="font-headline text-lg font-bold">Insight de governança</h4>
                  <p class="text-sm text-on-surface-variant font-body">
                    Fluxos de IA costumam incluir uma fase de avaliação após o desenvolvimento. Adicione uma etapa dedicada a ética e
                    conformidade.
                  </p>
                </div>
              </div>
              <button
                v-if="canEdit"
                type="button"
                class="px-5 py-2 bg-primary text-on-primary rounded-md text-sm font-bold whitespace-nowrap hover:opacity-90 transition-all shrink-0"
                :disabled="saving"
                @click="addPhaseTitled('Avaliação ética e conformidade')"
              >
                Adicionar fase sugerida
              </button>
            </div>
          </div>

          <button
            v-if="canEdit"
            type="button"
            class="w-full py-8 border-2 border-dashed border-outline-variant rounded-xl flex flex-col items-center justify-center gap-2 text-on-surface-variant hover:border-primary hover:text-primary transition-all group"
            :disabled="saving"
            @click="addPhase"
          >
            <div
              class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center group-hover:bg-primary group-hover:text-on-primary transition-all"
            >
              <span class="material-symbols-outlined">add</span>
            </div>
            <span class="font-bold tracking-tight font-headline">Adicionar nova fase</span>
          </button>
        </div>

        <div class="mt-10 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 text-[10px] font-bold uppercase tracking-[0.15em] text-outline font-label">
          <div class="flex flex-wrap gap-6">
            <span>Versão v{{ selected.version }}.0</span>
            <span>Editor: {{ auth.me?.email ?? "—" }}</span>
          </div>
          <div>
            <span :class="selected.status === 'publicado' ? 'text-on-tertiary-container' : 'text-on-surface-variant'">
              ● {{ selected.status === "publicado" ? "Template ativo" : "Rascunho ativo" }}
            </span>
          </div>
        </div>
      </div>

      <div v-else class="max-w-lg mx-auto text-center py-16 text-on-surface-variant font-body">
        <p class="mb-4">Template não encontrado ou sem permissão.</p>
        <button type="button" class="text-primary font-semibold underline" @click="backToLibrary">Voltar à biblioteca</button>
      </div>
    </template>

    <!-- Biblioteca (protótipo: gestão de templates) -->
    <template v-else>
      <div class="mb-4">
        <button
          type="button"
          class="inline-flex items-center gap-2 text-sm font-body font-medium text-on-surface-variant hover:text-primary transition-colors"
          @click="leaveTemplatesToPrevious"
        >
          <span class="material-symbols-outlined text-xl leading-none" aria-hidden="true">arrow_back</span>
          Voltar
        </button>
      </div>
      <div class="flex flex-col lg:flex-row lg:justify-between lg:items-end gap-6 mb-8">
        <div class="max-w-xl">
          <span class="text-[10px] font-extrabold uppercase tracking-widest text-on-surface-variant mb-1 block font-label"
            >Governance assets</span
          >
          <h2 class="text-3xl md:text-4xl font-headline font-extrabold tracking-tight text-on-surface">Templates de Kanban</h2>
          <p class="text-on-surface-variant mt-2 max-w-lg text-sm font-body leading-relaxed">
            Gerencie as estruturas dos fluxos de trabalho. Padronize a governança entre equipes.
          </p>
          <div class="mt-4 relative max-w-md">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg pointer-events-none"
              >search</span
            >
            <input
              v-model="searchQ"
              type="search"
              class="w-full bg-surface-container-low border-none rounded-lg pl-10 pr-4 py-2 text-sm focus:ring-1 focus:ring-primary h-10 font-body outline-none"
              placeholder="Procurar templates…"
            />
          </div>
        </div>
        <div class="flex flex-wrap gap-3 items-center">
          <button
            v-if="canEdit"
            type="button"
            class="flex items-center px-4 py-2.5 bg-surface-container-high text-on-surface font-semibold rounded-md hover:bg-surface-container-highest transition-colors text-sm font-body disabled:opacity-45"
            :disabled="!selected"
            @click="duplicateSelected"
          >
            <span class="material-symbols-outlined mr-2 text-lg">content_copy</span>
            Duplicar selecionado
          </button>
          <button
            v-if="canEdit"
            type="button"
            class="bg-primary text-on-primary px-6 py-3 rounded-md font-semibold flex items-center gap-2 hover:opacity-90 transition-all text-sm font-body shadow-md"
            @click="openNewModal"
          >
            <span class="material-symbols-outlined">add_circle</span>
            Novo template
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div class="bg-surface-container-low p-4 rounded-lg">
          <p class="text-[10px] font-bold uppercase text-on-surface-variant mb-1 font-label">Total de templates</p>
          <p class="text-2xl font-headline font-bold text-on-surface">{{ stats.total }}</p>
        </div>
        <div class="bg-surface-container-low p-4 rounded-lg border-l-4 border-tertiary-fixed">
          <p class="text-[10px] font-bold uppercase text-on-surface-variant mb-1 font-label">Status ativos</p>
          <p class="text-2xl font-headline font-bold text-on-surface">{{ stats.published }}</p>
        </div>
        <div class="bg-surface-container-low p-4 rounded-lg">
          <p class="text-[10px] font-bold uppercase text-on-surface-variant mb-1 font-label">Projetos governados</p>
          <p class="text-2xl font-headline font-bold text-on-surface">{{ stats.governed }}</p>
        </div>
        <div class="bg-surface-container-low p-4 rounded-lg">
          <p class="text-[10px] font-bold uppercase text-on-surface-variant mb-1 font-label">Última versão (máx.)</p>
          <p class="text-2xl font-headline font-bold text-on-surface">v{{ stats.maxVersion }}.0</p>
        </div>
      </div>

      <p v-if="msg" class="text-sm text-on-tertiary-container font-body">{{ msg }}</p>
      <p v-if="err" class="text-error text-sm font-body">{{ err }}</p>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div
          v-for="t in filteredItems"
          :key="t.id"
          role="button"
          tabindex="0"
          class="bg-surface-container-lowest p-6 rounded-xl transition-all group border hover:border-outline-variant/30 cursor-pointer"
          :class="[
            cardDimmed(t) ? 'opacity-80 md:opacity-90 md:grayscale hover:opacity-100 hover:grayscale-0' : '',
            selectedId === t.id
              ? 'border-primary ring-2 ring-primary/25 shadow-md'
              : 'border-transparent',
          ]"
          @click="selectTemplateCard(t)"
          @keydown.enter.prevent="selectTemplateCard(t)"
          @keydown.space.prevent="selectTemplateCard(t)"
        >
          <div class="flex justify-between items-start mb-6 gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-3 mb-1 flex-wrap">
                <h3 class="text-xl font-headline font-bold text-on-surface truncate">{{ t.name }}</h3>
                <span class="bg-surface-container text-on-surface-variant text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-tighter shrink-0"
                  >v{{ t.version }}.0</span
                >
              </div>
              <p class="text-sm text-on-surface-variant line-clamp-2 font-body">{{ templateDescriptionLine(t) }}</p>
            </div>
            <span class="text-[10px] font-bold px-3 py-1 rounded-full uppercase shrink-0" :class="statusPill(t.status).class">{{
              statusPill(t.status).label
            }}</span>
          </div>
          <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="flex items-center gap-3 text-sm">
              <div class="w-10 h-10 rounded-lg bg-surface-container-low flex items-center justify-center text-primary shrink-0">
                <span class="material-symbols-outlined">architecture</span>
              </div>
              <div class="min-w-0">
                <p class="text-[10px] text-on-surface-variant font-bold uppercase font-label">Metodologia</p>
                <p class="font-medium text-on-surface truncate font-body">{{ methodologyLine(t) }}</p>
              </div>
            </div>
            <div class="flex items-center gap-3 text-sm">
              <div class="w-10 h-10 rounded-lg bg-surface-container-low flex items-center justify-center text-primary shrink-0">
                <span class="material-symbols-outlined">layers</span>
              </div>
              <div class="min-w-0">
                <p class="text-[10px] text-on-surface-variant font-bold uppercase font-label">Projetos ativos</p>
                <p class="font-medium text-on-surface font-body">{{ projectCount(t.id) }} projeto(s)</p>
              </div>
            </div>
          </div>
          <div class="flex items-center justify-between pt-4 border-t border-surface-container-low gap-2 flex-wrap">
            <div class="flex gap-1">
              <button
                v-if="canEdit"
                type="button"
                class="text-on-surface-variant hover:text-primary transition-colors p-2 rounded-md hover:bg-surface-container-low"
                title="Editar dados"
                @click.stop="openEditMeta(t)"
              >
                <span class="material-symbols-outlined">edit</span>
              </button>
              <button
                v-if="canEdit"
                type="button"
                class="text-on-surface-variant hover:text-primary transition-colors p-2 rounded-md hover:bg-surface-container-low"
                title="Duplicar"
                @click.stop="duplicateTemplate(t)"
              >
                <span class="material-symbols-outlined">content_copy</span>
              </button>
              <button
                v-if="canEdit"
                type="button"
                class="text-on-surface-variant hover:text-error transition-colors p-2 rounded-md hover:bg-error-container/30"
                title="Excluir"
                @click.stop="openDeleteModal(t)"
              >
                <span class="material-symbols-outlined">delete</span>
              </button>
            </div>
            <button
              type="button"
              class="bg-surface-container-high text-on-surface text-xs font-bold px-4 py-2 rounded-md hover:bg-primary hover:text-on-primary transition-all flex items-center gap-2 font-label"
              @click.stop="goFluxo(t)"
            >
              Configurar fluxo
              <span class="material-symbols-outlined text-sm">settings_input_component</span>
            </button>
          </div>
        </div>

        <button
          v-if="canEdit"
          type="button"
          class="border-2 border-dashed border-outline-variant/40 rounded-xl flex flex-col items-center justify-center p-8 text-on-surface-variant hover:border-primary transition-all cursor-pointer bg-transparent hover:bg-surface-container-low min-h-[200px]"
          @click="openNewModal"
        >
          <span class="material-symbols-outlined text-4xl mb-3">add_box</span>
          <span class="text-sm font-bold uppercase tracking-widest font-label">Criar novo template</span>
        </button>
      </div>

      <div v-if="!filteredItems.length" class="text-center py-12 text-on-surface-variant font-body">Nenhum template encontrado.</div>

      <div class="mt-10 flex justify-center">
        <RouterLink
          to="/kanban"
          class="text-sm font-semibold text-primary hover:underline font-body inline-flex items-center gap-2"
        >
          <span class="material-symbols-outlined text-lg">view_kanban</span>
          Ver quadro Kanban
        </RouterLink>
      </div>
    </template>

    <!-- Modal: novo template -->
    <div
      v-if="showNewModal && canEdit"
      class="fixed inset-0 bg-primary-container/60 backdrop-blur-sm z-[60] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-tpl-title"
    >
      <div class="bg-surface-container-lowest w-full max-w-xl rounded-xl shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto">
        <div class="px-8 py-6 border-b border-surface-container-low flex justify-between items-center">
          <h2 id="new-tpl-title" class="text-2xl font-headline font-extrabold text-on-surface tracking-tight">Novo template de governança</h2>
          <button type="button" class="text-on-surface-variant hover:text-primary transition-colors p-1" aria-label="Fechar" @click="showNewModal = false">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
        <div class="p-8 space-y-6">
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label">Nome do template</label>
            <input
              v-model="newName"
              class="w-full bg-surface-container-low border-none rounded-md px-4 py-3 text-sm focus:ring-1 focus:ring-primary font-body"
              placeholder="Ex.: Operações lean de infraestrutura"
              type="text"
            />
          </div>
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label">Descrição executiva</label>
            <textarea
              v-model="newDescription"
              class="w-full bg-surface-container-low border-none rounded-md px-4 py-3 text-sm focus:ring-1 focus:ring-primary font-body"
              placeholder="Propósito e diretrizes deste fluxo…"
              rows="3"
            />
          </div>
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label">Metodologia base</label>
            <select
              v-model="newMethodology"
              class="w-full bg-surface-container-low border-none rounded-md px-4 py-3 text-sm focus:ring-1 focus:ring-primary appearance-none font-body"
            >
              <option v-for="opt in METHODOLOGY_OPTIONS" :key="opt" :value="opt">{{ opt }}</option>
            </select>
            <p class="text-[11px] text-on-surface-variant mt-2 font-body">
              As fases iniciais serão criadas automaticamente conforme o preset escolhido.
            </p>
          </div>
          <div class="flex justify-end gap-4 pt-4">
            <button
              type="button"
              class="px-6 py-2 text-sm font-bold text-on-surface-variant hover:text-primary transition-colors font-body"
              @click="showNewModal = false"
            >
              Cancelar
            </button>
            <button
              type="button"
              class="bg-primary text-on-primary px-8 py-2 rounded-md text-sm font-bold shadow-lg shadow-primary/20 font-body disabled:opacity-50"
              :disabled="saving"
              @click="createDraft"
            >
              Criar blueprint
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: editar metadados -->
    <div
      v-if="showEditMetaModal && canEdit"
      class="fixed inset-0 bg-primary-container/60 backdrop-blur-sm z-[60] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="bg-surface-container-lowest w-full max-w-xl rounded-xl shadow-2xl overflow-hidden">
        <div class="px-8 py-6 border-b border-surface-container-low flex justify-between items-center">
          <h2 class="text-xl font-headline font-extrabold text-on-surface">Editar template</h2>
          <button type="button" class="text-on-surface-variant hover:text-primary p-1" @click="showEditMetaModal = false">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
        <div class="p-8 space-y-4">
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label">Nome</label>
            <input v-model="metaDraftName" class="w-full bg-surface-container-low rounded-md px-4 py-3 text-sm border-none font-body" />
          </div>
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label">Descrição</label>
            <textarea v-model="metaDraftDescription" rows="3" class="w-full bg-surface-container-low rounded-md px-4 py-3 text-sm border-none font-body" />
          </div>
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2 font-label">Metodologia</label>
            <select v-model="metaDraftMethodology" class="w-full bg-surface-container-low rounded-md px-4 py-3 text-sm border-none font-body">
              <option v-for="opt in METHODOLOGY_OPTIONS" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
          <div class="flex justify-end gap-3 pt-4">
            <button type="button" class="px-4 py-2 text-sm font-bold text-on-surface-variant font-body" @click="showEditMetaModal = false">Cancelar</button>
            <button
              type="button"
              class="bg-primary text-on-primary px-6 py-2 rounded-md text-sm font-bold font-body disabled:opacity-50"
              :disabled="saving"
              @click="saveMetaDraft"
            >
              Guardar
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: exclusão -->
    <div
      v-if="showDeleteModal && pendingDeleteTpl"
      class="fixed inset-0 bg-primary-container/80 backdrop-blur-md z-[70] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="bg-surface-container-lowest max-w-sm w-full rounded-xl p-8 shadow-2xl text-center">
        <div class="w-16 h-16 bg-error-container rounded-full flex items-center justify-center mx-auto mb-6">
          <span class="material-symbols-outlined text-error text-3xl" style="font-variation-settings: 'FILL' 1">warning</span>
        </div>
        <h3 class="text-xl font-headline font-extrabold text-on-surface mb-2">Confirmar exclusão?</h3>
        <p class="text-sm text-on-surface-variant mb-8 font-body">
          Esta ação remove o template. Não é possível excluir se existirem projetos vinculados.
        </p>
        <div class="grid grid-cols-2 gap-4">
          <button
            type="button"
            class="bg-surface-container-high text-on-surface font-bold py-3 rounded-md hover:bg-surface-container-highest transition-colors font-body"
            @click="showDeleteModal = false; pendingDeleteTpl = null"
          >
            Abortar
          </button>
          <button
            type="button"
            class="bg-error text-on-error font-bold py-3 rounded-md hover:opacity-90 transition-colors font-body disabled:opacity-50"
            :disabled="saving"
            @click="confirmDeleteTemplate"
          >
            Sim, excluir
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
