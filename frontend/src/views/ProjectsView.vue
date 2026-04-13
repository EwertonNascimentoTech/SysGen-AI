<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type Project = {
  id: number;
  name: string;
  product_owner: string;
  directory_name: string | null;
  methodology: string;
  current_column_title: string | null;
  planned_start: string;
  planned_end: string;
  ended_at: string | null;
  template_id: number;
  github_repo_url: string | null;
};

type TemplateOut = { id: number; name: string; status: string; version: number };

type WikiBrief = { documents?: unknown[]; status?: string | null };

const auth = useAuthStore();
const rows = ref<Project[]>([]);
const templateNames = ref<Record<number, string>>({});
const wikiFlags = ref<Record<number, boolean>>({});
const err = ref("");
const msg = ref("");
const showDeleteModal = ref(false);
const pendingDeleteProject = ref<Project | null>(null);
const deleting = ref(false);

const canDeleteProject = computed(() => auth.hasRole("admin", "coordenador"));

const q = ref("");
const filterDirectory = ref("");
const filterPo = ref("");
const filterMethodology = ref("");

const page = ref(1);
const pageSize = ref(10);
const selectedProjectId = ref<number | null>(null);

const selectedProjectRow = computed(() => rows.value.find((p) => p.id === selectedProjectId.value) ?? null);

const directoryOptions = computed(() => {
  const s = new Set<string>();
  for (const p of rows.value) {
    if (p.directory_name) s.add(p.directory_name);
  }
  return [...s].sort();
});

const poOptions = computed(() => {
  const s = new Set<string>();
  for (const p of rows.value) s.add(p.product_owner);
  return [...s].sort();
});

const filtered = computed(() => {
  let list = rows.value;
  const term = q.value.trim().toLowerCase();
  if (term) {
    list = list.filter(
      (p) =>
        p.name.toLowerCase().includes(term) ||
        p.product_owner.toLowerCase().includes(term) ||
        (p.directory_name ?? "").toLowerCase().includes(term),
    );
  }
  if (filterDirectory.value) list = list.filter((p) => p.directory_name === filterDirectory.value);
  if (filterPo.value) list = list.filter((p) => p.product_owner === filterPo.value);
  if (filterMethodology.value) list = list.filter((p) => p.methodology === filterMethodology.value);
  return list;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filtered.value.slice(start, start + pageSize.value);
});

const rangeLabel = computed(() => {
  const total = filtered.value.length;
  if (total === 0) return "Nenhum projeto";
  const start = (page.value - 1) * pageSize.value + 1;
  const end = Math.min(page.value * pageSize.value, total);
  return `Exibindo ${start} a ${end} de ${total} projeto${total === 1 ? "" : "s"}`;
});

const portfolioHealth = computed(() => {
  const list = filtered.value;
  if (!list.length) return { pct: "—", delta: "", sub: "Cadastre projetos para acompanhar a governança." };
  let ok = 0;
  for (const p of list) {
    const st = rowStatus(p);
    if (st.label === "Saudável") ok++;
  }
  const pct = ((ok / list.length) * 100).toFixed(1);
  return {
    pct,
    delta: ok === list.length ? "+0%" : "",
    sub: `Monitorando ${list.length} projeto${list.length === 1 ? "" : "s"} no filtro atual.`,
  };
});

watch(pageSize, () => {
  page.value = 1;
});

watch([filterDirectory, filterPo, filterMethodology, q], () => {
  page.value = 1;
});

watch(filtered, () => {
  const t = Math.max(1, Math.ceil(filtered.value.length / pageSize.value));
  if (page.value > t) page.value = t;
});

watch(rows, (list) => {
  if (selectedProjectId.value != null && !list.some((p) => p.id === selectedProjectId.value)) {
    selectedProjectId.value = null;
  }
});

function selectProjectRow(id: number) {
  selectedProjectId.value = id;
}

function clearSelectedProject() {
  selectedProjectId.value = null;
}

function openDeleteProject(p: Project) {
  pendingDeleteProject.value = p;
  showDeleteModal.value = true;
  err.value = "";
}

