<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api } from "@/api/client";
import { hasLinkedGithubRepo, parseGithubRepoDisplaySlug } from "@/utils/githubRepo";

type Project = {
  id: number;
  name: string;
  product_owner: string;
  directory_name: string | null;
  github_repo_url: string | null;
  github_tag: string | null;
};

type WikiBrief = {
  documents?: unknown[];
  status?: string | null;
  error_message?: string | null;
  wiki_created_at?: string | null;
};

const projects = ref<Project[]>([]);
const wikiByProject = ref<Record<number, WikiBrief | null>>({});
const err = ref("");
const q = ref("");

const withRepo = computed(() => projects.value.filter(hasLinkedGithubRepo));

const filtered = computed(() => {
  const s = q.value.trim().toLowerCase();
  let list = withRepo.value;
  if (s) {
    list = list.filter(
      (p) =>
        p.name.toLowerCase().includes(s) ||
        p.product_owner.toLowerCase().includes(s) ||
        (p.directory_name ?? "").toLowerCase().includes(s) ||
        parseGithubRepoDisplaySlug(p.github_repo_url).toLowerCase().includes(s),
    );
  }
  return list;
});

function wikiStatusLabel(id: number): { text: string; cls: string } {
  const w = wikiByProject.value[id];
  if (w == null) return { text: "—", cls: "bg-surface-container-highest text-on-surface-variant" };
  if (w.status === "ready") return { text: "Sincronizado", cls: "bg-tertiary-container/15 text-on-tertiary-container" };
  if (w.status === "pending") return { text: "A processar", cls: "bg-secondary-container text-on-secondary-container" };
  if (w.status === "error") return { text: "Erro", cls: "bg-error-container text-error" };
  return { text: "Sem wiki", cls: "bg-surface-container-highest text-on-surface-variant" };
}

function formatWikiUpdatedAt(projectId: number): string {
  const w = wikiByProject.value[projectId];
  const raw = w?.wiki_created_at;
  if (!raw) return "—";
  try {
    return new Date(raw).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

async function load() {
  err.value = "";
  try {
    const list = await api<Project[]>("/projects");
    projects.value = list;
    const repos = list.filter(hasLinkedGithubRepo);
    wikiByProject.value = {};
    await Promise.all(
      repos.map(async (p) => {
        try {
          wikiByProject.value[p.id] = await api<WikiBrief>(`/projects/${p.id}/wiki`);
        } catch {
          wikiByProject.value[p.id] = null;
        }
      }),
    );
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao carregar projetos.";
  }
}

onMounted(() => void load());
</script>

<template>
  <div class="space-y-6 -mx-2 md:-mx-4 flex flex-col flex-1 min-h-[calc(100vh-6rem)]">
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4 px-2 md:px-4">
      <div class="flex flex-wrap items-start gap-3">
        <div class="w-10 h-10 bg-primary rounded-lg flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-on-primary text-xl">menu_book</span>
        </div>
        <div>
          <span class="text-[10px] font-bold tracking-[0.2em] text-on-surface-variant uppercase block mb-1 font-label"
            >Documentação</span
          >
          <h1 class="text-3xl font-extrabold font-headline tracking-tight text-on-surface">Wiki Explorer</h1>
          <p class="text-sm text-on-surface-variant mt-2 font-body max-w-xl">
            Aqui reúne-se a documentação dos projetos para consulta rápida. Escolha um projeto na lista abaixo para ler
            textos, orientações e materiais de apoio — tudo num só lugar, sem precisar de ferramentas técnicas.
          </p>
        </div>
      </div>
    </div>

    <p v-if="err" class="text-error text-sm font-body px-2 md:px-4">{{ err }}</p>

    <div class="px-2 md:px-4">
      <div
        class="flex items-center gap-2 max-w-lg bg-surface-container-lowest px-3 py-2 rounded-lg border border-outline-variant/10"
      >
        <span class="material-symbols-outlined text-outline text-lg shrink-0">search</span>
        <input
          v-model="q"
          class="bg-transparent border-none text-sm font-body focus:ring-0 p-0 w-full outline-none placeholder:text-outline"
          placeholder="Buscar por projeto, PO ou diretoria…"
          type="search"
          autocomplete="off"
        />
      </div>
    </div>

    <div
      v-if="!err && !withRepo.length"
      class="mx-2 md:mx-4 px-6 py-14 text-center bg-surface-container-low rounded-xl border border-outline-variant/22"
    >
      <p class="text-on-surface-variant font-body max-w-md mx-auto">
        Nenhum projeto com <strong class="text-on-surface">repositório GitHub</strong> vinculado. Associe a URL do repo no detalhe do projeto.
      </p>
      <RouterLink to="/projetos" class="inline-block mt-4 text-primary font-semibold underline font-body">Ir à listagem de projetos</RouterLink>
    </div>

    <ul v-else class="space-y-3 px-2 md:px-4 pb-8">
      <li
        v-for="p in filtered"
        :key="p.id"
        class="bg-surface rounded-xl border border-outline-variant/22 p-4 md:p-5 flex flex-col md:flex-row md:items-center gap-4 shadow-sm hover:border-primary/35 transition-colors"
      >
        <div class="flex-1 min-w-0 space-y-1">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-lg font-bold font-headline text-on-surface truncate">{{ p.name }}</h2>
            <span
              class="px-2.5 py-0.5 rounded-full text-[10px] font-bold font-label shrink-0"
              :class="wikiStatusLabel(p.id).cls"
            >
              {{ wikiStatusLabel(p.id).text }}
            </span>
          </div>
          <dl class="mt-2 space-y-1.5 text-xs text-on-surface-variant font-body">
            <div class="flex flex-wrap gap-x-1">
              <dt class="font-semibold text-on-surface-variant shrink-0">PO responsável:</dt>
              <dd class="text-on-surface min-w-0">{{ p.product_owner || "—" }}</dd>
            </div>
            <div class="flex flex-wrap gap-x-1">
              <dt class="font-semibold text-on-surface-variant shrink-0">Diretoria:</dt>
              <dd class="text-on-surface min-w-0">{{ p.directory_name ?? "—" }}</dd>
            </div>
            <div class="flex flex-wrap gap-x-1">
              <dt class="font-semibold text-on-surface-variant shrink-0">Última atualização da wiki:</dt>
              <dd class="text-on-surface min-w-0">{{ formatWikiUpdatedAt(p.id) }}</dd>
            </div>
          </dl>
        </div>
        <div class="flex flex-wrap gap-2 shrink-0">
          <RouterLink
            :to="{ name: 'detalhes-wiki', params: { projectId: String(p.id) } }"
            class="inline-flex items-center justify-center gap-2 bg-primary text-on-primary px-4 py-2.5 rounded-md text-sm font-semibold font-body hover:opacity-90 transition-opacity"
          >
            <span class="material-symbols-outlined text-lg">menu_book</span>
            Ver documentação
          </RouterLink>
        </div>
      </li>
    </ul>

    <p v-if="withRepo.length && !filtered.length" class="text-sm text-on-surface-variant font-body px-2 md:px-4">
      Nenhum projeto corresponde à pesquisa.
    </p>
  </div>
</template>
