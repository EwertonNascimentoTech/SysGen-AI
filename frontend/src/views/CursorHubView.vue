<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type Art = {
  id: number;
  kind: string;
  name: string;
  description: string | null;
  status: string;
  linked_projects_count?: number;
};

const auth = useAuthStore();
const items = ref<Art[]>([]);
const err = ref("");
const msg = ref("");
const searchQ = ref("");
const activeTab = ref<"rule" | "skill" | "mcp">("rule");
const showCreatePanel = ref(false);

const form = ref({ kind: "rule" as "rule" | "skill" | "mcp", name: "", description: "" });
const linkProjectId = ref<number | null>(null);
const linkArtifactId = ref<number | null>(null);

const tabs = [
  { id: "rule" as const, label: "Regras" },
  { id: "skill" as const, label: "Habilidades" },
  { id: "mcp" as const, label: "Biblioteca MCP" },
];

const filtered = computed(() => {
  const t = activeTab.value;
  let list = items.value.filter((a) => a.kind === t);
  const s = searchQ.value.trim().toLowerCase();
  if (s) {
    list = list.filter(
      (a) =>
        a.name.toLowerCase().includes(s) ||
        (a.description ?? "").toLowerCase().includes(s),
    );
  }
  return list;
});

const publishedCount = computed(() => items.value.filter((a) => a.status === "publicado").length);

onMounted(async () => {
  await auth.fetchMe();
  await reload();
});

