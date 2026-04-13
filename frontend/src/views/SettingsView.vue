<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type TabId = "geral" | "integracoes" | "permissoes";

const auth = useAuthStore();
const route = useRoute();

type GeneralSettingsOut = {
  org_name: string;
  locale: string;
  audit_strict: boolean;
  ai_indexing: boolean;
};

type GithubAuthStatus = {
  oauth_configured: boolean;
  github_client_id_set?: boolean;
  github_client_secret_set?: boolean;
  /** URL que o backend envia ao GitHub como redirect_uri — deve ser a mesma no OAuth App. */
  oauth_redirect_uri?: string;
};

const tab = ref<TabId>("geral");
const orgName = ref("SysGen AI");
const locale = ref("pt-BR");
const auditStrict = ref(true);
const aiIndexing = ref(false);
const saveMsg = ref("");
const generalErr = ref("");
const generalLoading = ref(false);
const savingGeneral = ref(false);

const canPersistGeneral = computed(() => auth.hasRole("admin", "coordenador"));

const ghPublic = ref<GithubAuthStatus | null>(null);
const ghLoading = ref(false);
const ghErr = ref("");
const ghMsg = ref("");

const oauthDiag = computed(() => {
  const g = ghPublic.value;
  if (!g || g.oauth_configured) return null;
  const idOk = g.github_client_id_set === true;
  const secOk = g.github_client_secret_set === true;
  if (!idOk && !secOk) return "O servidor não recebeu Client ID nem Client Secret.";
  if (idOk && !secOk) return "Client ID está definido; falta o Client Secret.";
  if (!idOk && secOk) return "Client Secret está definido; falta o Client ID.";
  return null;
});

const tabNavItems: ({ kind: "tab"; id: TabId; label: string } | { kind: "link"; to: string; label: string })[] = [
  { kind: "tab", id: "geral", label: "Geral" },
  { kind: "link", to: "/templates", label: "Templates" },
  { kind: "link", to: "/regras-avanco", label: "Regras de avanço" },
  { kind: "link", to: "/usuarios", label: "Usuários" },
  { kind: "link", to: "/auditoria", label: "Auditoria" },
  { kind: "tab", id: "integracoes", label: "Integrações" },
  { kind: "tab", id: "permissoes", label: "Permissões" },
];

async function loadGeneralSettings() {
  generalErr.value = "";
  saveMsg.value = "";
  generalLoading.value = true;
  try {
    await auth.fetchMe();
    const data = await api<GeneralSettingsOut>("/system-settings/general");
    orgName.value = data.org_name;
    locale.value = data.locale;
    auditStrict.value = data.audit_strict;
    aiIndexing.value = data.ai_indexing;
  } catch (e) {
    generalErr.value =
      e instanceof Error ? e.message : "Não foi possível carregar os parâmetros gerais.";
  } finally {
    generalLoading.value = false;
  }
}

async function discard() {
  saveMsg.value = "";
  await loadGeneralSettings();
}

async function save() {
  saveMsg.value = "";
  generalErr.value = "";
  if (!canPersistGeneral.value) {
    generalErr.value =
      "Apenas administradores ou coordenadores podem guardar a configuração geral.";
    return;
  }
  savingGeneral.value = true;
  try {
    await api<GeneralSettingsOut>("/system-settings/general", {
      method: "PATCH",
      body: JSON.stringify({
        org_name: orgName.value,
        locale: locale.value,
        audit_strict: auditStrict.value,
        ai_indexing: aiIndexing.value,
      }),
    });
    saveMsg.value = "Configuração guardada no servidor.";
  } catch (e) {
    generalErr.value = e instanceof Error ? e.message : "Erro ao guardar a configuração.";
  } finally {
    savingGeneral.value = false;
  }
}

function implementGuideline() {
  window.alert("Diretriz sugerida: ative auditoria cruzada nas integrações GitHub (documentação em README).");
}

function exportMatrix() {
  window.alert("Exportação da matriz: em breve (CSV/PDF).");
}

async function loadGithubPublic() {
  try {
    ghPublic.value = await api<GithubAuthStatus>("/auth/github/status");
  } catch {
    ghPublic.value = null;
  }
}

async function loadIntegrationsTab() {
  ghMsg.value = "";
  ghErr.value = "";
  ghLoading.value = true;
  try {
    await loadGithubPublic();
    await auth.fetchMe();
  } catch (e) {
    ghErr.value = e instanceof Error ? e.message : "Erro ao carregar integração GitHub.";
  } finally {
    ghLoading.value = false;
  }
}

