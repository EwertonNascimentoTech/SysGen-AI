<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from "vue";

type PlanejPath = (string | number)[];

export type PlanejTreeRow = {
  pathKey: string;
  path: PlanejPath;
  label: string;
  preview: string;
  depth: number;
  hasChildren: boolean;
};

type PhaseBlock = {
  pathKey: string;
  path: PlanejPath;
  titulo: string;
  pct: number;
  items: PhaseItem[];
  dotClass: string;
  /** Bloco antes das fases de entrega (Cursor, ambiente, arquitetura). */
  kind: "preparation" | "feature";
};

type PhaseItem = {
  pathKey: string;
  path: PlanejPath;
  titulo: string;
  status: string;
};

const props = defineProps<{
  parsed: unknown | null;
  treeRows: PlanejTreeRow[];
  expanded: Record<string, boolean>;
  selectedPathKey: string | null;
  detailJson: string;
}>();

const emit = defineEmits<{
  select: [pathKey: string];
  "toggle-expand": [pathKey: string, ev: MouseEvent];
  "close-detail": [];
}>();

const detailTitleId = useId();
const modalPanelRef = ref<HTMLElement | null>(null);

function closeDetail() {
  emit("close-detail");
}

watch(
  () => props.selectedPathKey,
  async (key) => {
    if (!key) return;
    await nextTick();
    modalPanelRef.value?.focus({ preventScroll: true });
  },
);

const CHILD_KEYS = [
  "itens",
  "atividades",
  "items",
  "tasks",
  "historias",
  "children",
  "subitens",
  "filhos",
] as const;