async function reload() {
  err.value = "";
  try {
    items.value = await api<Art[]>("/cursor-artifacts");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

async function createArt() {
  msg.value = "";
  await api("/cursor-artifacts", {
    method: "POST",
    body: JSON.stringify({ ...form.value, content: "# rascunho" }),
  });
  form.value = { kind: form.value.kind, name: "", description: "" };
  await reload();
  msg.value = "Artefato criado como rascunho.";
  showCreatePanel.value = false;
}

async function publish(id: number) {
  await api(`/cursor-artifacts/${id}/publish`, { method: "POST" });
  await reload();
  msg.value = "Artefato publicado.";
}

async function link() {
  if (!linkProjectId.value || !linkArtifactId.value) return;
  await api(`/cursor-artifacts/projects/${linkProjectId.value}/link`, {
    method: "POST",
    body: JSON.stringify({ artifact_id: linkArtifactId.value }),
  });
  msg.value = "Vínculo registrado.";
  await reload();
}

function kindBadge(kind: string) {
  if (kind === "rule") return { label: "REGRA_PROMPT", class: "bg-primary-container text-primary-fixed" };
  if (kind === "skill") return { label: "HABILIDADE_IA", class: "bg-secondary-container text-on-secondary-container" };
  return { label: "BIBLIOTECA_MCP", class: "bg-tertiary-container text-tertiary-fixed" };
}

function authorInitials(name: string) {
  const p = name.trim().split(/\s+/).filter(Boolean);
  if (p.length >= 2) return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase() || "IA";
}

function openCreateForTab(tab: typeof activeTab.value) {
  form.value.kind = tab;
  showCreatePanel.value = true;
}
</script>

<template>
  <div class="-mx-2 md:-mx-4 space-y-8 px-2 md:px-4 pb-12">
    <!-- Cabeçalho (protótipo cursor_hub_artefatos_pt_br) -->
    <div class="flex flex-col lg:flex-row lg:justify-between lg:items-end gap-6">
      <div>
        <h2 class="text-4xl font-extrabold font-headline tracking-tight text-on-surface mb-2">Cursor Hub</h2>
        <p class="text-on-surface-variant max-w-2xl text-sm leading-relaxed font-body">
          Gerencie artefatos de IA, regras de prompt e bibliotecas de Model Context Protocol em todo o ciclo de vida de desenvolvimento da
          sua organização.
        </p>
        <div class="mt-4 relative max-w-md">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-lg pointer-events-none"
            >search</span
          >
          <input
            v-model="searchQ"
            type="search"
            class="w-full bg-surface-container-low border-none rounded-md pl-10 pr-4 py-2 text-sm text-on-surface focus:ring-1 focus:ring-primary transition-all font-body outline-none"
            placeholder="Pesquisar artefatos…"
          />
        </div>
      </div>
      <button
        v-if="auth.hasRole('admin', 'coordenador', 'dev')"
        type="button"
        class="bg-primary text-on-primary px-6 py-2.5 rounded-md font-semibold flex items-center gap-2 hover:opacity-90 transition-opacity shrink-0 font-body"
        @click="openCreateForTab(activeTab)"
      >
        <span class="material-symbols-outlined text-sm">add</span>
        Criar artefato
      </button>
    </div>

    <!-- Abas -->
    <div class="flex flex-wrap gap-8 border-b border-outline-variant/20">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        class="pb-4 text-sm font-body transition-all"
        :class="
          activeTab === t.id
            ? 'text-black font-bold border-b-2 border-primary -mb-px'
            : 'text-on-surface-variant font-medium hover:text-primary'
        "
        @click="activeTab = t.id"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- Painel criar (colapsável) -->
    <div
      v-if="showCreatePanel && auth.hasRole('admin', 'coordenador', 'dev')"
      class="bg-surface-container-low rounded-xl p-6 border border-outline-variant/10 space-y-4 max-w-3xl"
    >
      <div class="flex justify-between items-center gap-4">
        <h3 class="font-headline font-bold text-lg">Novo artefato</h3>
        <button type="button" class="text-on-surface-variant hover:text-on-surface text-sm font-body" @click="showCreatePanel = false">
          Fechar
        </button>
      </div>
      <div class="grid sm:grid-cols-2 gap-4">
        <label class="space-y-1 block text-xs font-bold text-on-surface-variant uppercase tracking-wider font-label">
          Tipo
          <select v-model="form.kind" class="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm font-body border border-outline-variant/10">
            <option value="rule">Regra (prompt)</option>
            <option value="skill">Habilidade</option>
            <option value="mcp">MCP</option>
          </select>
        </label>
        <label class="space-y-1 block text-xs font-bold text-on-surface-variant uppercase tracking-wider font-label">
          Nome
          <input v-model="form.name" class="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm font-body border border-outline-variant/10 outline-none" />
        </label>
      </div>
      <label class="space-y-1 block text-xs font-bold text-on-surface-variant uppercase tracking-wider font-label">
        Descrição
        <input
          v-model="form.description"
          class="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-sm font-body border border-outline-variant/10 outline-none"
        />
      </label>
      <button type="button" class="px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold font-body" @click="createArt">
        Salvar rascunho
      </button>
    </div>

    <div
      v-if="auth.hasRole('admin', 'coordenador') && !showCreatePanel"
      class="bg-surface-container-low/80 rounded-xl p-4 flex flex-wrap gap-4 items-end max-w-3xl border border-outline-variant/10"
    >
      <h3 class="w-full font-headline font-semibold text-sm">Vincular artefato publicado a projeto</h3>
      <input
        v-model.number="linkProjectId"
        type="number"
        class="w-32 rounded-lg bg-surface-container-lowest px-3 py-2 text-sm font-body border border-outline-variant/10 outline-none"
        placeholder="ID projeto"
      />
      <input
        v-model.number="linkArtifactId"
        type="number"
        class="w-36 rounded-lg bg-surface-container-lowest px-3 py-2 text-sm font-body border border-outline-variant/10 outline-none"
        placeholder="ID artefato"
      />
      <button type="button" class="px-4 py-2 bg-surface-container-high rounded-md text-sm font-semibold font-body hover:bg-surface-variant" @click="link">
        Vincular
      </button>
    </div>

    <p v-if="msg" class="text-sm text-on-tertiary-container font-body">{{ msg }}</p>
    <p v-if="err" class="text-error text-sm font-body">{{ err }}</p>

    <!-- Grade bento -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="a in filtered"
        :key="a.id"
        class="bg-surface-container-lowest rounded-xl p-6 flex flex-col justify-between group transition-all hover:-translate-y-1 editorial-shadow border border-transparent hover:border-outline-variant/20"
      >
        <div class="mb-4">
          <div class="flex justify-between items-start mb-4 gap-2">
            <span class="px-2.5 py-1 text-[10px] font-bold tracking-widest uppercase rounded font-label" :class="kindBadge(a.kind).class">{{
              kindBadge(a.kind).label
            }}</span>
            <div
              v-if="a.status === 'publicado'"
              class="flex items-center gap-1.5 text-on-tertiary-container bg-tertiary-container px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 font-label"
            >
              <span class="material-symbols-outlined text-[10px]" style="font-variation-settings: 'FILL' 1">check_circle</span>
              PUBLICADO
            </div>
            <div
              v-else
              class="flex items-center gap-1.5 text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 font-label"
            >
              RASCUNHO
            </div>
          </div>
          <h3 class="text-xl font-bold font-headline mb-2 text-on-surface">{{ a.name }}</h3>
          <p class="text-sm text-on-surface-variant line-clamp-2 font-body">{{ a.description || "Sem descrição." }}</p>
        </div>
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4 pt-4 border-t border-outline-variant/10">
            <div>
              <span class="text-[10px] uppercase font-bold text-outline tracking-wider block mb-1 font-label">Autor</span>
              <div class="flex items-center gap-2">
                <div
                  class="w-5 h-5 rounded-full bg-primary-container flex items-center justify-center text-[8px] text-primary-fixed font-bold shrink-0"
                >
                  {{ authorInitials(a.name) }}
                </div>
                <span class="text-xs font-semibold font-body truncate">{{ auth.me?.full_name ?? "Equipa" }}</span>
              </div>
            </div>
            <div>
              <span class="text-[10px] uppercase font-bold text-outline tracking-wider block mb-1 font-label">Projetos vinculados</span>
              <span class="text-xs font-semibold font-body">{{ a.linked_projects_count ?? 0 }} projeto(s)</span>
            </div>
          </div>
          <div class="flex justify-between items-center bg-surface-container-low p-2 rounded gap-2">
            <span class="text-[11px] font-medium opacity-60 font-body">ID #{{ a.id }} · gerir no painel</span>
            <div class="flex items-center gap-2">
              <button
                v-if="auth.hasRole('admin') && a.status !== 'publicado'"
                type="button"
                class="text-[10px] font-bold uppercase text-primary hover:underline font-label"
                @click="publish(a.id)"
              >
                Publicar
              </button>
              <span class="material-symbols-outlined text-sm opacity-40 group-hover:opacity-100 transition-opacity">arrow_forward</span>
            </div>
          </div>
        </div>
      </div>

      <p v-if="!err && filtered.length === 0" class="col-span-full text-center text-on-surface-variant text-sm py-12 font-body italic">
        Nenhum artefato nesta categoria. Crie um novo ou troque de aba.
      </p>

      <!-- Insight governança -->
      <div
        class="lg:col-span-2 bg-gradient-to-br from-primary-container to-slate-900 rounded-xl p-8 text-white relative overflow-hidden group border border-white/5"
      >
        <div class="absolute -right-20 -top-20 w-64 h-64 bg-tertiary-fixed/10 blur-[100px] pointer-events-none" />
        <div class="relative z-10 flex flex-col md:flex-row gap-8 items-center">
          <div class="flex-1">
            <div class="flex items-center gap-2 mb-4">
              <span class="material-symbols-outlined text-tertiary-fixed">auto_awesome</span>
              <span class="text-xs font-bold tracking-widest uppercase text-tertiary-fixed font-label">Insight de governança IA</span>
            </div>
            <h3 class="text-2xl font-bold font-headline mb-4 tracking-tight leading-tight">
              Padronize regras antes de publicar para vários projetos.
            </h3>
            <p class="text-slate-300 mb-6 text-sm leading-relaxed font-body">
              Artefatos em rascunho não podem ser vinculados. Publique (perfil admin), depois associe no bloco “Vincular” ou no detalhe do
              projeto.
            </p>
            <div class="flex flex-wrap gap-4">
              <button
                type="button"
                class="bg-white text-slate-900 px-5 py-2 rounded font-bold text-xs hover:bg-slate-200 transition-colors font-label"
                @click="showCreatePanel = true"
              >
                Novo rascunho
              </button>
              <button
                type="button"
                class="text-white border border-white/20 px-5 py-2 rounded font-bold text-xs hover:bg-white/10 transition-colors font-label"
                @click="activeTab = 'rule'"
              >
                Ver regras
              </button>
            </div>
          </div>
          <div class="w-full md:w-1/3 aspect-video bg-white/5 rounded-lg border border-white/10 p-4 backdrop-blur-sm">
            <div class="h-full flex flex-col justify-between">
              <div class="flex justify-between items-start">
                <div class="space-y-1">
                  <div class="w-16 h-1 bg-tertiary-fixed rounded" />
                  <div class="w-12 h-1 bg-white/20 rounded" />
                </div>
                <span class="text-[10px] font-mono text-white/40">v1</span>
              </div>
              <div class="space-y-2">
                <div class="w-full h-8 bg-white/5 rounded" />
                <div class="w-2/3 h-8 bg-white/5 rounded" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sugerir nova regra -->
      <div
        class="bg-surface-container-low/50 border border-dashed border-outline-variant/30 rounded-xl p-6 flex flex-col items-center justify-center text-center"
      >
        <span class="material-symbols-outlined text-4xl text-outline-variant mb-3">auto_fix_high</span>
        <h4 class="text-sm font-bold text-on-surface-variant font-headline">Sugerir nova regra</h4>
        <p class="text-xs text-outline mt-1 px-4 font-body leading-relaxed">
          Defina regras e habilidades alinhadas ao PRD; use MCP para integrações externas no Cursor.
        </p>
        <button
          type="button"
          class="mt-4 text-xs font-bold text-primary hover:underline font-label"
          @click="openCreateForTab(activeTab)"
        >
          Criar nesta aba
        </button>
      </div>
    </div>

    <!-- Rodapé meta -->
    <div      class="mt-8 flex flex-col lg:flex-row lg:justify-between gap-4 text-[11px] text-on-surface-variant border-t border-outline-variant/20 pt-6 font-body"
    >
      <div class="flex flex-wrap gap-6 items-center">
        <div class="flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-tertiary-fixed shadow-[0_0_8px_#6bff8f]" />
          <span>Gateway operacional</span>
        </div>
        <span>{{ items.length }} artefato(s) · {{ publishedCount }} publicado(s)</span>
        <span>Última sinc: painel ao vivo</span>
      </div>
      <div class="flex flex-wrap gap-4">
        <RouterLink to="/configuracoes" class="hover:text-primary transition-colors">Configurações</RouterLink>
        <RouterLink to="/auditoria" class="hover:text-primary transition-colors">Auditoria</RouterLink>
      </div>
    </div>
  </div>
</template>
