<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { api } from "@/api/client";

export type ProjectTask = {
  id: number;
  project_id: number;
  title: string;
  description: string | null;
  column_key: string;
  priority: string;
  assignee: string | null;
  due_date: string | null;
  governance_aligned: boolean;
  position: number;
};

export type ProjectTaskColumn = {
  id: number;
  project_id: number;
  key: string;
  title: string;
  position: number;
  color_hex: string;
  is_done: boolean;
};

function normalizeHex(raw: string | undefined): string {
  const s = (raw || "").trim();
  if (/^#[0-9A-Fa-f]{6}$/.test(s)) return s.toLowerCase();
  if (/^[0-9A-Fa-f]{6}$/.test(s)) return `#${s.toLowerCase()}`;
  return "#64748b";
}

function columnDotStyle(c: ProjectTaskColumn) {
  return { backgroundColor: normalizeHex(c.color_hex) };
}

function normalizePriority(p: string): "high" | "medium" | "low" {
  if (p === "high" || p === "low" || p === "medium") return p;
  return "medium";
}

const props = defineProps<{
  projectId: number;
  projectName: string;
  canMutate: boolean;
}>();

const tasks = ref<ProjectTask[]>([]);
const boardColumns = ref<ProjectTaskColumn[]>([]);
const loading = ref(true);
const err = ref("");
const taskSearch = ref("");
const assigneeFilter = ref<string>("__all__");
const priorityFilter = ref<"all" | "high" | "medium" | "low">("all");

const showTaskModal = ref(false);
const editingTaskId = ref<number | null>(null);
const saving = ref(false);
const taskForm = ref({
  title: "",
  description: "",
  column_key: "todo",
  priority: "medium" as "high" | "medium" | "low",
  assignee: "",
  due_date: "",
  governance_aligned: false,
});

const dragTaskId = ref<number | null>(null);
const dragOverTaskId = ref<number | null>(null);

const sortedColumns = computed(() =>
  [...boardColumns.value].sort((a, b) => a.position - b.position || a.id - b.id),
);

function firstColumnKey(): string {
  return sortedColumns.value[0]?.key ?? "todo";
}

function resolveColumnKey(k: string): string {
  if (sortedColumns.value.some((c) => c.key === k)) return k;
  return firstColumnKey();
}

function taskEffectiveKey(t: ProjectTask): string {
  return resolveColumnKey(t.column_key);
}

function columnByKey(key: string): ProjectTaskColumn | undefined {
  return sortedColumns.value.find((c) => c.key === key);
}

const openColMenuId = ref<number | null>(null);
const showColumnModal = ref(false);
const editingColumnId = ref<number | null>(null);
const editingColumnKeyDisplay = ref("");
const savingColumn = ref(false);
const columnForm = ref({ title: "", color_hex: "#64748b", is_done: false });

async function loadBoard() {
  loading.value = true;
  err.value = "";
  try {
    const [taskList, colList] = await Promise.all([
      api<ProjectTask[]>(`/projects/${props.projectId}/tasks`),
      api<ProjectTaskColumn[]>(`/projects/${props.projectId}/task-columns`),
    ]);
    tasks.value = taskList;
    boardColumns.value = colList;
    if (!sortedColumns.value.some((c) => c.key === taskForm.value.column_key)) {
      taskForm.value.column_key = firstColumnKey();
    }
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao carregar o quadro";
    tasks.value = [];
    boardColumns.value = [];
  } finally {
    loading.value = false;
  }
}

function toggleColMenu(id: number) {
  openColMenuId.value = openColMenuId.value === id ? null : id;
}

function closeColMenu() {
  openColMenuId.value = null;
}

async function applyColumnOrder(ids: number[]) {
  if (!props.canMutate) return;
  err.value = "";
  try {
    await api<ProjectTaskColumn[]>(`/projects/${props.projectId}/task-columns/order`, {
      method: "PUT",
      body: JSON.stringify({ column_ids: ids }),
    });
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao reordenar raias";
  }
}

async function shiftColumn(col: ProjectTaskColumn, delta: number) {
  const ord = sortedColumns.value.map((c) => c.id);
  const i = ord.indexOf(col.id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= ord.length) {
    closeColMenu();
    return;
  }
  const next = [...ord];
  [next[i], next[j]] = [next[j], next[i]];
  closeColMenu();
  await applyColumnOrder(next);
}

function openNewColumnModal() {
  editingColumnId.value = null;
  editingColumnKeyDisplay.value = "";
  columnForm.value = { title: "", color_hex: "#64748b", is_done: false };
  showColumnModal.value = true;
  closeColMenu();
}

function openEditColumn(col: ProjectTaskColumn) {
  editingColumnId.value = col.id;
  editingColumnKeyDisplay.value = col.key;
  columnForm.value = {
    title: col.title,
    color_hex: normalizeHex(col.color_hex),
    is_done: col.is_done,
  };
  showColumnModal.value = true;
  closeColMenu();
}

function closeColumnModal() {
  showColumnModal.value = false;
  editingColumnId.value = null;
  editingColumnKeyDisplay.value = "";
}

async function submitColumnForm() {
  const f = columnForm.value;
  if (!f.title.trim()) return;
  savingColumn.value = true;
  err.value = "";
  try {
    if (editingColumnId.value != null) {
      await api<ProjectTaskColumn>(
        `/projects/${props.projectId}/task-columns/${editingColumnId.value}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            title: f.title.trim(),
            color_hex: f.color_hex,
            is_done: f.is_done,
          }),
        },
      );
    } else {
      await api<ProjectTaskColumn>(`/projects/${props.projectId}/task-columns`, {
        method: "POST",
        body: JSON.stringify({
          title: f.title.trim(),
          color_hex: f.color_hex,
          is_done: f.is_done,
        }),
      });
    }
    closeColumnModal();
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao guardar raia";
  } finally {
    savingColumn.value = false;
  }
}

async function deleteColumn(col: ProjectTaskColumn) {
  if (!props.canMutate) return;
  if (!confirm(`Excluir a raia «${col.title}»? As tarefas serão movidas para outra coluna.`)) return;
  closeColMenu();
  err.value = "";
  try {
    await api(`/projects/${props.projectId}/task-columns/${col.id}`, { method: "DELETE" });
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao excluir raia";
  }
}

onMounted(loadBoard);
watch(
  () => props.projectId,
  () => loadBoard(),
);

const assigneeOptions = computed(() => {
  const s = new Set<string>();
  for (const t of tasks.value) {
    const a = (t.assignee || "").trim();
    if (a) s.add(a);
  }
  return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
});

/** Até 3 responsáveis + contagem para a pilha do protótipo */
const assigneeStack = computed(() => {
  const all = assigneeOptions.value;
  return {
    visible: all.slice(0, 3),
    more: Math.max(0, all.length - 3),
  };
});

const filteredTasks = computed(() => {
  let list = tasks.value;
  const q = taskSearch.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        (t.description && t.description.toLowerCase().includes(q)),
    );
  }
  if (assigneeFilter.value !== "__all__") {
    const af = assigneeFilter.value;
    list = list.filter((t) => (t.assignee || "").trim() === af);
  }
  if (priorityFilter.value !== "all") {
    list = list.filter((t) => t.priority === priorityFilter.value);
  }
  return list;
});

function tasksInColumn(key: string) {
  return filteredTasks.value
    .filter((t) => taskEffectiveKey(t) === key)
    .slice()
    .sort((a, b) => a.position - b.position || a.id - b.id);
}

/** Todas as tarefas da raia (ignora filtros) — usado para persistir ordem correcta. */
function tasksInColumnRaw(columnKey: string): ProjectTask[] {
  return tasks.value
    .filter((t) => taskEffectiveKey(t) === columnKey)
    .slice()
    .sort((a, b) => a.position - b.position || a.id - b.id);
}

function countInColumn(key: string) {
  return tasks.value.filter((t) => taskEffectiveKey(t) === key).length;
}

function clearFilters() {
  taskSearch.value = "";
  assigneeFilter.value = "__all__";
  priorityFilter.value = "all";
}

function setAssigneeFilter(name: string | "__all__") {
  assigneeFilter.value = name;
}

function priorityLabel(p: string) {
  if (p === "high") return "Alta";
  if (p === "medium") return "Média";
  if (p === "low") return "Baixa";
  return p;
}

function priorityBadgeClass(p: string, col: ProjectTaskColumn) {
  if (col.is_done) {
    return "bg-tertiary-container text-on-tertiary-container";
  }
  if (p === "high") return "bg-error-container/50 text-on-error-container";
  if (p === "medium") return "bg-secondary-container text-on-secondary-container";
  return "bg-surface-container-highest text-on-surface-variant";
}

function dueLabelShort(due: string | null) {
  if (!due) return "—";
  const d = new Date(due + "T12:00:00");
  return d.toLocaleDateString("pt-BR", { day: "numeric", month: "short" });
}

function isOverdue(t: ProjectTask) {
  const col = columnByKey(t.column_key);
  if (!t.due_date || col?.is_done) return false;
  const d = new Date(t.due_date + "T12:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return d < today;
}

function pseudoProgress(id: number) {
  return 35 + (id % 46);
}

type StatusFoot = { icon: string; text: string; textClass: string };

function cardStatusFoot(t: ProjectTask, col: ProjectTaskColumn): StatusFoot {
  if (col.is_done) {
    return {
      icon: "check_circle",
      text: "Validado",
      textClass: "text-on-tertiary-container font-bold",
    };
  }
  if (col.key === "in_progress") {
    return {
      icon: "schedule",
      text: "Em progresso",
      textClass: "text-on-surface-variant font-medium",
    };
  }
  if (col.key === "review") {
    if (t.id % 2 === 0) {
      return {
        icon: "rate_review",
        text: "Aguardando aprovação",
        textClass: "text-on-surface-variant font-medium",
      };
    }
    return {
      icon: "visibility",
      text: "Em revisão",
      textClass: "text-on-surface-variant font-medium",
    };
  }
  if (isOverdue(t)) {
    return {
      icon: "event_busy",
      text: "Atrasado",
      textClass: "text-error font-medium",
    };
  }
  return {
    icon: "calendar_today",
    text: dueLabelShort(t.due_date),
    textClass: "text-on-surface-variant font-medium",
  };
}

const sovereignInsight = computed(() => {
  const reviewCol = sortedColumns.value.find((c) => c.key === "review");
  const todoCol = sortedColumns.value.find((c) => c.key === "todo");
  const progCol = sortedColumns.value.find((c) => c.key === "in_progress");
  const nReview = reviewCol ? countInColumn(reviewCol.key) : 0;
  const nTodo = todoCol ? countInColumn(todoCol.key) : 0;
  const nProgress = progCol ? countInColumn(progCol.key) : 0;
  if (reviewCol && nReview >= 2) {
    return {
      title: "Otimização de gargalo detectada",
      body: `A coluna ${reviewCol.title} concentra ${nReview} tarefa(s). Considere priorizar aprovações ou alocar um revisor adicional para não impactar a próxima sprint.`,
    };
  }
  if (todoCol && nTodo >= 4) {
    return {
      title: "Backlog operacional elevado",
      body: `Há ${nTodo} tarefa(s) em ${todoCol.title}. Vale revisar prioridades e capacidade do time em relação ao projeto ${props.projectName}.`,
    };
  }
  if (progCol && nProgress >= 3) {
    return {
      title: "Execução em ritmo intenso",
      body: `${nProgress} tarefa(s) em ${progCol.title}. Acompanhe dependências e prazos para manter previsibilidade nas entregas.`,
    };
  }
  return {
    title: "Panorama equilibrado",
    body: `O quadro do projeto ${props.projectName} está distribuído de forma saudável entre as colunas. Continue monitorando prazos e a fila de revisão.`,
  };
});

function initials(name: string | null) {
  const s = (name || "").trim();
  if (!s) return "?";
  const parts = s.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return s.slice(0, 2).toUpperCase();
}

function avatarClass(name: string | null) {
  const s = (name || "?").toLowerCase();
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  const palette = [
    "bg-primary-container text-on-primary-container",
    "bg-secondary-container text-on-secondary-container",
    "bg-tertiary-container text-on-tertiary-container",
    "bg-surface-container-high text-on-surface",
  ];
  return palette[Math.abs(h) % palette.length];
}

async function moveTask(taskId: number, columnKey: string) {
  if (!props.canMutate) return;
  try {
    await api<ProjectTask>(`/projects/${props.projectId}/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ column_key: columnKey }),
    });
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao mover";
  }
}