function objRecord(v: unknown): Record<string, unknown> | null {
  if (v === null || typeof v !== "object" || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

function readTitle(o: Record<string, unknown>): string {
  const t = o.titulo ?? o.nome ?? o.title ?? o.epico ?? o.fase ?? o.label;
  if (typeof t === "string" && t.trim()) return t.trim();
  return "Sem título";
}

function readProgress(o: Record<string, unknown>): number {
  const keys = [
    "percentual_concluido",
    "percentual",
    "progresso",
    "pct",
    "percent",
    "concluido_pct",
    "concluido",
  ] as const;
  for (const k of keys) {
    const n = o[k];
    if (typeof n === "number" && !Number.isNaN(n)) return Math.min(100, Math.max(0, n));
    if (typeof n === "string") {
      const m = parseFloat(String(n).replace(/%/g, "").replace(",", "."));
      if (!Number.isNaN(m)) return Math.min(100, Math.max(0, m));
    }
  }
  const ck = findChildArrayKey(o);
  if (ck) {
    const arr = o[ck];
    if (Array.isArray(arr) && arr.length) {
      let done = 0;
      for (const it of arr) {
        const io = objRecord(it);
        if (!io) continue;
        const st = String(io.status ?? io.situacao ?? "").toLowerCase();
        if (st.includes("conclu") || st.includes("done") || st.includes("complete") || io.concluido === true)
          done++;
      }
      return Math.round((done / arr.length) * 100);
    }
  }
  return 0;
}

function findChildArrayKey(o: Record<string, unknown>): string | null {
  for (const k of CHILD_KEYS) {
    const v = o[k];
    if (Array.isArray(v) && v.length > 0) return k;
  }
  for (const k of Object.keys(o).sort((a, b) => a.localeCompare(b, "pt"))) {
    const v = o[k];
    if (Array.isArray(v) && (v as unknown[]).some((x) => x !== null && typeof x === "object")) return k;
  }
  return null;
}

function itemFromUnknown(it: unknown, path: PlanejPath): PhaseItem {
  const io = objRecord(it);
  const pathKey = JSON.stringify(path);
  const titulo = typeof it === "string" ? it : io ? readTitle(io) : "—";
  let status = "—";
  if (io) {
    const s = io.status ?? io.situacao;
    status = typeof s === "string" ? s : "—";
  }
  return { pathKey, path, titulo, status };
}

function phaseFromUnknown(
  ph: unknown,
  path: PlanejPath,
  index: number,
  kind: "preparation" | "feature" = "feature",
): PhaseBlock {
  const po = objRecord(ph) ?? {};
  const titulo = typeof ph === "string" ? ph : readTitle(po);
  const pct = typeof ph === "string" ? 0 : readProgress(po);
  const pathKey = JSON.stringify(path);
  const childKey = typeof ph === "string" ? null : findChildArrayKey(po);
  const items: PhaseItem[] = [];
  if (childKey && Array.isArray(po[childKey])) {
    (po[childKey] as unknown[]).forEach((it, idx) => {
      items.push(itemFromUnknown(it, [...path, childKey, idx]));
    });
  }
  const dotClass =
    kind === "preparation"
      ? "bg-amber-600"
      : index % 2 === 0
        ? "bg-emerald-500"
        : "bg-blue-600";
  return { pathKey, path, titulo, pct, items, dotClass, kind };
}

/** Chaves na raiz do JSON para o bloco executado antes das `fases` (Cursor / ambiente / arquitetura). */
const PREPARATION_ROOT_KEYS = [
  "preparacao",
  "preparação",
  "setup_inicial",
  "fundacao",
  "fundacao_tecnica",
  "antes_fases",
  "ambiente_arquitetura",
  "pre_fases",
] as const;

const DEFAULT_PREPARATION_TITLE = "Preparação: ambiente, arquitetura e Cursor";

function extractPreparationPhase(parsed: unknown): PhaseBlock | null {
  const o = objRecord(parsed);
  if (!o) return null;
  for (const k of PREPARATION_ROOT_KEYS) {
    if (!(k in o)) continue;
    const raw = o[k];
    const block = phaseFromUnknown(raw, [k], 0, "preparation");
    if (block.titulo === "Sem título" && block.items.length === 0) continue;
    if (block.titulo === "Sem título") {
      return { ...block, titulo: DEFAULT_PREPARATION_TITLE };
    }
    return block;
  }
  return null;
}

function extractRoadmapPhases(parsed: unknown): PhaseBlock[] | null {
  if (parsed === null || parsed === undefined) return null;
  if (Array.isArray(parsed)) {
    if (!parsed.length) return null;
    const fo = objRecord(parsed[0]);
    const firstProbe = fo ?? {};
    if (readTitle(firstProbe) === "Sem título" && !findChildArrayKey(firstProbe)) return null;
    return parsed.map((ph, i) => phaseFromUnknown(ph, [i], i, "feature"));
  }
  const o = objRecord(parsed);
  if (!o) return null;
  for (const prop of ["fases", "phases", "etapas"] as const) {
    const arr = o[prop];
    if (Array.isArray(arr) && arr.length > 0) {
      return arr.map((ph, i) => phaseFromUnknown(ph, [prop, i], i, "feature"));
    }
  }
  return null;
}

const roadmapPhases = computed((): PhaseBlock[] | null => extractRoadmapPhases(props.parsed));
const preparationPhase = computed(() => extractPreparationPhase(props.parsed));
const useRoadmapLayout = computed(
  () => !!preparationPhase.value || ((roadmapPhases.value?.length ?? 0) > 0),
);

type RoadmapLabeledRow = { labelBefore: string | null; phase: PhaseBlock };

const orderedRoadmapSections = computed((): RoadmapLabeledRow[] => {
  const out: RoadmapLabeledRow[] = [];
  const prep = preparationPhase.value;
  const phases = roadmapPhases.value ?? [];
  if (prep) {
    out.push({
      labelBefore: "Antes das fases de funcionalidades · ambiente, arquitetura e Cursor",
      phase: prep,
    });
  }
  phases.forEach((ph, i) => {
    out.push({
      labelBefore: prep && i === 0 ? "Fases de desenvolvimento (PRD e protótipo)" : null,
      phase: ph,
    });
  });
  return out;
});

function statusPillClass(status: string): string {
  const s = status.toLowerCase();
  if (s.includes("conclu") || s.includes("done") || s.includes("complete") || s.includes("feito"))
    return "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/35 dark:text-emerald-100";
  if (s.includes("andamento") || s.includes("progress") || s.includes("doing") || s.includes("em curso"))
    return "bg-sky-100 text-sky-900 dark:bg-sky-900/35 dark:text-sky-100";
  if (s.includes("pend") || s.includes("bloq") || s.includes("risk"))
    return "bg-amber-100 text-amber-900 dark:bg-amber-900/35 dark:text-amber-100";
  return "bg-surface-container-high text-on-surface-variant";
}

function getAtPath(root: unknown, path: PlanejPath): unknown {
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

function rowStatus(row: PlanejTreeRow): string {
  try {
    const path = JSON.parse(row.pathKey) as PlanejPath;
    const v = getAtPath(props.parsed, path);
    const o = objRecord(v);
    if (o) {
      const s = o.status ?? o.situacao;
      if (typeof s === "string" && s.trim()) return s.trim();
    }
  } catch {
    /* ignore */
  }
  return "—";
}

function isItemCompleted(status: string): boolean {
  const s = status.toLowerCase();
  return s.includes("conclu") || s.includes("done") || s.includes("complete");
}

const detailRecord = computed(() => {
  if (!props.detailJson?.trim()) return null;
  try {
    const d = JSON.parse(props.detailJson);
    if (d === null || typeof d !== "object" || Array.isArray(d)) return null;
    return d as Record<string, unknown>;
  } catch {
    return null;
  }
});

const detailTitle = computed(() => {
  const o = detailRecord.value;
  if (!o) return "";
  const t = o.titulo ?? o.nome ?? o.title ?? o.epico ?? o.label;
  if (typeof t === "string" && t.trim()) return t.trim();
  return "";
});

const detailDescription = computed(() => {
  const o = detailRecord.value;
  if (!o) return "";
  for (const k of ["descricao", "descricao_detalhada", "sumario", "texto", "description", "detalhe"]) {
    const v = o[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "";
});

const RESERVED_DETAIL_KEYS = new Set([
  "titulo",
  "nome",
  "title",
  "epico",
  "label",
  "descricao",
  "descricao_detalhada",
  "sumario",
  "texto",
  "description",
  "detalhe",
]);

/** Caminhos / layout longos — bloco dedicado no cartão (como na referência). */
const LAYOUT_BLOCK_KEYS = new Set([
  "layout",
  "layouts",
  "caminhos_layout",
  "ficheiros_layout",
  "prototipo_paths",
  "html_paths",
  "paths",
]);

/** Relatório do agente / «o que foi entregue» — alinhado a `ENTREGA_BLOCK_KEYS` no backend. */
const ENTREGA_BLOCK_KEYS = new Set([
  "o_que_foi_entregue",
  "oque_foi_entregue",
  "entrega_resumo",
  "entrega",
  "entregue",
  "entregaveis",
  "entregáveis",
  "what_was_delivered",
  "deliverables",
  "resumo_entrega",
  "agent_delivery",
  "relatorio_entrega",
  "relatório_entrega",
]);

const detailLayoutText = computed(() => {
  const o = detailRecord.value;
  if (!o) return "";
  for (const k of LAYOUT_BLOCK_KEYS) {
    if (!(k in o)) continue;
    const v = o[k];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (Array.isArray(v) && v.length) {
      const parts = v.filter((x): x is string => typeof x === "string" && x.trim().length > 0);
      if (parts.length) return parts.join(" e ");
    }
  }
  return "";
});

const detailEntregaText = computed(() => {
  const o = detailRecord.value;
  if (!o) return "";
  for (const k of ENTREGA_BLOCK_KEYS) {
    if (!(k in o)) continue;
    const v = o[k as keyof typeof o];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (Array.isArray(v) && v.length) {
      const lines = v
        .map((x) => {
          if (typeof x === "string" && x.trim()) return x.trim();
          if (x && typeof x === "object" && !Array.isArray(x)) {
            const rec = x as Record<string, unknown>;
            const t = rec.titulo ?? rec.nome ?? rec.title ?? rec.label;
            if (typeof t === "string" && t.trim()) return t.trim();
          }
          return "";
        })
        .filter((s) => s.length > 0);
      if (lines.length) return lines.join("\n");
    }
  }
  return "";
});

function chipSortPriority(k: string): number {
  if (k === "batch") return 0;
  if (k === "id") return 1;
  return 10;
}

const detailChips = computed(() => {
  const o = detailRecord.value;
  if (!o) return [];
  const chips: { label: string; value: string }[] = [];
  const keys = Object.keys(o)
    .filter(
      (k) => !RESERVED_DETAIL_KEYS.has(k) && !LAYOUT_BLOCK_KEYS.has(k) && !ENTREGA_BLOCK_KEYS.has(k),
    )
    .sort((a, b) => {
      const pa = chipSortPriority(a) - chipSortPriority(b);
      if (pa !== 0) return pa;
      return a.localeCompare(b, "pt");
    });
  for (const k of keys) {
    const v = o[k];
    if (v === null || v === undefined) continue;
    if (typeof v === "object") continue;
    const value =
      typeof v === "string" || typeof v === "number" || typeof v === "boolean" ? String(v) : "";
    if (!value) continue;
    const clipped = value.length > 200 ? `${value.slice(0, 200)}…` : value;
    chips.push({ label: formatChipLabel(k), value: clipped });
  }
  return chips;
});

function formatChipLabel(k: string): string {
  const map: Record<string, string> = {
    area_path: "Área no Azure",
    area: "Área",
    inicio_previsto: "Início previsto",
    fim_previsto: "Fim previsto",
    inicio_realizado: "Início realizado",
    fim_realizado: "Fim realizado",
    data_inicio: "Data início",
    data_fim: "Data fim",
    previsto_inicio: "Previsto (início)",
    previsto_fim: "Previsto (fim)",
    status: "Estado",
    situacao: "Situação",
    equipe: "Equipa",
    time: "Equipa",
    devs: "Devs",
  };
  return map[k] || k.replace(/_/g, " ");
}

function iconForDepth(depth: number): { name: string; color: string } {
  const m = depth % 3;
  if (m === 0) return { name: "workspace_premium", color: "text-amber-600 dark:text-amber-400" };
  if (m === 1) return { name: "emoji_events", color: "text-purple-600 dark:text-purple-400" };
  return { name: "menu_book", color: "text-blue-600 dark:text-blue-400" };
}

function onToggleExpand(pathKey: string, ev: MouseEvent) {
  emit("toggle-expand", pathKey, ev);
}
</script>

<template>
  <div class="min-h-[16rem]">
    <!-- Lista: roadmap por fases ou árvore estilizada (largura total) -->
    <div class="space-y-6 max-h-[32rem] lg:max-h-[40rem] overflow-y-auto pr-1">
      <template v-if="useRoadmapLayout && orderedRoadmapSections.length">
        <template v-for="(row, rowIdx) in orderedRoadmapSections" :key="row.phase.pathKey">
          <p
            v-if="row.labelBefore"
            class="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant font-label mb-2"
            :class="rowIdx > 0 ? 'mt-8' : ''"
          >
            {{ row.labelBefore }}
          </p>
          <section
            class="rounded-xl border bg-surface-container-lowest/80 shadow-sm overflow-hidden"
            :class="
              row.phase.kind === 'preparation'
                ? 'border-amber-600/35 ring-1 ring-amber-600/15'
                : 'border-outline-variant/20'
            "
          >
            <button
              type="button"
              class="w-full text-left px-4 pt-4 pb-3 border-b border-outline-variant/10 hover:bg-surface-container-high/40 transition-colors"
              :class="selectedPathKey === row.phase.pathKey ? 'bg-primary-container/25' : ''"
              @click="emit('select', row.phase.pathKey)"
            >
              <div class="flex items-start gap-3">
                <span
                  class="mt-1.5 inline-flex h-3 w-3 shrink-0 items-center justify-center rounded-full ring-2 ring-surface-container-lowest"
                  :class="row.phase.dotClass"
                  aria-hidden="true"
                >
                  <span class="h-1 w-1 rounded-full bg-white/90" />
                </span>
                <div class="min-w-0 flex-1">
                  <h5 class="text-sm font-bold text-on-surface font-headline leading-snug">{{ row.phase.titulo }}</h5>
                  <div class="mt-2 flex items-center gap-3">
                    <div
                      class="h-1.5 flex-1 max-w-[14rem] rounded-full bg-outline-variant/25 overflow-hidden"
                      role="progressbar"
                      :aria-valuenow="row.phase.pct"
                      aria-valuemin="0"
                      aria-valuemax="100"
                    >
                      <div
                        class="h-full rounded-full bg-primary transition-[width] duration-300"
                        :style="{ width: `${Math.min(100, Math.max(0, row.phase.pct))}%` }"
                      />
                    </div>
                    <span class="text-xs text-on-surface-variant font-body shrink-0 tabular-nums">
                      {{ Math.round(row.phase.pct) }}% Concluído
                    </span>
                  </div>
                </div>
              </div>
            </button>
            <div class="bg-surface-container-low/50 px-2 py-2">
              <div class="rounded-lg border border-outline-variant/15 bg-surface-container-lowest overflow-hidden">
                <button
                  v-for="(it, idx) in row.phase.items"
                  :key="it.pathKey"
                  type="button"
                  class="w-full flex items-center gap-3 px-3 py-3 text-left border-b border-outline-variant/10 last:border-b-0 transition-colors hover:bg-surface-container-high/30"
                  :class="[
                    selectedPathKey === it.pathKey ? 'bg-primary-container/20' : 'bg-surface-container-lowest',
                    idx === 0 ? '' : '',
                  ]"
                  @click="emit('select', it.pathKey)"
                >
                  <span
                    class="material-symbols-outlined text-xl shrink-0"
                    :class="isItemCompleted(it.status) ? 'text-emerald-600' : 'text-outline-variant'"
                    aria-hidden="true"
                  >
                    {{ isItemCompleted(it.status) ? "check_circle" : "radio_button_unchecked" }}
                  </span>
                  <span class="flex-1 min-w-0 text-sm text-on-surface font-body truncate">{{ it.titulo }}</span>
                  <span
                    class="shrink-0 text-[11px] font-semibold px-2.5 py-0.5 rounded-full font-body"
                    :class="statusPillClass(it.status)"
                  >
                    {{ it.status }}
                  </span>
                  <span class="shrink-0 flex items-center gap-0.5 text-on-surface-variant">
                    <span class="material-symbols-outlined text-lg opacity-50" aria-hidden="true">edit</span>
                    <span class="material-symbols-outlined text-lg text-error/70" aria-hidden="true">delete</span>
                  </span>
                </button>
                <div
                  class="m-2 rounded-lg border border-dashed border-outline-variant/35 bg-surface-container-low/40 px-3 py-4 flex items-center justify-center gap-2 text-primary text-sm font-medium font-body pointer-events-none select-none"
                  aria-hidden="true"
                >
                  <span class="material-symbols-outlined text-xl">add</span>
                  Adicionar atividade
                </div>
              </div>
            </div>
          </section>
        </template>
      </template>

      <template v-else>
        <div class="relative rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-2 pl-3">
          <div
            class="absolute left-[19px] top-10 bottom-10 w-px bg-outline-variant/25 pointer-events-none"
            aria-hidden="true"
          />
          <div
            v-for="row in treeRows"
            :key="row.pathKey"
            class="relative flex items-stretch gap-1 rounded-lg"
            :style="{ marginLeft: `${row.depth * 14}px` }"
          >
            <button
              v-if="row.hasChildren"
              type="button"
              class="shrink-0 z-[1] w-9 flex items-center justify-center rounded-md hover:bg-surface-container-high text-on-surface-variant"
              :aria-expanded="expanded[row.pathKey] ? 'true' : 'false'"
              aria-label="Expandir ou colapsar"
              @click="onToggleExpand(row.pathKey, $event)"
            >
              <span
                class="material-symbols-outlined text-xl transition-transform duration-150"
                :style="{ transform: expanded[row.pathKey] ? 'rotate(90deg)' : 'rotate(0deg)' }"
              >
                chevron_right
              </span>
            </button>
            <span v-else class="shrink-0 w-9 inline-flex items-center justify-center" aria-hidden="true" />
            <button
              type="button"
              class="min-w-0 flex-1 flex items-center gap-2 text-left rounded-lg border px-2 py-2.5 transition-colors"
              :class="
                selectedPathKey === row.pathKey
                  ? 'bg-surface-container-high border-primary/40 shadow-sm'
                  : 'border-transparent hover:bg-surface-container-high/60 hover:border-outline-variant/15'
              "
              @click="emit('select', row.pathKey)"
            >
              <span
                class="material-symbols-outlined text-[22px] shrink-0"
                :class="iconForDepth(row.depth).color"
                aria-hidden="true"
              >
                {{ iconForDepth(row.depth).name }}
              </span>
              <span class="min-w-0 flex-1">
                <span class="block font-semibold text-sm text-on-surface font-body truncate">{{ row.label }}</span>
                <span class="block text-xs text-on-surface-variant font-body truncate mt-0.5">{{ row.preview }}</span>
              </span>
              <span
                class="shrink-0 text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full max-w-[7rem] truncate font-body"
                :class="statusPillClass(rowStatus(row))"
              >
                {{ rowStatus(row) }}
              </span>
              <span
                v-if="row.hasChildren"
                class="shrink-0 material-symbols-outlined text-lg text-on-surface-variant/70"
                aria-hidden="true"
              >
                add_circle
              </span>
              <span class="shrink-0 material-symbols-outlined text-lg text-error/65" aria-hidden="true">delete</span>
            </button>
          </div>
        </div>
      </template>
    </div>

    <Teleport to="body">
      <div
        v-if="selectedPathKey"
        class="fixed inset-0 z-[110] flex items-center justify-center bg-black/45 p-3 backdrop-blur-sm sm:p-4"
        role="presentation"
        @click.self="closeDetail"
      >
        <div
          ref="modalPanelRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="detailTitleId"
          tabindex="-1"
          class="flex max-h-[min(92vh,calc(100dvh-1rem))] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-2xl outline-none"
          @keydown.escape.prevent="closeDetail"
          @click.stop
        >
          <div
            class="flex shrink-0 items-start justify-between gap-3 border-b border-outline-variant/15 px-5 py-4"
          >
            <h2
              :id="detailTitleId"
              class="min-w-0 flex-1 text-xl font-bold text-on-surface font-headline leading-snug pr-2"
            >
              {{ detailTitle || "Detalhe" }}
            </h2>
            <div class="flex shrink-0 items-center gap-1">
              <span
                class="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 px-2.5 py-1.5 text-xs font-semibold text-on-surface-variant font-body"
              >
                <span class="material-symbols-outlined text-base" aria-hidden="true">edit</span>
                Editar
              </span>
              <button
                type="button"
                class="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high"
                aria-label="Fechar"
                @click="closeDetail"
              >
                <span class="material-symbols-outlined text-[22px]">close</span>
              </button>
            </div>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto p-5">
            <template
              v-if="
                detailRecord &&
                (detailTitle ||
                  detailDescription ||
                  detailChips.length ||
                  detailLayoutText ||
                  detailEntregaText)
              "
            >
              <p
                v-if="detailDescription"
                class="mb-4 text-sm leading-relaxed text-on-surface-variant font-body"
              >
                {{ detailDescription }}
              </p>
              <div v-if="detailChips.length" class="mb-4 flex flex-wrap gap-2">
                <div
                  v-for="(c, i) in detailChips"
                  :key="i"
                  class="inline-flex max-w-full items-baseline gap-1 rounded-lg border border-outline-variant/25 bg-surface-container-low px-2.5 py-1 text-xs"
                >
                  <span class="shrink-0 font-bold text-on-surface font-body">{{ c.label }}:</span>
                  <span class="break-all font-body text-on-surface-variant">{{ c.value }}</span>
                </div>
              </div>
              <div
                v-if="detailLayoutText"
                class="rounded-lg border border-outline-variant/20 bg-surface-container-low p-3 text-sm leading-relaxed"
              >
                <span class="font-bold text-on-surface font-body">layout:</span>
                <span class="ml-1 break-all text-on-surface-variant font-body">{{ detailLayoutText }}</span>
              </div>
              <div
                v-if="detailEntregaText"
                class="mt-3 rounded-lg border border-emerald-700/15 bg-emerald-50/80 p-3 text-sm leading-relaxed dark:border-emerald-500/20 dark:bg-emerald-950/25"
              >
                <p class="mb-1 font-bold text-on-surface font-body">O que foi entregue</p>
                <p class="whitespace-pre-wrap break-words font-body text-on-surface-variant">{{ detailEntregaText }}</p>
              </div>
            </template>
            <template v-else-if="detailJson.trim()">
              <p class="mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-on-surface-variant font-label">
                JSON do nó
              </p>
              <pre
                class="max-h-[min(60vh,520px)] overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-on-surface"
              >{{ detailJson }}</pre>
            </template>
            <p v-else class="text-sm text-on-surface-variant font-body">Sem conteúdo para este nó.</p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
