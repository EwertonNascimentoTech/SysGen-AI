<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { api } from "@/api/client";

const router = useRouter();

type Project = {
  id: number;
  name: string;
  product_owner: string;
  methodology: string;
  current_column_title: string | null;
  directory_name: string | null;
  planned_end: string;
  ended_at: string | null;
  github_repo_url: string | null;
};

type Summary = {
  total_projects: number;
  active_projects: number;
  github_linked: number;
  wikis_ready: number;
  cursor_artifact_links: number;
};

const projects = ref<Project[]>([]);
const summary = ref<Summary | null>(null);
const err = ref("");

const barPalette = [
  "bg-primary-container",
  "bg-primary",
  "bg-secondary-fixed-dim",
  "bg-outline",
  "bg-surface-variant",
] as const;

onMounted(async () => {
  try {
    projects.value = await api<Project[]>("/projects");
    try {
      summary.value = await api<Summary>("/dashboard/summary");
    } catch {
      summary.value = null;
    }
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
});

function methodologyLabel(m: string) {
  if (m === "base44") return "Base 44";
  if (m === "prd") return "PRD";
  return m;
}

function formatDate(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

const today = new Date();
today.setHours(0, 0, 0, 0);

function isOverdue(p: Project) {
  if (p.ended_at) return false;
  const end = new Date(p.planned_end + "T12:00:00");
  return end < today;
}

function rowAccentClass(i: number) {
  const r = i % 3;
  if (r === 0) return "border-l-2 border-primary";
  if (r === 1) return "border-l-2 border-secondary";
  return "border-l-2 border-outline-variant";
}

function statusDotClass(p: Project) {
  const col = (p.current_column_title ?? "").toLowerCase();
  if (p.ended_at || col.includes("conclu")) return "bg-tertiary-fixed";
  if (isOverdue(p)) return "bg-error";
  if (col.includes("revis") || col.includes("homolog")) return "bg-amber-400";
  return "bg-tertiary-fixed";
}

const byDirectory = computed(() => {
  const m = new Map<string, number>();
  for (const p of projects.value) {
    const d = p.directory_name ?? "Sem diretoria";
    m.set(d, (m.get(d) ?? 0) + 1);
  }
  return [...m.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
});

const maxDirCount = computed(() => Math.max(1, ...byDirectory.value.map(([, n]) => n)));

const methodologySplit = computed(() => {
  const n = projects.value.length;
  if (!n) return { base44: 0, prd: 0 };
  const b44 = projects.value.filter((p) => p.methodology === "base44").length;
  const prd = projects.value.filter((p) => p.methodology === "prd").length;
  return {
    base44: Math.round((b44 / n) * 100),
    prd: Math.round((prd / n) * 100),
  };
});

const displaySummary = computed((): Summary => {
  const list = projects.value;
  if (summary.value) return summary.value;
  const active = list.filter((p) => !p.ended_at).length;
  const gh = list.filter((p) => p.github_repo_url).length;
  return {
    total_projects: list.length,
    active_projects: active,
    github_linked: gh,
    wikis_ready: 0,
    cursor_artifact_links: 0,
  };
});

const executiveSubtitle = computed(() => {
  const t = displaySummary.value.total_projects;
  if (!t) {
    return "Nenhuma iniciativa cadastrada ainda. Crie o primeiro projeto para iniciar a governança.";
  }
  return `Portfólio com ${t} iniciativa${t === 1 ? "" : "s"}. Acompanhe metodologia, Kanban e vínculos com GitHub em tempo real.`;
});
</script>

<template>
  <div class="space-y-8 relative pb-24">
    <!-- Cabeçalho (protótipo dashboard_executivo_pt_br) -->
    <section class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <h2 class="text-4xl font-extrabold font-headline tracking-tighter text-on-surface">Visão Geral Executiva</h2>
        <p class="text-on-surface-variant mt-2 max-w-xl font-body text-sm leading-relaxed">
          {{ executiveSubtitle }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          type="button"
          disabled
          class="px-4 py-2 bg-surface-container-high text-on-surface font-semibold rounded-md text-sm opacity-60 cursor-not-allowed flex items-center gap-2"
          title="Em breve"
        >
          <span class="material-symbols-outlined text-sm">filter_list</span>
          Filtrar vista
        </button>
        <RouterLink
          to="/projetos/novo"
          class="px-4 py-2 bg-primary text-on-primary font-semibold rounded-md text-sm hover:opacity-90 transition-opacity flex items-center gap-2"
        >
          <span class="material-symbols-outlined text-sm">add</span>
          Novo projeto
        </RouterLink>
      </div>
    </section>

    <p v-if="err" class="text-error text-sm font-body">{{ err }}</p>

    <!-- KPI bento -->
    <section class="grid grid-cols-1 md:grid-cols-5 gap-4">
      <div class="bg-surface-container-lowest p-6 rounded-xl editorial-shadow flex flex-col justify-between h-32">
        <div class="flex justify-between items-start">
          <span class="text-[10px] font-bold tracking-widest text-on-surface-variant uppercase font-label">Total de projetos</span>
          <span class="material-symbols-outlined text-primary-fixed-dim">account_tree</span>
        </div>
        <div class="text-4xl font-extrabold font-headline">{{ displaySummary.total_projects }}</div>
      </div>
      <div
        class="bg-surface-container-lowest p-6 rounded-xl editorial-shadow flex flex-col justify-between h-32 border-l-4 border-tertiary-fixed"
      >
        <div class="flex justify-between items-start">
          <span class="text-[10px] font-bold tracking-widest text-on-surface-variant uppercase font-label">Status ativo</span>
          <span class="material-symbols-outlined text-tertiary-fixed">rocket_launch</span>
        </div>
        <div class="text-4xl font-extrabold font-headline">{{ displaySummary.active_projects }}</div>
      </div>
      <div class="bg-surface-container-lowest p-6 rounded-xl editorial-shadow flex flex-col justify-between h-32">
        <div class="flex justify-between items-start">
          <span class="text-[10px] font-bold tracking-widest text-on-surface-variant uppercase font-label">GitHub</span>
          <span class="material-symbols-outlined text-on-surface-variant">code</span>
        </div>
        <div class="text-4xl font-extrabold font-headline">{{ displaySummary.github_linked }}</div>
      </div>
      <div class="bg-surface-container-lowest p-6 rounded-xl editorial-shadow flex flex-col justify-between h-32">
        <div class="flex justify-between items-start">
          <span class="text-[10px] font-bold tracking-widest text-on-surface-variant uppercase font-label">Wikis prontas</span>
          <span class="material-symbols-outlined text-on-surface-variant">menu_book</span>
        </div>
        <div class="text-4xl font-extrabold font-headline">{{ displaySummary.wikis_ready }}</div>
      </div>
      <div
        class="bg-surface-container-lowest p-6 rounded-xl editorial-shadow flex flex-col justify-between h-32 bg-gradient-to-br from-primary-container to-slate-900"
      >
        <div class="flex justify-between items-start">
          <span class="text-[10px] font-bold tracking-widest text-[#DAE2FD] uppercase font-label">Artefatos Cursor</span>
          <span class="material-symbols-outlined text-tertiary-fixed">auto_awesome</span>
        </div>
        <div class="text-4xl font-extrabold font-headline text-white">{{ displaySummary.cursor_artifact_links }}</div>
      </div>
    </section>

    <!-- Gráfico + insight + metodologia -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-2 bg-surface-container-low p-8 rounded-xl space-y-6">
        <div class="flex justify-between items-baseline">
          <h3 class="text-xl font-bold font-headline tracking-tight">Distribuição de projetos</h3>
          <span class="text-xs font-medium text-on-surface-variant uppercase tracking-tighter font-label">Por diretoria</span>
        </div>
        <div v-if="byDirectory.length === 0" class="h-64 flex items-center justify-center text-on-surface-variant text-sm font-body">
          Sem dados para exibir.
        </div>
        <div v-else class="h-64 flex items-end gap-4 px-4 pb-4">
          <div v-for="([name, count], idx) in byDirectory" :key="name" class="flex-1 flex flex-col items-center gap-3 min-w-0">
            <div
              class="w-full rounded-t-sm transition-all"
              :class="barPalette[idx % barPalette.length]"
              :style="{ height: `${Math.round((count / maxDirCount) * 100)}%`, minHeight: count ? '8px' : '0' }"
            />
            <span class="text-[10px] font-bold uppercase text-on-surface-variant font-label truncate max-w-full text-center">{{
              name
            }}</span>
          </div>
        </div>
      </div>

      <div class="space-y-6">
        <div class="bg-surface-container-lowest p-6 rounded-xl border border-tertiary-fixed/30 relative overflow-hidden">
          <div class="absolute top-0 right-0 p-2">
            <span class="material-symbols-outlined text-tertiary-fixed text-lg">temp_preferences_custom</span>
          </div>
          <h4 class="text-sm font-bold uppercase tracking-widest text-on-tertiary-fixed mb-4 font-label">Insight de governança</h4>
          <p class="text-sm text-on-surface italic leading-relaxed font-body">
            Acompanhe o desvio de metodologia e o estágio do Kanban por projeto. Use o detalhe do projeto para wiki, tags GitHub e
            artefatos do Cursor Hub.
          </p>
          <RouterLink
            to="/projetos"
            class="mt-4 inline-block text-[10px] font-bold text-on-tertiary-container underline underline-offset-4 font-label"
          >
            VER PORTFÓLIO
          </RouterLink>
        </div>

        <div class="bg-surface-container-lowest p-6 rounded-xl editorial-shadow">
          <h4 class="text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-4 font-label">Divisão de metodologia</h4>
          <div class="space-y-4">
            <div>
              <div class="flex justify-between text-xs mb-1 font-body">
                <span class="font-semibold">Padrão Base 44</span>
                <span class="font-bold">{{ methodologySplit.base44 }}%</span>
              </div>
              <div class="w-full bg-surface-container h-1.5 rounded-full overflow-hidden">
                <div class="bg-primary h-full transition-all" :style="{ width: `${methodologySplit.base44}%` }" />
              </div>
            </div>
            <div>
              <div class="flex justify-between text-xs mb-1 font-body">
                <span class="font-semibold">Framework PRD</span>
                <span class="font-bold">{{ methodologySplit.prd }}%</span>
              </div>
              <div class="w-full bg-surface-container h-1.5 rounded-full overflow-hidden">
                <div class="bg-primary-fixed-dim h-full transition-all" :style="{ width: `${methodologySplit.prd}%` }" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Tabela -->
    <section class="bg-surface-container-low rounded-xl p-8 overflow-hidden">
      <div class="flex justify-between items-center mb-8">
        <h3 class="text-xl font-bold font-headline tracking-tight">Governança recente de projetos</h3>
        <div class="flex gap-2">
          <RouterLink
            to="/projetos"
            class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-variant text-on-surface-variant"
            title="Ver todos"
          >
            <span class="material-symbols-outlined text-sm">open_in_new</span>
          </RouterLink>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-separate border-spacing-y-4">
          <thead>
            <tr class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant font-label">
              <th class="pb-2 px-4">Nome do projeto</th>
              <th class="pb-2 px-4">PO / líder</th>
              <th class="pb-2 px-4">Metodologia</th>
              <th class="pb-2 px-4">Status atual</th>
              <th class="pb-2 px-4 text-right">Prazo</th>
            </tr>
          </thead>
          <tbody class="text-sm font-body">
            <tr
              v-for="(p, idx) in projects"
              :key="p.id"
              class="bg-surface-container-lowest group hover:bg-white transition-colors cursor-pointer"
              :class="{ 'opacity-75': isOverdue(p) }"
              @click="router.push(`/projetos/${p.id}`)"
            >
              <td :class="['py-4 px-4 font-bold rounded-l-lg text-on-surface', rowAccentClass(idx)]">
                {{ p.name }}
              </td>
              <td class="py-4 px-4">{{ p.product_owner }}</td>
              <td class="py-4 px-4">
                <span class="bg-surface-container-high px-2 py-0.5 rounded text-[10px] font-bold uppercase font-label">{{
                  methodologyLabel(p.methodology)
                }}</span>
              </td>
              <td class="py-4 px-4">
                <div class="flex items-center gap-2">
                  <div class="w-2 h-2 rounded-full shrink-0" :class="statusDotClass(p)" />
                  <span>{{ p.current_column_title ?? "—" }}</span>
                </div>
              </td>
              <td
                class="py-4 px-4 text-right font-mono rounded-r-lg"
                :class="isOverdue(p) ? 'text-error font-bold' : ''"
              >
                {{ isOverdue(p) ? "ATRASADO" : formatDate(p.planned_end) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!err && projects.length === 0" class="text-on-surface-variant text-sm font-body py-6 text-center">
          Nenhum projeto listado.
        </p>
      </div>
    </section>

    <RouterLink
      to="/projetos/novo"
      class="fixed bottom-8 right-8 w-14 h-14 bg-primary text-on-primary rounded-full shadow-2xl flex items-center justify-center hover:scale-105 transition-transform z-40"
      title="Novo projeto"
    >
      <span class="material-symbols-outlined text-3xl">add</span>
    </RouterLink>
  </div>
</template>