async function reorderInColumn(columnKey: string, orderedIds: number[]) {
  await api<ProjectTask[]>(`/projects/${props.projectId}/tasks/reorder`, {
    method: "PUT",
    body: JSON.stringify({ column_key: columnKey, task_ids: orderedIds }),
  });
}

function onDragStart(taskId: number, e: DragEvent) {
  if (!props.canMutate) return;
  dragTaskId.value = taskId;
  dragOverTaskId.value = null;
  try {
    e.dataTransfer?.setData("text/plain", String(taskId));
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  } catch {
    /* ignore */
  }
}

function onDragEnd() {
  dragTaskId.value = null;
  dragOverTaskId.value = null;
}

function onDragOverColumn(e: DragEvent) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onDragOverCard(e: DragEvent, taskId: number) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
  if (dragTaskId.value != null && dragTaskId.value !== taskId) {
    dragOverTaskId.value = taskId;
  }
}

async function onDropOnCard(target: ProjectTask, columnKey: string) {
  const draggedId = dragTaskId.value;
  dragTaskId.value = null;
  dragOverTaskId.value = null;
  if (draggedId == null || !props.canMutate) return;
  if (draggedId === target.id) return;
  const dragged = tasks.value.find((x) => x.id === draggedId);
  if (!dragged) return;
  const srcKey = taskEffectiveKey(dragged);
  let ids = tasksInColumnRaw(columnKey)
    .map((t) => t.id)
    .filter((id) => id !== draggedId);
  const ti = ids.indexOf(target.id);
  if (ti === -1) {
    ids.push(draggedId);
  } else {
    ids.splice(ti, 0, draggedId);
  }
  err.value = "";
  try {
    if (srcKey !== columnKey) {
      await api<ProjectTask>(`/projects/${props.projectId}/tasks/${draggedId}`, {
        method: "PATCH",
        body: JSON.stringify({ column_key: columnKey }),
      });
    }
    await reorderInColumn(columnKey, ids);
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao reordenar tarefas";
  }
}