function startGithubOAuth() {
  const next = "/configuracoes?tab=integracoes";
  window.location.href = `/api/auth/github/authorize?next=${encodeURIComponent(next)}`;
}

function applyTabFromQuery() {
  const t = route.query.tab;
  const raw = typeof t === "string" ? t : Array.isArray(t) ? t[0] : undefined;
  const allowed: TabId[] = ["geral", "integracoes", "permissoes"];
  if (raw && (allowed as string[]).includes(raw)) tab.value = raw as TabId;
}

watch(tab, (t) => {
  if (t === "integracoes") void loadIntegrationsTab();
});

watch(
  () => route.fullPath,
  () => {
    applyTabFromQuery();
    if (tab.value === "integracoes") void loadIntegrationsTab();
  },
);

onMounted(() => {
  applyTabFromQuery();
  void loadGeneralSettings();
  if (tab.value === "integracoes") void loadIntegrationsTab();
});
</script>

<template>
  <div class="-mx-2 md:-mx-4 max-w-7xl mx-auto px-2 md:px-4 pb-12 space-y-8">
    <div class="mb-2">
      <h2 class="text-3xl font-extrabold font-headline text-on-surface tracking-tight mb-2">Configurações do sistema</h2>
      <p class="text-on-surface-variant max-w-2xl text-sm font-body leading-relaxed">
        Configure parâmetros globais, protocolos de segurança e ganchos de integração para o ecossistema da plataforma.
      </p>
    </div>

    <!-- Abas (protótipo configura_es_do_sistema_pt_br) -->
    <div class="flex flex-wrap gap-1 bg-surface-container-low p-1 rounded-lg w-fit border border-outline-variant/10">
      <template v-for="item in tabNavItems" :key="item.kind === 'tab' ? item.id : item.to">
        <button
          v-if="item.kind === 'tab'"
          type="button"
          class="px-6 py-2 text-sm rounded-md font-body transition-colors"
          :class="
            tab === item.id
              ? 'bg-surface-container-lowest shadow-sm text-primary font-semibold'
              : 'text-on-surface-variant font-medium hover:bg-surface-container hover:text-on-surface'
          "
          @click="tab = item.id"
        >
          {{ item.label }}
        </button>
        <RouterLink
          v-else
          :to="item.to"
          class="px-6 py-2 text-sm rounded-md font-body transition-colors text-on-surface-variant font-medium hover:bg-surface-container hover:text-on-surface inline-flex items-center justify-center"
        >
          {{ item.label }}
        </RouterLink>
      </template>
    </div>

    <p v-if="generalErr" class="text-sm text-error font-body">{{ generalErr }}</p>
    <p v-else-if="saveMsg" class="text-sm text-on-tertiary-container font-body">{{ saveMsg }}</p>

    <!-- Geral: grelha bento -->
    <div v-show="tab === 'geral'" class="grid grid-cols-12 gap-6">
      <div class="col-span-12 lg:col-span-8 bg-surface-container-lowest rounded-xl p-8 shadow-sm border border-outline-variant/10">
        <div class="flex items-center justify-between mb-8">
          <div>
            <h3 class="text-lg font-bold font-headline tracking-tight text-on-surface">Parâmetros gerais</h3>
            <p class="text-xs text-on-surface-variant uppercase tracking-widest mt-1 font-label">Configuração principal do ambiente</p>
          </div>
          <span class="material-symbols-outlined text-on-surface-variant">tune</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div class="space-y-2">
            <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider font-label">Nome da organização</label>
            <input
              v-model="orgName"
              type="text"
              :disabled="generalLoading || !canPersistGeneral"
              class="w-full bg-surface-container-low border-none rounded-md px-4 py-3 text-sm font-medium focus:ring-1 focus:ring-primary-container outline-none font-body border border-outline-variant/10 disabled:opacity-60"
            />
          </div>
          <div class="space-y-2">
            <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider font-label">Localidade do sistema</label>
            <select
              v-model="locale"
              :disabled="generalLoading || !canPersistGeneral"
              class="w-full bg-surface-container-low border-none rounded-md px-4 py-3 text-sm font-medium focus:ring-1 focus:ring-primary-container outline-none font-body border border-outline-variant/10 disabled:opacity-60"
            >
              <option value="pt-BR">Português (Brasil)</option>
              <option value="en-US">English (United States)</option>
            </select>
          </div>
          <div class="col-span-1 md:col-span-2 space-y-4">
            <div class="flex items-center justify-between p-4 bg-surface-container-low rounded-lg border border-outline-variant/10">
              <div>
                <h4 class="text-sm font-bold text-on-surface font-headline">Log de auditoria estrito</h4>
                <p class="text-xs text-on-surface-variant font-body">Registrar operações sensíveis e integrações (comportamento desejado em produção).</p>
              </div>
              <button
                type="button"
                role="switch"
                :aria-checked="auditStrict"
                :disabled="generalLoading || !canPersistGeneral"
                class="w-10 h-5 rounded-full relative flex items-center px-1 transition-colors shrink-0 disabled:opacity-50 disabled:pointer-events-none"
                :class="auditStrict ? 'bg-tertiary-container' : 'bg-outline-variant/30'"
                @click="auditStrict = !auditStrict"
              >
                <span
                  class="w-3 h-3 rounded-full transition-all"
                  :class="auditStrict ? 'bg-tertiary-fixed ml-auto' : 'bg-white'"
                />
              </button>
            </div>
            <div class="flex items-center justify-between p-4 bg-surface-container-low rounded-lg border border-outline-variant/10">
              <div>
                <h4 class="text-sm font-bold text-on-surface font-headline">Indexação preditiva por IA</h4>
                <p class="text-xs text-on-surface-variant font-body">Etiquetagem autónoma de metadados para novos projetos (opcional / roadmap).</p>
              </div>
              <button
                type="button"
                role="switch"
                :aria-checked="aiIndexing"
                :disabled="generalLoading || !canPersistGeneral"
                class="w-10 h-5 rounded-full relative flex items-center px-1 transition-colors shrink-0 disabled:opacity-50 disabled:pointer-events-none"
                :class="aiIndexing ? 'bg-tertiary-container' : 'bg-outline-variant/30'"
                @click="aiIndexing = !aiIndexing"
              >
                <span
                  class="w-3 h-3 rounded-full transition-all"
                  :class="aiIndexing ? 'bg-tertiary-fixed ml-auto' : 'bg-white'"
                />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="col-span-12 lg:col-span-4 bg-primary-container text-primary-fixed rounded-xl p-8 relative overflow-hidden flex flex-col justify-between border border-outline-variant/10">
        <div class="relative z-10">
          <div class="flex items-center gap-2 mb-4">
            <span class="material-symbols-outlined text-tertiary-fixed">smart_toy</span>
            <span class="text-xs font-bold uppercase tracking-widest text-tertiary-fixed font-label">Insight de governança IA</span>
          </div>
          <h3 class="text-2xl font-bold font-headline leading-tight mb-4 text-primary-fixed">Sugestão de protocolo de segurança</h3>
          <p class="text-sm text-on-primary-container leading-relaxed font-body">
            Com integrações GitHub ativas, recomenda-se reforçar a auditoria de referência cruzada para preservar a linhagem de artefatos e PRs.
          </p>
        </div>
        <button
          type="button"
          class="relative z-10 mt-8 w-full py-3 bg-tertiary-fixed text-on-tertiary-fixed font-bold text-sm rounded-md hover:opacity-90 transition-opacity font-body"
          @click="implementGuideline"
        >
          Implementar diretriz
        </button>
        <div class="absolute -bottom-20 -right-20 w-64 h-64 bg-tertiary-fixed/10 rounded-full blur-3xl pointer-events-none" />
      </div>
    </div>

    <!-- Integrações -->
    <div v-show="tab === 'integracoes'" class="grid grid-cols-12 gap-6">
      <div class="col-span-12 lg:col-span-6 bg-surface-container-low rounded-xl p-8 border border-outline-variant/10">
        <div class="flex items-center gap-4 mb-6">
          <div class="p-3 bg-white rounded-lg shadow-sm border border-outline-variant/10">
            <span class="material-symbols-outlined text-2xl text-on-surface">hub</span>
          </div>
          <div>
            <h3 class="text-lg font-bold font-headline tracking-tight text-on-surface">Integração GitHub</h3>
            <p class="text-xs text-on-surface-variant uppercase tracking-widest font-label">Apenas OAuth</p>
          </div>
        </div>
        <div class="space-y-4">
          <p class="text-sm text-on-surface-variant font-body leading-relaxed">
            A ligação da <strong class="text-on-surface">sua conta GitHub</strong> à plataforma é feita
            <strong class="text-on-surface">sempre</strong> através do
            <strong class="text-on-surface">login OAuth do GitHub</strong>. Tags, validação de refs e geração de Wiki usam apenas o
            token dessa conta — cada utilizador acede só ao que o GitHub permite para o seu utilizador.
          </p>
          <div class="p-4 bg-surface-container-lowest rounded-lg border border-outline-variant/10 space-y-3">
            <p v-if="ghPublic?.oauth_redirect_uri" class="text-xs text-on-surface-variant font-body leading-relaxed">
              No GitHub, em OAuth App →
              <strong class="text-on-surface">Authorization callback URL</strong>, use
              <strong class="text-on-surface break-all">{{ ghPublic.oauth_redirect_uri }}</strong>
              (tem de ser <strong class="text-on-surface">exatamente</strong> isto; se registou
              <code class="rounded bg-surface-container-high px-1 text-[11px]">127.0.0.1:8000</code> ou outro host/porta, o GitHub
              recusa).
            </p>
            <div class="flex items-center gap-2 text-sm font-bold text-on-surface font-body">
              <span
                class="w-2 h-2 rounded-full shrink-0"
                :class="ghPublic?.oauth_configured ? 'bg-tertiary-fixed-dim' : 'bg-outline-variant'"
              />
              {{ ghPublic?.oauth_configured ? "OAuth configurado no servidor" : "OAuth não configurado no servidor" }}
            </div>
            <div class="flex items-center gap-2 text-sm font-body text-on-surface">
              <span
                class="w-2 h-2 rounded-full shrink-0"
                :class="auth.me?.has_github ? 'bg-tertiary-fixed-dim' : 'bg-outline-variant'"
              />
              {{
                auth.me?.has_github
                  ? "A sua conta está ligada ao GitHub (OAuth)"
                  : "A sua conta ainda não está ligada ao GitHub"
              }}
            </div>
            <button
              v-if="ghPublic?.oauth_configured"
              type="button"
              class="w-full rounded-md bg-secondary py-2.5 text-sm font-semibold text-on-secondary font-body hover:opacity-95 disabled:opacity-50"
              :disabled="ghLoading"
              @click="startGithubOAuth"
            >
              Ligar conta GitHub (OAuth)
            </button>
            <div
              v-else
              class="rounded-lg border border-outline-variant/25 bg-surface-container-high/40 p-3 text-xs text-on-surface-variant font-body leading-relaxed space-y-2"
            >
              <p v-if="oauthDiag" class="text-on-surface font-medium">{{ oauthDiag }}</p>
              <p>
                Defina <strong class="text-on-surface">GITHUB_CLIENT_ID</strong> e
                <strong class="text-on-surface">GITHUB_CLIENT_SECRET</strong> e reinicie o backend.
              </p>
              <p>
                <strong class="text-on-surface">Docker Compose:</strong> edite o ficheiro
                <code class="rounded bg-surface-container-lowest px-1 text-[11px]">compose.env</code> na pasta
                <code class="rounded bg-surface-container-lowest px-1 text-[11px]">plataforma-governanca-ia/</code> (não basta
                alterar só o <code class="rounded bg-surface-container-lowest px-1 text-[11px]">.env.example</code>), depois
                <code class="rounded bg-surface-container-lowest px-1 text-[11px]">docker compose up -d</code>. O callback
                registado no GitHub deve ser
                <code class="rounded bg-surface-container-lowest px-1 text-[11px]">http://localhost:8080/api/auth/github/callback</code>
                (porta da UI no compose).
              </p>
              <p>
                <strong class="text-on-surface">Sem Docker:</strong> use
                <code class="rounded bg-surface-container-lowest px-1 text-[11px]">.env</code> na raiz do projeto ou em
                <code class="rounded bg-surface-container-lowest px-1 text-[11px]">backend/.env</code>. OAuth App:
                <a
                  href="https://github.com/settings/developers"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-primary underline font-medium"
                  >github.com/settings/developers</a
                >.
              </p>
              <p v-if="ghPublic === null" class="text-error">Não foi possível contactar o servidor para ler o estado OAuth.</p>
            </div>
            <p v-if="ghErr" class="text-sm text-error font-body">{{ ghErr }}</p>
            <p v-if="ghMsg" class="text-sm text-on-tertiary-container font-body">{{ ghMsg }}</p>
          </div>

          <p class="text-xs text-on-surface-variant font-body">
            Endpoint OAuth:
            <code class="bg-surface-container-lowest px-1 rounded text-[11px]">GET /api/auth/github/authorize</code>
          </p>
        </div>
      </div>
      <div class="col-span-12 lg:col-span-6 bg-surface-container-low rounded-xl p-8 border border-outline-variant/10">
        <h3 class="text-lg font-bold font-headline tracking-tight text-on-surface mb-2">Stack documentada</h3>
        <p class="text-sm text-on-surface-variant font-body mb-4">
          FastAPI, SQLAlchemy async, Vue 3, Pinia. Wiki assíncrona via fila em Redis
          (<code class="bg-surface-container-lowest px-1 rounded text-xs">python -m app.worker</code>).
        </p>
        <p class="text-sm text-on-surface-variant font-body">
          Anexos com MinIO/S3 quando <code class="bg-surface-container-lowest px-1 rounded text-xs">S3_ENDPOINT_URL</code> está definido.
        </p>
      </div>
    </div>

    <!-- Permissões: matriz -->
    <div v-show="tab === 'permissoes'" class="bg-surface-container-low rounded-xl p-8 border border-outline-variant/10">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h3 class="text-lg font-bold font-headline tracking-tight text-on-surface">Visão geral de permissões de cargo</h3>
          <p class="text-xs text-on-surface-variant uppercase tracking-widest mt-1 font-label">Matriz de autoridade (referência)</p>
        </div>
        <button
          type="button"
          class="text-sm font-bold text-primary flex items-center gap-2 hover:underline font-body"
          @click="exportMatrix"
        >
          Exportar matriz <span class="material-symbols-outlined text-sm">download</span>
        </button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left min-w-[640px]">
          <thead>
            <tr class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest font-label">
              <th class="pb-4 pr-6 text-left">Cargo funcional</th>
              <th class="pb-4 px-6 text-center">Acesso de leitura</th>
              <th class="pb-4 px-6 text-center">Escrita / edição</th>
              <th class="pb-4 px-6 text-center">Meta governança</th>
              <th class="pb-4 px-6 text-center">Gestão de integração</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-variant/10">
            <tr class="group hover:bg-surface-container-lowest transition-colors">
              <td class="py-4 pr-6">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-full bg-slate-900 flex items-center justify-center text-white text-[10px] font-bold font-headline">AD</div>
                  <div>
                    <div class="text-sm font-bold text-on-surface font-headline">Administrador</div>
                    <div class="text-[10px] text-on-surface-variant italic font-body">Admin total</div>
                  </div>
                </div>
              </td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
            </tr>
            <tr class="group hover:bg-surface-container-lowest transition-colors">
              <td class="py-4 pr-6">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center text-on-secondary-container text-[10px] font-bold font-headline">
                    CO
                  </div>
                  <div>
                    <div class="text-sm font-bold text-on-surface font-headline">Coordenador</div>
                    <div class="text-[10px] text-on-surface-variant italic font-body">Líder operacional</div>
                  </div>
                </div>
              </td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-outline-variant">cancel</span></td>
            </tr>
            <tr class="group hover:bg-surface-container-lowest transition-colors">
              <td class="py-4 pr-6">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant text-[10px] font-bold font-headline">
                    PO
                  </div>
                  <div>
                    <div class="text-sm font-bold text-on-surface font-headline">Product owner</div>
                    <div class="text-[10px] text-on-surface-variant italic font-body">Backlog e priorização</div>
                  </div>
                </div>
              </td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-outline-variant">cancel</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-outline-variant">cancel</span></td>
            </tr>
            <tr class="group hover:bg-surface-container-lowest transition-colors">
              <td class="py-4 pr-6">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center text-on-surface text-[10px] font-bold font-headline">
                    DV
                  </div>
                  <div>
                    <div class="text-sm font-bold text-on-surface font-headline">Desenvolvedor</div>
                    <div class="text-[10px] text-on-surface-variant italic font-body">Contribuidor</div>
                  </div>
                </div>
              </td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-on-tertiary-container">check_circle</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-outline-variant">cancel</span></td>
              <td class="py-4 px-6 text-center"><span class="material-symbols-outlined text-outline-variant">cancel</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="flex flex-col sm:flex-row justify-end gap-4 border-t border-outline-variant/10 pt-8">
      <button
        type="button"
        class="px-8 py-3 text-sm font-bold text-on-surface-variant hover:text-primary transition-colors font-body order-2 sm:order-1 disabled:opacity-50"
        :disabled="generalLoading || savingGeneral"
        @click="discard"
      >
        Descartar alterações
      </button>
      <button
        type="button"
        class="px-8 py-3 bg-primary text-on-primary font-bold text-sm rounded-md shadow-lg shadow-black/5 hover:scale-[1.02] active:scale-95 transition-all font-body order-1 sm:order-2 disabled:opacity-50 disabled:hover:scale-100"
        :disabled="generalLoading || savingGeneral || !canPersistGeneral"
        :title="!canPersistGeneral ? 'Requer perfil administrador ou coordenador.' : undefined"
        @click="save"
      >
        {{ savingGeneral ? "A guardar…" : "Salvar configuração do sistema" }}
      </button>
    </div>
  </div>
</template>