async function confirmDeleteProject() {
  const p = pendingDeleteProject.value;
  if (!p || !canDeleteProject.value) return;
  deleting.value = true;
  err.value = "";
  try {
    await api(`/projects/${p.id}`, { method: "DELETE" });
    rows.value = rows.value.filter((x) => x.id !== p.id);
    if (selectedProjectId.value === p.id) selectedProjectId.value = null;
    msg.value = `Projeto "${p.name}" foi excluído.`;
    showDeleteModal.value = false;
    pendingDeleteProject.value = null;
    void loadWikiFlags(rows.value);
    window.setTimeout(() => {
      msg.value = "";
    }, 4000);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Não foi possível excluir.";
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  try {
    const [projs, tpls] = await Promise.all([api<Project[]>("/projects"), api<TemplateOut[]>("/kanban-templates")]);
    rows.value = projs;
    for (const t of tpls) templateNames.value[t.id] = t.name;
    void loadWikiFlags(projs);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
});

async function loadWikiFlags(projects: Project[]) {
  wikiFlags.value = {};
  if (projects.length > 40) {
    for (const p of projects) wikiFlags.value[p.id] = false;
    return;
  }
  await Promise.all(
    projects.map(async (p) => {
      try {
        const w = await api<WikiBrief>(`/projects/${p.id}/wiki`);
        wikiFlags.value[p.id] = !!(w.documents?.length && w.status === "ready");
      } catch {
        wikiFlags.value[p.id] = false;
      }
    }),
  );
}

function methodologyLabel(m: string) {
  if (m === "base44") return "Base 44";
  if (m === "prd") return "PRD";
  return m;
}

function projectCode(p: Project) {
  const y = new Date().getFullYear();
  return `PRJ-${y}-${String(p.id).padStart(3, "0")}`;
}

function poInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase() || "PO";
}

function poShort(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "—";
  if (parts.length === 1) return parts[0].slice(0, 10);
  return `${parts[0]} ${parts[parts.length - 1][0]}.`;
}

const today = new Date();
today.setHours(0, 0, 0, 0);

function rowStatus(p: Project) {
  if (p.ended_at) {
    return {
      label: "Encerrado",
      pillClass: "bg-outline-variant text-on-surface",
      dotClass: "bg-on-surface",
    };
  }
  const end = new Date(p.planned_end + "T12:00:00");
  if (end < today) {
    return {
      label: "Atrasado",
      pillClass: "bg-error-container text-on-error-container",
      dotClass: "bg-on-error-container",
    };
  }
  const col = (p.current_column_title ?? "").toLowerCase();
  if (
    col.includes("backlog") ||
    col.includes("espera") ||
    col.includes("concepção") ||
    col.includes("concepcao")
  ) {
    return {
      label: "Em espera",
      pillClass: "bg-secondary-container text-on-secondary-container",
      dotClass: "bg-on-secondary-container",
    };
  }
  return {
    label: "Saudável",
    pillClass: "bg-tertiary-container text-on-tertiary-container",
    dotClass: "bg-on-tertiary-container",
  };
}

function avatarClass(i: number) {
  const r = i % 3;
  if (r === 0) return "bg-secondary-container text-on-secondary-container";
  if (r === 1) return "bg-primary-fixed text-on-primary-fixed";
  return "bg-secondary-fixed text-on-secondary-fixed";
}

function clearFilters() {
  q.value = "";
  filterDirectory.value = "";
  filterPo.value = "";
  filterMethodology.value = "";
}