async function onDropColumn(columnKey: string) {
  const draggedId = dragTaskId.value;
  dragTaskId.value = null;
  dragOverTaskId.value = null;
  if (draggedId == null || !props.canMutate) return;
  const dragged = tasks.value.find((x) => x.id === draggedId);
  if (!dragged) return;
  const srcKey = taskEffectiveKey(dragged);
  if (srcKey === columnKey) {
    let ids = tasksInColumnRaw(columnKey)
      .map((t) => t.id)
      .filter((id) => id !== draggedId);
    ids.push(draggedId);
    err.value = "";
    try {
      await reorderInColumn(columnKey, ids);
      await loadBoard();
    } catch (e) {
      err.value = e instanceof Error ? e.message : "Erro ao reordenar tarefas";
    }
    return;
  }
  await moveTask(draggedId, columnKey);
}

async function removeTask(taskId: number) {
  if (!props.canMutate || !confirm("Excluir esta tarefa?")) return;
  try {
    await api(`/projects/${props.projectId}/tasks/${taskId}`, { method: "DELETE" });
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao excluir";
  }
}

function resetTaskForm() {
  taskForm.value = {
    title: "",
    description: "",
    column_key: firstColumnKey(),
    priority: "medium",
    assignee: "",
    due_date: "",
    governance_aligned: false,
  };
}

