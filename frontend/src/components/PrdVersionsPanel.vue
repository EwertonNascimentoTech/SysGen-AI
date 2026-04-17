<script setup lang="ts">
import { MdEditor } from "md-editor-v3";
import "md-editor-v3/lib/style.css";
import { computed, onUnmounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { renderPrdAssistantMarkdown } from "@/utils/prdChatMarkdown";

/** Itens da barra menos úteis no modal PRD (guardamos com o botão da app). */
const mdToolbarExclude = ["github", "save", "catalog", "htmlPreview"] as const;

type PrdVersionRow = {
  version: number;
  created_at: string | null;
  created_by_email: string | null;
  is_latest: boolean;
};

const props = withDefaults(
  defineProps<{
    projectId: number;
    tabActive?: boolean;
  }>(),
  { tabActive: true },
);

const emit = defineEmits<{ "prd-saved": [] }>();
const auth = useAuthStore();
const canSavePrdToServer = computed(() => auth.hasRole("admin", "coordenador", "po"));

const prdEditorId = computed(() => `prd-md-editor-${props.projectId}`);

const detailModalOpen = ref(false);
const prdVersions = ref<PrdVersionRow[]>([]);
const selectedPrdVersion = ref<number | null>(null);
const panelMarkdown = ref("");
const panelLoading = ref(false);
const panelErr = ref("");
const versionsLoading = ref(false);
const savingPanel = ref(false);
const panelSaveMsg = ref("");

/** Edição só na ponta do histórico (maior número de versão), alinhado ao backend. */
const canEditPrdPanel = computed(() => {
  if (!canSavePrdToServer.value || selectedPrdVersion.value == null) return false;
  if (!prdVersions.value.length) return false;
  const maxV = Math.max(...prdVersions.value.map((r) => r.version));
  return selectedPrdVersion.value === maxV;
});

/** Realce na lista: versão aberta na modal, ou a última se a modal estiver fechada. */
const highlightedVersion = computed(() => {
  if (detailModalOpen.value && selectedPrdVersion.value != null) return selectedPrdVersion.value;
  return prdVersions.value.find((r) => r.is_latest)?.version ?? prdVersions.value[0]?.version ?? null;
});

function formatPrdVersionDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function closeDetailModal() {
  detailModalOpen.value = false;
}

function onEscapeKey(e: KeyboardEvent) {
  if (e.key === "Escape" && detailModalOpen.value) {
    e.preventDefault();
    closeDetailModal();
  }
}

async function loadPanelDetail(version: number) {
  panelLoading.value = true;
  panelErr.value = "";
  try {
    const d = await api<{
      version: number;
      markdown: string;
      created_at: string | null;
      created_by_email: string | null;
      is_latest: boolean;
    }>(`/projects/${props.projectId}/prd/versions/${version}`);
    panelMarkdown.value = d.markdown;
    const i = prdVersions.value.findIndex((r) => r.version === version);
    if (i >= 0) {
      prdVersions.value[i] = {
        ...prdVersions.value[i]!,
        is_latest: d.is_latest,
        created_at: d.created_at ?? prdVersions.value[i]!.created_at,
        created_by_email: d.created_by_email ?? prdVersions.value[i]!.created_by_email,
      };
    }
  } catch (e) {
    panelErr.value = e instanceof Error ? e.message : "Não foi possível carregar a versão.";
    panelMarkdown.value = "";
  } finally {
    panelLoading.value = false;
  }
}

async function openVersionModal(v: number) {
  selectedPrdVersion.value = v;
  detailModalOpen.value = true;
  await loadPanelDetail(v);
}

async function loadPrdVersions() {
  versionsLoading.value = true;
  panelErr.value = "";
  try {
    const rows = await api<PrdVersionRow[]>(`/projects/${props.projectId}/prd/versions`);
    prdVersions.value = rows;
    if (detailModalOpen.value && selectedPrdVersion.value != null) {
      const exists = rows.some((r) => r.version === selectedPrdVersion.value);
      if (exists) await loadPanelDetail(selectedPrdVersion.value);
      else closeDetailModal();
    }
  } catch {
    prdVersions.value = [];
    closeDetailModal();
  } finally {
    versionsLoading.value = false;
  }
}

type PrdVersionDetail = {
  version: number;
  markdown: string;
  created_at: string | null;
  created_by_email: string | null;
  is_latest: boolean;
};

function mergeNewVersionIntoList(detail: PrdVersionDetail) {
  const others = prdVersions.value.map((r) => ({ ...r, is_latest: false }));
  prdVersions.value = [
    {
      version: detail.version,
      created_at: detail.created_at,
      created_by_email: detail.created_by_email,
      is_latest: true,
    },
    ...others.filter((r) => r.version !== detail.version),
  ].sort((a, b) => b.version - a.version);
}

async function savePrdPanelEdit() {
  if (selectedPrdVersion.value == null || !canEditPrdPanel.value) return;
  savingPanel.value = true;
  panelErr.value = "";
  panelSaveMsg.value = "";
  try {
    const v = selectedPrdVersion.value;
    const out = await api<PrdVersionDetail>(`/projects/${props.projectId}/prd/versions/${v}`, {
      method: "PATCH",
      body: JSON.stringify({ markdown: panelMarkdown.value }),
    });
    mergeNewVersionIntoList(out);
    selectedPrdVersion.value = out.version;
    panelMarkdown.value = out.markdown;
    panelSaveMsg.value = `As alterações foram guardadas na versão ${out.version}.`;
    emit("prd-saved");
    await loadPrdVersions();
    window.setTimeout(() => {
      if (panelSaveMsg.value.startsWith("As alterações foram guardadas")) {
        panelSaveMsg.value = "";
      }
    }, 6000);
  } catch (e) {
    panelErr.value = e instanceof Error ? e.message : "Não foi possível guardar.";
  } finally {
    savingPanel.value = false;
  }
}

watch(
  () => [props.projectId, props.tabActive] as const,
  ([, active]) => {
    if (active === false) return;
    void loadPrdVersions();
  },
  { immediate: true },
);

watch(detailModalOpen, (open) => {
  if (open) window.addEventListener("keydown", onEscapeKey);
  else window.removeEventListener("keydown", onEscapeKey);
});

watch(
  () => props.tabActive,
  (active) => {
    if (active === false) closeDetailModal();
  },
);

onUnmounted(() => {
  window.removeEventListener("keydown", onEscapeKey);
});

defineExpose({
  reload: loadPrdVersions,
});
</script>

<template>
  <div class="flex w-full flex-col gap-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h3 class="font-headline text-xl font-bold tracking-tight text-on-surface">Versões PRD</h3>
        <p class="mt-0.5 font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
          Clique numa versão para ver o Markdown
        </p>
      </div>
      <button
        type="button"
        class="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low disabled:opacity-40"
        title="Actualizar lista"
        :disabled="versionsLoading"
        @click="loadPrdVersions"
      >
        <span class="material-symbols-outlined text-[22px]" :class="{ 'animate-spin': versionsLoading }">refresh</span>
      </button>
    </div>

    <div class="flex max-h-[min(42vh,280px)] flex-col gap-3 overflow-y-auto prd-v-scroll">
      <p
        v-if="!versionsLoading && !prdVersions.length"
        class="rounded-lg bg-surface-container-low px-4 py-6 text-center font-body text-xs leading-relaxed text-on-surface-variant"
      >
        Ainda não há versões guardadas. Usa «Guardar PRD (MD)» numa resposta da IA.
      </p>
      <button
        v-for="row in prdVersions"
        :key="row.version"
        type="button"
        class="group w-full rounded-r-lg p-4 text-left transition-all"
        :class="
          highlightedVersion === row.version
            ? 'border-l-4 border-primary bg-surface-container-lowest shadow-sm'
            : 'border border-transparent bg-surface-container-low hover:border-outline-variant/25'
        "
        @click="openVersionModal(row.version)"
      >
        <div class="mb-2 flex items-start justify-between gap-2">
          <span
            class="font-headline text-xs font-bold"
            :class="highlightedVersion === row.version ? 'text-on-surface' : 'text-on-surface-variant group-hover:text-on-surface'"
            >Versão {{ row.version }}</span
          >
          <span
            v-if="row.is_latest"
            class="shrink-0 rounded-full bg-tertiary-container px-2 py-0.5 font-label text-[9px] font-bold uppercase tracking-tighter text-on-tertiary-container"
            >v{{ row.version }} · actual</span
          >
          <span v-else class="shrink-0 font-mono text-[10px] italic text-on-surface-variant/50">arquivo</span>
        </div>
        <p class="font-body text-[11px] font-medium text-on-surface-variant/80">
          Atualizado: {{ formatPrdVersionDate(row.created_at) || "—" }}
        </p>
      </button>
    </div>

    <!-- Modal: Teleport para document.body para ficar acima do layout (aside z-50, header z-40) -->
    <Teleport to="body">
      <div
        v-if="detailModalOpen"
        class="fixed inset-0 z-[110] flex items-center justify-center bg-primary-container/55 p-2 sm:p-3 backdrop-blur-sm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prd-detail-modal-title"
        @click.self="closeDetailModal"
      >
        <div
          class="flex h-[min(92vh,calc(100dvh-1rem))] w-full max-w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-xl border border-outline-variant/15 bg-surface-container-lowest shadow-2xl sm:max-w-[calc(100vw-1.5rem)]"
          @click.stop
        >
        <div class="flex shrink-0 items-start justify-between gap-3 border-b border-outline-variant/15 px-5 py-4 sm:px-6">
          <div class="min-w-0">
            <h2 id="prd-detail-modal-title" class="font-headline text-lg font-extrabold tracking-tight text-on-surface sm:text-xl">
              PRD · Versão {{ selectedPrdVersion }}
            </h2>
            <p class="mt-1 font-body text-xs text-on-surface-variant">
              <template v-if="canEditPrdPanel">Última versão — pode editar o Markdown.</template>
              <template v-else>Versão em arquivo — só leitura.</template>
            </p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low"
            aria-label="Fechar"
            @click="closeDetailModal"
          >
            <span class="material-symbols-outlined text-[22px]">close</span>
          </button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          <div
            v-if="panelSaveMsg"
            role="status"
            aria-live="polite"
            class="mb-4 flex items-start gap-3 rounded-xl border border-primary/30 bg-primary-container/20 px-4 py-3"
          >
            <span class="material-symbols-outlined shrink-0 text-[22px] text-primary" aria-hidden="true">check_circle</span>
            <p class="font-body text-sm font-semibold leading-snug text-on-surface">{{ panelSaveMsg }}</p>
          </div>
          <p v-if="panelErr" class="mb-3 font-body text-xs text-error">{{ panelErr }}</p>

          <div
            v-if="panelLoading"
            class="flex items-center justify-center py-16 font-body text-sm text-on-surface-variant"
          >
            <span class="material-symbols-outlined mr-2 animate-spin">progress_activity</span>
            A carregar…
          </div>

          <template v-else-if="selectedPrdVersion != null">
            <div
              v-if="!canEditPrdPanel && prdVersions.length"
              class="mb-4 flex items-start gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-low p-3"
            >
              <span class="material-symbols-outlined shrink-0 text-lg text-on-surface-variant">info</span>
              <p class="font-body text-xs leading-relaxed text-on-surface-variant">
                Esta versão está arquivada. Apenas a versão marcada como <span class="font-semibold text-on-surface">actual</span> pode ser editada.
              </p>
            </div>

            <div
              v-if="canEditPrdPanel || savingPanel"
              class="prd-md-editor-wrap overflow-hidden rounded-xl border border-outline-variant/10 bg-white shadow-inner"
            >
              <MdEditor
                :id="prdEditorId"
                :key="`${prdEditorId}-v-${selectedPrdVersion}`"
                v-model="panelMarkdown"
                theme="light"
                preview-theme="github"
                :preview="true"
                language="en-US"
                placeholder="Edite o Markdown do PRD…"
                :no-upload-img="true"
                :toolbars-exclude="[...mdToolbarExclude]"
                :disabled="savingPanel"
                class="prd-md-editor"
              />
            </div>
            <div
              v-else
              class="max-h-[min(60vh,520px)] overflow-y-auto rounded-xl border border-outline-variant/10 bg-white p-4 prd-v-scroll sm:p-5"
            >
              <div
                class="prd-chat-markdown font-body text-sm leading-relaxed text-on-surface"
                v-html="renderPrdAssistantMarkdown(panelMarkdown)"
              />
            </div>
          </template>
        </div>

        <div
          v-if="(canEditPrdPanel || savingPanel) && selectedPrdVersion != null && !panelLoading"
          class="shrink-0 border-t border-outline-variant/15 bg-surface-container-low px-4 py-4 sm:px-6"
        >
          <button
            type="button"
            class="w-full rounded-md bg-primary py-2.5 font-label text-xs font-bold uppercase tracking-widest text-on-primary shadow-lg shadow-primary/10 transition-all hover:opacity-95 disabled:opacity-40 sm:w-auto sm:px-8"
            :disabled="savingPanel"
            @click="savePrdPanelEdit"
          >
            {{ savingPanel ? "A guardar…" : "Guardar alterações" }}
          </button>
        </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.prd-v-scroll::-webkit-scrollbar {
  width: 4px;
}
.prd-v-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.prd-v-scroll::-webkit-scrollbar-thumb {
  background: rgb(198 198 205 / 0.8);
  border-radius: 10px;
}

/* Editor Markdown: aproveita melhor a modal em ecrã largo */
.prd-md-editor-wrap :deep(.md-editor) {
  min-height: min(55vh, 480px);
}
@media (min-width: 1024px) {
  .prd-md-editor-wrap :deep(.md-editor) {
    min-height: min(60vh, 560px);
  }
}
</style>