function exportCsv() {
  const header = ["Nome", "ID", "Diretoria", "PO", "Metodologia", "Template", "Status Kanban", "Prazo fim"];
  const lines = [header.join(";"), ...filtered.value.map((p) =>
    [
      `"${p.name.replace(/"/g, '""')}"`,
      projectCode(p),
      p.directory_name ?? "",
      `"${p.product_owner.replace(/"/g, '""')}"`,
      methodologyLabel(p.methodology),
      templateNames.value[p.template_id] ?? String(p.template_id),
      p.current_column_title ?? "",
      p.planned_end,
    ].join(";"),
  )];
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `projetos-governanca-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function pageNumbers(): (number | string)[] {
  const t = totalPages.value;
  const p = page.value;
  if (t <= 5) return Array.from({ length: t }, (_, i) => i + 1);
  const set = new Set<number>();
  set.add(1);
  set.add(t);
  set.add(p);
  if (p > 1) set.add(p - 1);
  if (p < t) set.add(p + 1);
  const arr = [...set].filter((n) => n >= 1 && n <= t).sort((a, b) => a - b);
  const out: (number | string)[] = [];
  for (let i = 0; i < arr.length; i++) {
    if (i > 0 && arr[i] - arr[i - 1] > 1) out.push("…");
    out.push(arr[i]);
  }
  return out;
}

function goToPage(item: number | string) {
  if (typeof item === "number") page.value = item;
}
</script>

<template>
  <div class="space-y-6 -mx-2 md:-mx-4">
    <!-- Cabeçalho (protótipo gest_o_de_projetos_pt_br) -->
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4 px-2 md:px-4">
      <div>
        <span class="text-[10px] font-bold tracking-[0.2em] text-on-surface-variant uppercase block mb-1 font-label"
          >Workspace de governança</span
        >
        <h1 class="text-4xl font-extrabold font-headline tracking-tight text-on-surface">Listagem de projetos</h1>
        <p class="text-sm text-on-surface-variant mt-2 font-body max-w-xl">
          Clique em qualquer célula da linha para selecionar o projeto; a linha e o painel acima da tabela mostram o destaque.
        </p>
      </div>
      <RouterLink
        to="/projetos/novo"
        class="bg-primary text-on-primary px-6 py-2.5 rounded-md font-semibold flex items-center gap-2 hover:opacity-90 transition-opacity font-body shrink-0"
      >
        <span class="material-symbols-outlined text-lg">add</span>
        Novo projeto
      </RouterLink>
    </div>

    <p v-if="err" class="text-error text-sm font-body px-2 md:px-4">{{ err }}</p>
    <p v-if="msg" class="text-on-tertiary-container text-sm font-body px-2 md:px-4">{{ msg }}</p>

    <!-- Filtros -->
    <div class="bg-surface-container-low rounded-xl p-4 flex flex-wrap items-center gap-4 px-2 md:px-4">
      <div class="flex items-center gap-2 flex-1 min-w-[200px] bg-surface-container-lowest px-3 py-2 rounded border border-outline-variant/10">
        <span class="material-symbols-outlined text-outline text-lg shrink-0">search</span>
        <input
          v-model="q"
          class="bg-transparent border-none text-sm font-body focus:ring-0 p-0 w-full outline-none placeholder:text-outline"
          placeholder="Buscar por nome, PO ou diretoria…"
          type="search"
        />
      </div>
      <div class="flex items-center gap-2 bg-surface-container-lowest px-3 py-2 rounded border border-outline-variant/10">
        <label class="text-[10px] font-bold text-outline uppercase tracking-wider font-label whitespace-nowrap">Diretoria</label>
        <select v-model="filterDirectory" class="bg-transparent border-none text-xs font-semibold focus:ring-0 p-0 pr-6 font-body max-w-[160px]">
          <option value="">Todos os departamentos</option>
          <option v-for="d in directoryOptions" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="flex items-center gap-2 bg-surface-container-lowest px-3 py-2 rounded border border-outline-variant/10">
        <label class="text-[10px] font-bold text-outline uppercase tracking-wider font-label whitespace-nowrap">PO</label>
        <select v-model="filterPo" class="bg-transparent border-none text-xs font-semibold focus:ring-0 p-0 pr-6 font-body max-w-[180px]">
          <option value="">Qualquer proprietário</option>
          <option v-for="po in poOptions" :key="po" :value="po">{{ po }}</option>
        </select>
      </div>
      <div class="flex items-center gap-2 bg-surface-container-lowest px-3 py-2 rounded border border-outline-variant/10">
        <label class="text-[10px] font-bold text-outline uppercase tracking-wider font-label whitespace-nowrap">Metodologia</label>
        <select v-model="filterMethodology" class="bg-transparent border-none text-xs font-semibold focus:ring-0 p-0 pr-6 font-body">
          <option value="">Todos os frameworks</option>
          <option value="base44">Base 44</option>
          <option value="prd">PRD</option>
        </select>
      </div>
      <div class="ml-auto flex items-center gap-2 flex-wrap">
        <button
          type="button"
          class="text-xs font-bold text-on-surface-variant hover:text-primary flex items-center gap-1 px-3 py-2 font-label"
          @click="clearFilters"
        >
          <span class="material-symbols-outlined text-sm">filter_list</span>
          Limpar
        </button>
        <div class="h-4 w-px bg-outline-variant/30 mx-1 hidden sm:block" />
        <button
          type="button"
          class="text-xs font-bold text-on-surface hover:text-primary flex items-center gap-1 px-3 py-2 font-label"
          @click="exportCsv"
        >
          <span class="material-symbols-outlined text-sm">download</span>
          Exportar
        </button>
      </div>
    </div>

    <div
      v-if="selectedProjectRow"
      class="mx-2 md:mx-4 flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 rounded-xl bg-primary/10 border-2 border-primary/30 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <span class="material-symbols-outlined text-primary text-2xl shrink-0" aria-hidden="true">bookmark</span>
      <div class="min-w-0 flex-1">
        <span class="text-[10px] font-bold uppercase text-on-surface-variant tracking-wider font-label block">Projeto selecionado</span>
        <span class="font-headline font-bold text-on-surface text-base block truncate">{{ selectedProjectRow.name }}</span>
        <span class="text-xs text-on-surface-variant font-mono">{{ projectCode(selectedProjectRow) }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2 shrink-0">
        <RouterLink
          :to="`/projetos/${selectedProjectRow.id}`"
          class="px-3 py-1.5 rounded-md bg-primary text-on-primary text-xs font-bold font-body hover:opacity-90"
        >
          Abrir detalhe
        </RouterLink>
        <RouterLink
          :to="`/kanban?project_id=${selectedProjectRow.id}`"
          class="px-3 py-1.5 rounded-md bg-surface-container-high text-on-surface text-xs font-bold font-body hover:bg-surface-container-highest"
        >
          Kanban
        </RouterLink>
        <button
          type="button"
          class="px-3 py-1.5 rounded-md text-xs font-bold text-on-surface-variant hover:text-on-surface font-body border border-outline-variant/30"
          @click.stop="clearSelectedProject"
        >
          Limpar seleção
        </button>
      </div>
    </div>

    <!-- Tabela -->
    <div class="bg-surface-container-low rounded-xl overflow-hidden mx-2 md:mx-4">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-separate border-spacing-y-2 px-4 min-w-[900px]">
          <thead>
            <tr class="text-[10px] font-bold text-outline uppercase tracking-widest font-label">
              <th class="py-4 pl-4">Nome &amp; ID</th>
              <th class="py-4">Diretoria</th>
              <th class="py-4">PO</th>
              <th class="py-4">Metodologia</th>
              <th class="py-4">Template</th>
              <th class="py-4">Status</th>
              <th class="py-4 text-center">Docs</th>
              <th class="py-4 text-right pr-4">Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(p, idx) in pagedRows"
              :key="p.id"
              class="transition-colors group cursor-pointer"
              :class="
                selectedProjectId === p.id
                  ? 'bg-primary/[0.08] ring-2 ring-inset ring-primary/45 shadow-inner'
                  : 'bg-surface-container-lowest hover:bg-white'
              "
              :aria-selected="selectedProjectId === p.id"
              role="row"
              @click="selectProjectRow(p.id)"
            >
              <td
                class="py-4 pl-4 rounded-l-lg border-l-4 transition-all"
                :class="
                  selectedProjectId === p.id ? 'border-primary' : 'border-transparent group-hover:border-primary'
                "
              >
                <div class="flex flex-col">
                  <RouterLink
                    :to="`/kanban?project_id=${p.id}`"
                    class="text-sm font-bold text-on-surface hover:underline font-body"
                  >
                    {{ p.name }}
                  </RouterLink>
                  <span class="text-[10px] text-outline tracking-tighter font-mono">{{ projectCode(p) }}</span>
                </div>
              </td>
              <td class="py-4">
                <span class="text-xs font-medium text-on-surface-variant font-body">{{ p.directory_name ?? "—" }}</span>
              </td>
              <td class="py-4">
                <div class="flex items-center gap-2">
                  <div
                    class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
                    :class="avatarClass(idx)"
                  >
                    {{ poInitials(p.product_owner) }}
                  </div>
                  <span class="text-xs font-medium font-body">{{ poShort(p.product_owner) }}</span>
                </div>
              </td>
              <td class="py-4">
                <span
                  class="text-xs px-2 py-1 bg-surface-container text-on-surface-variant rounded text-[10px] font-bold uppercase tracking-wide font-label"
                  >{{ methodologyLabel(p.methodology) }}</span
                >
              </td>
              <td class="py-4">
                <span class="text-xs text-on-surface-variant italic font-body">{{
                  templateNames[p.template_id] ?? "—"
                }}</span>
              </td>
              <td class="py-4">
                <span
                  class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold font-label"
                  :class="rowStatus(p).pillClass"
                >
                  <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="rowStatus(p).dotClass" />
                  {{ rowStatus(p).label }}
                </span>
              </td>
              <td class="py-4">
                <div class="flex justify-center gap-3">
                  <span
                    class="material-symbols-outlined text-lg"
                    :class="p.github_repo_url ? 'text-primary' : 'text-outline-variant'"
                    :title="p.github_repo_url ? 'GitHub vinculado' : 'GitHub ausente'"
                    >hub</span
                  >
                  <span
                    class="material-symbols-outlined text-lg"
                    :class="wikiFlags[p.id] ? 'text-tertiary-fixed-dim' : 'text-outline-variant'"
                    :style="wikiFlags[p.id] ? 'font-variation-settings: \'FILL\' 1' : undefined"
                    :title="wikiFlags[p.id] ? 'Wiki pronta' : 'Wiki ausente ou pendente'"
                    >description</span
                  >
                </div>
              </td>
              <td class="py-4 pr-4 text-right rounded-r-lg">
                <div class="flex items-center justify-end gap-1">
                  <RouterLink
                    :to="`/projetos/${p.id}`"
                    class="p-1.5 hover:bg-surface-container-low rounded transition-colors inline-flex"
                    title="Visualizar"
                  >
                    <span class="material-symbols-outlined text-lg text-outline">visibility</span>
                  </RouterLink>
                  <RouterLink
                    :to="`/projetos/${p.id}`"
                    class="p-1.5 hover:bg-surface-container-low rounded transition-colors inline-flex"
                    title="Editar no detalhe"
                  >
                    <span class="material-symbols-outlined text-lg text-outline">edit</span>
                  </RouterLink>
                  <RouterLink
                    :to="`/kanban?project_id=${p.id}`"
                    class="p-1.5 hover:bg-surface-container-low rounded transition-colors inline-flex"
                    title="Kanban"
                  >
                    <span class="material-symbols-outlined text-lg text-outline">view_kanban</span>
                  </RouterLink>
                  <button
                    v-if="canDeleteProject"
                    type="button"
                    class="p-1.5 hover:bg-error-container/40 rounded transition-colors inline-flex text-outline hover:text-error"
                    title="Excluir projeto"
                    @click.stop="openDeleteProject(p)"
                  >
                    <span class="material-symbols-outlined text-lg">delete</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="!err && filtered.length === 0 && rows.length === 0" class="px-6 py-12 text-center text-on-surface-variant text-sm font-body">
        Carregando…
      </div>
      <div v-else-if="!err && filtered.length === 0" class="px-6 py-12 text-center text-on-surface-variant text-sm font-body">
        Nenhum projeto corresponde aos filtros.
      </div>

      <!-- Rodapé paginação -->
      <div class="px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-4 bg-surface-container-low/50 border-t border-outline-variant/10">
        <div class="flex flex-wrap items-center gap-4">
          <span class="text-xs text-on-surface-variant font-body">{{ rangeLabel }}</span>
          <div class="h-4 w-px bg-outline-variant/30 hidden sm:block" />
          <div class="flex items-center gap-2">
            <label class="text-[10px] font-bold text-outline uppercase font-label">Exibir</label>
            <select v-model.number="pageSize" class="bg-transparent border-none text-xs font-bold focus:ring-0 p-0 font-body">
              <option :value="10">10</option>
              <option :value="25">25</option>
              <option :value="50">50</option>
            </select>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <button
            type="button"
            class="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-container transition-colors disabled:opacity-30"
            :disabled="page <= 1"
            @click="page--"
          >
            <span class="material-symbols-outlined text-sm">chevron_left</span>
          </button>
          <template v-for="(item, i) in pageNumbers()" :key="`${item}-${i}`">
            <span v-if="item === '…'" class="px-1 text-xs font-bold text-on-surface-variant">…</span>
            <button
              v-else
              type="button"
              class="w-8 h-8 flex items-center justify-center rounded font-bold text-xs transition-colors"
              :class="item === page ? 'bg-primary text-on-primary' : 'hover:bg-surface-container text-on-surface'"
              @click="goToPage(item)"
            >
              {{ item }}
            </button>
          </template>
          <button
            type="button"
            class="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-container transition-colors disabled:opacity-30"
            :disabled="page >= totalPages"
            @click="page++"
          >
            <span class="material-symbols-outlined text-sm">chevron_right</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Insight + saúde -->
    <div class="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-6 px-2 md:px-4 pb-8">
      <div
        class="lg:col-span-2 p-6 rounded-xl bg-gradient-to-br from-primary-container to-slate-800 text-white shadow-xl relative overflow-hidden group"
      >
        <div class="absolute -right-12 -top-12 w-48 h-48 bg-tertiary/10 rounded-full blur-3xl group-hover:scale-110 transition-transform duration-700" />
        <div class="relative z-10">
          <div class="flex items-center gap-2 mb-4">
            <span class="material-symbols-outlined text-tertiary-fixed">bolt</span>
            <span class="text-[10px] font-bold uppercase tracking-[0.2em] text-tertiary-fixed font-label">Insight de governança IA</span>
          </div>
          <h3 class="text-xl font-bold font-headline mb-2 tracking-tight">Análise do portfólio filtrado</h3>
          <p class="text-sm text-primary-fixed/80 leading-relaxed max-w-xl font-body">
            Priorize projetos <strong class="text-white">atrasados</strong> e sem Wiki pronta. Vincule o GitHub e gere documentação a partir da pasta
            <code class="text-tertiary-fixed/90">docs/</code> no detalhe de cada projeto.
          </p>
          <div class="mt-6 flex flex-wrap gap-4">
            <RouterLink
              to="/projetos/novo"
              class="px-4 py-2 bg-white/10 hover:bg-white/20 backdrop-blur rounded text-xs font-bold transition-colors font-label"
            >
              Novo projeto
            </RouterLink>
            <RouterLink to="/" class="px-4 py-2 text-tertiary-fixed text-xs font-bold hover:underline font-label"> Ir ao painel → </RouterLink>
          </div>
        </div>
      </div>
      <div class="p-6 rounded-xl bg-surface-container-lowest shadow-sm border border-outline-variant/10 flex flex-col justify-center editorial-shadow">
        <span class="text-[10px] font-bold uppercase text-outline mb-1 font-label">Saúde do filtro</span>
        <div class="flex items-baseline gap-2 mb-4">
          <span class="text-4xl font-extrabold font-headline tracking-tighter text-on-surface">{{ portfolioHealth.pct }}%</span>
          <span v-if="portfolioHealth.delta" class="text-xs text-on-tertiary-container font-bold font-body">{{ portfolioHealth.delta }}</span>
        </div>
        <div class="w-full bg-surface-container h-1 rounded-full overflow-hidden">
          <div
            class="bg-on-tertiary-container h-full transition-all"
            :style="{ width: portfolioHealth.pct === '—' ? '0%' : `${Math.min(100, Number(portfolioHealth.pct))}%` }"
          />
        </div>
        <p class="text-[10px] text-outline-variant mt-4 leading-tight italic font-body">
          {{ portfolioHealth.sub }}
        </p>
      </div>
    </div>

    <div
      v-if="showDeleteModal && pendingDeleteProject"
      class="fixed inset-0 bg-primary-container/70 backdrop-blur-sm z-[70] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="bg-surface-container-lowest max-w-md w-full rounded-xl p-8 shadow-2xl text-center border border-outline-variant/10">
        <div class="w-16 h-16 bg-error-container rounded-full flex items-center justify-center mx-auto mb-6">
          <span class="material-symbols-outlined text-error text-3xl" style="font-variation-settings: 'FILL' 1">warning</span>
        </div>
        <h3 class="text-xl font-headline font-extrabold text-on-surface mb-2">Excluir projeto?</h3>
        <p class="text-sm text-on-surface-variant mb-2 font-body">
          <strong class="text-on-surface">{{ pendingDeleteProject.name }}</strong> será removido com anexos, wiki e vínculos ao Cursor Hub. Esta
          ação não pode ser desfeita.
        </p>
        <div class="grid grid-cols-2 gap-4 mt-8">
          <button
            type="button"
            class="bg-surface-container-high text-on-surface font-bold py-3 rounded-md hover:bg-surface-container-highest transition-colors font-body"
            :disabled="deleting"
            @click="showDeleteModal = false; pendingDeleteProject = null"
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