function closeTaskModal() {
  showTaskModal.value = false;
  editingTaskId.value = null;
}

function openNewModal() {
  editingTaskId.value = null;
  resetTaskForm();
  showTaskModal.value = true;
}

function openEditTask(t: ProjectTask) {
  if (!props.canMutate) return;
  editingTaskId.value = t.id;
  taskForm.value = {
    title: t.title,
    description: t.description ?? "",
    column_key: resolveColumnKey(t.column_key),
    priority: normalizePriority(t.priority),
    assignee: t.assignee ?? "",
    due_date: t.due_date ? t.due_date.slice(0, 10) : "",
    governance_aligned: t.governance_aligned,
  };
  showTaskModal.value = true;
}

async function submitTask() {
  const f = taskForm.value;
  if (!f.title.trim()) return;
  saving.value = true;
  err.value = "";
  const id = editingTaskId.value;
  const body = {
    title: f.title.trim(),
    description: f.description.trim() || null,
    column_key: f.column_key,
    priority: f.priority,
    assignee: f.assignee.trim() || null,
    due_date: f.due_date.trim() || null,
    governance_aligned: f.governance_aligned,
  };
  try {
    if (id != null) {
      await api<ProjectTask>(`/projects/${props.projectId}/tasks/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    } else {
      await api<ProjectTask>(`/projects/${props.projectId}/tasks`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    }
    closeTaskModal();
    await loadBoard();
  } catch (e) {
    err.value = e instanceof Error ? e.message : id != null ? "Erro ao salvar" : "Erro ao criar";
  } finally {
    saving.value = false;
  }
}

function cardShellClass(col: ProjectTaskColumn) {
  if (col.is_done) {
    return "bg-surface-container-lowest/60 shadow-none border border-surface-container-highest";
  }
  if (col.key === "in_progress") {
    return "border-y border-r border-transparent border-l-4 bg-surface-container-lowest shadow-[0_2px_15px_-3px_rgba(0,0,0,0.04)] hover:border-outline-variant/30";
  }
  return "bg-surface-container-lowest shadow-[0_2px_15px_-3px_rgba(0,0,0,0.04)] border border-transparent hover:border-outline-variant/30";
}

function cardLeftBorderStyle(col: ProjectTaskColumn) {
  if (col.key !== "in_progress") return {};
  return { borderLeftColor: normalizeHex(col.color_hex) };
}
</script>

<template>
  <div class="w-full">
    <!-- Cabeçalho (protótipo) -->
    <div class="mb-6 flex flex-col justify-between gap-4 sm:mb-8 md:flex-row md:items-end">
      <div>
        <h2 class="font-headline text-3xl font-extrabold tracking-tight text-on-surface sm:text-4xl">
          Quadro de Tarefas do Projeto
        </h2>
        <p class="mt-2 text-base text-on-surface-variant font-body sm:text-lg">
          Gerenciamento operacional de sprints e entregáveis técnicos do projeto
          <strong class="text-on-surface">{{ projectName }}</strong
          >.
        </p>
        <p v-if="canMutate" class="mt-2 text-xs text-on-surface-variant font-body">
          Arraste um cartão sobre outro para o colocar antes dele na mesma raia; solte na área vazia da coluna para enviar para o fim.
          Arraste para outra raia para mudar de estado.
        </p>
      </div>
      <div v-if="canMutate" class="flex shrink-0 flex-wrap gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-xl border border-outline-variant/40 bg-surface-container-low px-5 py-2.5 text-sm font-semibold text-on-surface shadow-sm transition-all font-body hover:bg-surface-container-high active:scale-[0.98]"
          @click="openNewColumnModal"
        >
          <span class="material-symbols-outlined text-[20px]">view_week</span>
          Nova raia
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition-all font-body hover:opacity-90 active:scale-[0.98]"
          @click="openNewModal"
        >
          <span class="material-symbols-outlined text-[20px]">add</span>
          Nova Tarefa
        </button>
      </div>
    </div>

    <!-- Barra de filtros -->
    <div
      class="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-surface-container-low p-4 md:mb-8"
    >
      <div class="flex flex-wrap items-center gap-4">
        <div class="relative w-full min-w-[200px] sm:w-72">
          <span class="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-outline"
            >filter_list</span
          >
          <input
            v-model="taskSearch"
            type="search"
            placeholder="Filtrar por nome da tarefa..."
            class="w-full rounded-lg border-none bg-surface-container-lowest py-2 pl-10 pr-4 text-sm focus:ring-1 focus:ring-outline-variant font-body"
          />
        </div>
        <div v-if="assigneeOptions.length" class="flex items-center gap-2">
          <span class="mr-1 text-xs font-label uppercase tracking-tighter text-on-surface-variant">Responsável:</span>
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="rounded-full border-2 px-2 py-1 text-[10px] font-bold transition-all font-label"
              :class="
                assigneeFilter === '__all__'
                  ? 'border-primary bg-primary text-on-primary'
                  : 'border-surface-container-lowest bg-surface-container-high text-on-surface-variant hover:bg-surface-variant'
              "
              title="Todos"
              @click="setAssigneeFilter('__all__')"
            >
              Todos
            </button>
            <div class="flex -space-x-2">
              <button
                v-for="name in assigneeStack.visible"
                :key="name"
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-full border-2 border-surface-container-lowest text-[10px] font-bold transition-transform hover:z-10 hover:scale-110"
                :class="[avatarClass(name), assigneeFilter === name ? 'ring-2 ring-primary ring-offset-2' : '']"
                :title="name"
                @click="setAssigneeFilter(name)"
              >
                {{ initials(name) }}
              </button>
              <div
                v-if="assigneeStack.more > 0"
                class="flex h-8 w-8 items-center justify-center rounded-full border-2 border-surface-container-lowest bg-surface-container-high text-[10px] font-bold text-on-surface"
              >
                +{{ assigneeStack.more }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <span class="text-xs font-label uppercase tracking-tighter text-on-surface-variant">Prioridade:</span>
        <button
          type="button"
          class="rounded-full px-4 py-1.5 text-xs font-bold transition-opacity font-body"
          :class="
            priorityFilter === 'high'
              ? 'bg-error-container text-on-error-container'
              : 'bg-surface-container-highest text-on-surface-variant hover:opacity-80'
          "
          @click="priorityFilter = priorityFilter === 'high' ? 'all' : 'high'"
        >
          Alta
        </button>
        <button
          type="button"
          class="rounded-full px-4 py-1.5 text-xs font-bold transition-opacity font-body"
          :class="
            priorityFilter === 'medium'
              ? 'bg-secondary-container text-on-secondary-container'
              : 'bg-surface-container-highest text-on-surface-variant hover:opacity-80'
          "
          @click="priorityFilter = priorityFilter === 'medium' ? 'all' : 'medium'"
        >
          Média
        </button>
        <button
          type="button"
          class="rounded-full px-4 py-1.5 text-xs font-bold transition-opacity font-body"
          :class="
            priorityFilter === 'low'
              ? 'bg-surface-container-high text-on-surface font-semibold'
              : 'bg-surface-container-highest text-on-surface-variant hover:opacity-80'
          "
          @click="priorityFilter = priorityFilter === 'low' ? 'all' : 'low'"
        >
          Baixa
        </button>
        <button
          type="button"
          class="text-xs font-semibold text-primary underline-offset-2 hover:underline font-body"
          @click="clearFilters"
        >
          Limpar filtros
        </button>
      </div>
    </div>

    <p v-if="err" class="mb-4 text-sm text-error font-body">{{ err }}</p>
    <p v-if="loading" class="py-12 text-sm text-on-surface-variant font-body">Carregando quadro…</p>

    <div v-else class="overflow-x-auto pb-2 [-webkit-overflow-scrolling:touch]">
      <div
        class="grid w-full min-w-0 gap-4 sm:gap-6"
        :style="{
          gridTemplateColumns: `repeat(${Math.max(sortedColumns.length, 1)}, minmax(220px, 1fr))`,
        }"
      >
        <div
          v-for="col in sortedColumns"
          :key="col.id"
          class="flex min-h-[280px] min-w-0 flex-col gap-4"
          @dragover="onDragOverColumn"
          @drop="onDropColumn(col.key)"
        >
          <div class="flex items-center justify-between gap-1 px-2">
            <div class="flex min-w-0 items-center gap-2">
              <span class="h-2 w-2 shrink-0 rounded-full ring-1 ring-black/5" :style="columnDotStyle(col)" />
              <h3 class="min-w-0 truncate font-headline text-sm font-bold uppercase tracking-widest text-on-surface">
                {{ col.title }}
              </h3>
              <span
                class="shrink-0 rounded-full bg-surface-container px-2 py-0.5 text-xs font-medium text-on-surface-variant font-body"
              >
                {{ countInColumn(col.key) }}
              </span>
            </div>
            <div v-if="canMutate" class="relative shrink-0">
              <button
                type="button"
                class="material-symbols-outlined rounded p-1 text-outline hover:bg-surface-container-high hover:text-primary"
                aria-label="Menu da raia"
                @click="toggleColMenu(col.id)"
              >
                more_horiz
              </button>
              <div
                v-if="openColMenuId === col.id"
                role="menu"
                class="absolute right-0 z-30 mt-1 w-52 rounded-lg border border-outline-variant/20 bg-surface-container-lowest py-1 shadow-lg"
              >
                <button
                  type="button"
                  class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-body hover:bg-surface-container-high"
                  @click="openEditColumn(col)"
                >
                  <span class="material-symbols-outlined text-[18px]">edit</span>
                  Editar raia
                </button>
                <button
                  type="button"
                  class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-body hover:bg-surface-container-high"
                  @click="shiftColumn(col, -1)"
                >
                  <span class="material-symbols-outlined text-[18px]">west</span>
                  Mover para a esquerda
                </button>
                <button
                  type="button"
                  class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-body hover:bg-surface-container-high"
                  @click="shiftColumn(col, 1)"
                >
                  <span class="material-symbols-outlined text-[18px]">east</span>
                  Mover para a direita
                </button>
                <button
                  type="button"
                  class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-error font-body hover:bg-error-container/10"
                  @click="deleteColumn(col)"
                >
                  <span class="material-symbols-outlined text-[18px]">delete</span>
                  Excluir raia
                </button>
              </div>
            </div>
          </div>
          <div class="flex flex-col gap-4">
            <div
              v-for="t in tasksInColumn(col.key)"
              :key="t.id"
              :draggable="canMutate"
              class="group cursor-grab rounded-xl p-5 transition-shadow hover:shadow-md active:cursor-grabbing"
              :class="[
                cardShellClass(col),
                dragOverTaskId === t.id && dragTaskId != null && dragTaskId !== t.id
                  ? 'ring-2 ring-primary ring-offset-2 ring-offset-surface-container-lowest'
                  : '',
              ]"
              :style="cardLeftBorderStyle(col)"
              @dragstart="onDragStart(t.id, $event)"
              @dragend="onDragEnd"
              @dragover="onDragOverCard($event, t.id)"
              @drop.prevent.stop="onDropOnCard(t, col.key)"
              @click="canMutate ? openEditTask(t) : undefined"
            >
            <div class="mb-3 flex items-start justify-between gap-2">
              <span
                class="rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider font-label"
                :class="priorityBadgeClass(t.priority, col)"
              >
                {{ col.is_done ? "Concluído" : priorityLabel(t.priority) }}
              </span>
              <div class="flex items-center gap-0.5" @click.stop>
                <button
                  v-if="canMutate"
                  type="button"
                  class="material-symbols-outlined text-[18px] text-outline opacity-0 transition-opacity group-hover:opacity-100 hover:text-primary"
                  title="Editar"
                  @click="openEditTask(t)"
                >
                  edit_note
                </button>
                <button
                  v-if="canMutate"
                  type="button"
                  class="material-symbols-outlined text-[18px] text-outline opacity-0 transition-opacity group-hover:opacity-100 hover:text-error"
                  title="Excluir"
                  @click="removeTask(t.id)"
                >
                  delete
                </button>
              </div>
            </div>
            <h4
              class="mb-4 text-sm font-bold leading-tight text-on-surface font-body"
              :class="col.is_done ? 'text-on-surface/50 line-through' : ''"
            >
              {{ t.title }}
            </h4>

            <div v-if="col.key === 'in_progress'" class="mb-4">
              <div class="mb-1 flex justify-between text-[10px] font-bold text-on-surface-variant font-label">
                <span>Progresso</span>
                <span>{{ pseudoProgress(t.id) }}%</span>
              </div>
              <div class="h-1.5 w-full overflow-hidden rounded-full bg-surface-container">
                <div
                  class="h-full rounded-full"
                  :style="{
                    width: `${pseudoProgress(t.id)}%`,
                    backgroundColor: normalizeHex(col.color_hex),
                  }"
                />
              </div>
            </div>

            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 text-[11px] font-medium font-body" :class="cardStatusFoot(t, col).textClass">
                <span class="material-symbols-outlined text-[16px]">{{ cardStatusFoot(t, col).icon }}</span>
                {{ cardStatusFoot(t, col).text }}
              </div>
              <div class="flex items-center gap-2" @click.stop>
                <span
                  v-if="t.governance_aligned"
                  class="material-symbols-outlined text-[16px] text-tertiary-fixed-dim"
                  title="Alinhado à governança"
                  >verified_user</span
                >
                <span
                  v-else-if="t.description && t.description.length > 20"
                  class="material-symbols-outlined text-[16px] text-outline"
                  title="Com descrição"
                  >attach_file</span
                >
                <span
                  v-else-if="col.key === 'review' && t.id % 3 === 0"
                  class="material-symbols-outlined text-[16px] text-outline"
                  >link</span
                >
                <div
                  v-if="(t.assignee || '').trim()"
                  class="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold"
                  :class="avatarClass(t.assignee)"
                  :title="t.assignee || ''"
                >
                  {{ initials(t.assignee) }}
                </div>
                <select
                  v-if="canMutate"
                  class="max-w-[120px] rounded border border-outline-variant/20 bg-transparent py-0.5 pl-1 text-[10px] font-medium outline-none font-body"
                  :value="resolveColumnKey(t.column_key)"
                  @change="moveTask(t.id, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="c in sortedColumns" :key="c.key" :value="c.key">{{ c.title }}</option>
                </select>
              </div>
            </div>
          </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Sovereign Insight (protótipo) -->
    <div v-if="!loading" class="mt-10 rounded-xl bg-gradient-to-br from-slate-200 via-slate-100 to-slate-200 p-1">
      <div class="flex flex-col gap-4 rounded-[10px] bg-surface-container-lowest p-6 sm:flex-row sm:items-start sm:gap-6">
        <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary-container">
          <span class="material-symbols-outlined text-[28px] text-tertiary-fixed" style="font-variation-settings: 'FILL' 1"
            >psychology</span
          >
        </div>
        <div class="min-w-0 flex-1">
          <div class="mb-1 flex items-center gap-2">
            <span class="text-[10px] font-bold font-label uppercase tracking-[0.2em] text-primary">Sovereign Insight</span>
            <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-tertiary-fixed shadow-[0_0_8px_#6bff8f]" />
          </div>
          <h5 class="mb-2 font-headline text-lg font-bold text-on-surface">{{ sovereignInsight.title }}</h5>
          <p class="max-w-3xl text-sm leading-relaxed text-on-surface-variant font-body">{{ sovereignInsight.body }}</p>
        </div>
        <button
          type="button"
          class="shrink-0 self-start rounded-lg border border-outline-variant px-5 py-2 text-xs font-bold transition-colors font-body hover:bg-surface-container"
        >
          Ver relatório completo
        </button>
      </div>
    </div>

    <!-- Modal criar / editar -->
    <Teleport to="body">
      <div
        v-if="showTaskModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="closeTaskModal"
      >
        <div
          class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-xl"
        >
          <h4 class="text-lg font-bold font-headline">{{ editingTaskId != null ? "Editar tarefa" : "Nova tarefa" }}</h4>
          <form class="mt-4 space-y-3" @submit.prevent="submitTask">
            <label class="block text-sm font-body">
              <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Título</span>
              <input
                v-model="taskForm.title"
                required
                class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-container"
              />
            </label>
            <label class="block text-sm font-body">
              <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Descrição (opcional)</span>
              <textarea
                v-model="taskForm.description"
                rows="3"
                class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-container font-body"
              />
            </label>
            <div class="grid grid-cols-2 gap-3">
              <label class="block text-sm font-body">
                <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Coluna</span>
                <select
                  v-model="taskForm.column_key"
                  class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none"
                >
                  <option v-for="c in sortedColumns" :key="c.key" :value="c.key">{{ c.title }}</option>
                </select>
              </label>
              <label class="block text-sm font-body">
                <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Prioridade</span>
                <select
                  v-model="taskForm.priority"
                  class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none"
                >
                  <option value="high">Alta</option>
                  <option value="medium">Média</option>
                  <option value="low">Baixa</option>
                </select>
              </label>
            </div>
            <label class="block text-sm font-body">
              <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Responsável</span>
              <input
                v-model="taskForm.assignee"
                class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none"
                placeholder="Nome"
              />
            </label>
            <label class="block text-sm font-body">
              <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Prazo</span>
              <input
                v-model="taskForm.due_date"
                type="date"
                class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none"
              />
            </label>
            <label class="flex cursor-pointer items-center gap-2 text-sm font-body">
              <input v-model="taskForm.governance_aligned" type="checkbox" class="rounded border-outline-variant" />
              <span>Indicador de alinhamento à governança (ícone no cartão)</span>
            </label>
            <div class="flex justify-end gap-2 pt-2">
              <button
                type="button"
                class="rounded-lg px-4 py-2 text-sm font-medium text-on-surface-variant hover:bg-surface-container-high"
                @click="closeTaskModal"
              >
                Cancelar
              </button>
              <button
                type="submit"
                class="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
                :disabled="saving"
              >
                {{ saving ? "Salvando…" : editingTaskId != null ? "Salvar" : "Criar" }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showColumnModal"
        class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4 backdrop-blur-[2px]"
        role="dialog"
        aria-modal="true"
        @click.self="closeColumnModal"
      >
        <div
          class="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-xl"
        >
          <h4 class="text-lg font-bold font-headline">
            {{ editingColumnId != null ? "Editar raia" : "Nova raia" }}
          </h4>
          <p v-if="editingColumnId != null" class="mt-1 text-xs text-on-surface-variant font-body">
            Chave interna (não alterável):
            <code class="rounded bg-surface-container-high px-1">{{ editingColumnKeyDisplay }}</code>
          </p>
          <form class="mt-4 space-y-3" @submit.prevent="submitColumnForm">
            <label class="block text-sm font-body">
              <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Nome da raia</span>
              <input
                v-model="columnForm.title"
                required
                class="mt-1 w-full rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-container"
              />
            </label>
            <label class="block text-sm font-body">
              <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Cor do estado</span>
              <span class="mt-1 flex items-center gap-3">
                <input
                  v-model="columnForm.color_hex"
                  type="color"
                  class="h-10 w-14 cursor-pointer rounded border border-outline-variant/20 bg-transparent"
                />
                <input
                  v-model="columnForm.color_hex"
                  type="text"
                  pattern="#[0-9a-fA-F]{6}"
                  class="min-w-0 flex-1 rounded-lg border border-outline-variant/15 bg-surface-container-low px-3 py-2 font-mono text-sm outline-none"
                  placeholder="#3b82f6"
                />
              </span>
            </label>
            <label class="flex cursor-pointer items-center gap-2 text-sm font-body">
              <input v-model="columnForm.is_done" type="checkbox" class="rounded border-outline-variant" />
              <span>Tratar como coluna de conclusão (estilo de cartão concluído)</span>
            </label>
            <div class="flex justify-end gap-2 pt-2">
              <button
                type="button"
                class="rounded-lg px-4 py-2 text-sm font-medium text-on-surface-variant hover:bg-surface-container-high"
                @click="closeColumnModal"
              >
                Cancelar
              </button>
              <button
                type="submit"
                class="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
                :disabled="savingColumn"
              >
                {{ savingColumn ? "Salvando…" : editingColumnId != null ? "Guardar" : "Criar raia" }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>
