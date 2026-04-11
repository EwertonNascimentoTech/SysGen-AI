<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type GovernanceRule = {
  id: number;
  name: string;
  description: string | null;
  rule_key: string;
  min_tags_value: number | null;
  active: boolean;
  on_violation: "bloqueio" | "alerta";
};

const auth = useAuthStore();
const router = useRouter();
const canAccess = computed(() => auth.hasRole("admin", "coordenador"));

const rules = ref<GovernanceRule[]>([]);
const loadErr = ref("");
const err = ref("");

const searchQ = ref("");
const filterRuleKey = ref<string>("all");
const filterStatus = ref<"all" | "active" | "inactive">("all");
const showAdvanced = ref(false);

const page = ref(1);
const pageSize = 8;

const modalOpen = ref(false);
const editingId = ref<number | null>(null);
const draft = ref({
  name: "",
  description: "",
  rule_key: "require_po_assigned",
  min_tags_value: 1 as number,
  active: true,
  on_violation: "bloqueio" as "bloqueio" | "alerta",
});

const RULE_KEY_OPTIONS: { value: string; label: string; icon: string }[] = [
  { value: "require_description", label: "Descrição mínima (≥10 caracteres)", icon: "notes" },
  { value: "require_attachment_audit", label: "Anexo de auditoria", icon: "attach_file" },
  { value: "require_po_assigned", label: "Product Owner atribuído", icon: "verified_user" },
  { value: "require_github_tag", label: "Tag GitHub informada", icon: "terminal" },
  { value: "min_tag_count", label: "Mínimo de tags GitHub", icon: "sell" },
  { value: "require_github_repo", label: "Repositório GitHub vinculado (URL)", icon: "code" },
  { value: "require_methodology_prd", label: "Metodologia PRD no projeto", icon: "description" },
  { value: "require_any_attachment", label: "Pelo menos um anexo (qualquer)", icon: "attach_file_add" },
];

/** Ideias para evolução (ainda não implementadas no motor). */
const ROADMAP_IDEAS: string[] = [
  "Status de pipeline CI/CD (build/test verde antes de homologar).",
  "Issue/milestone GitHub obrigatório vinculado ao projeto.",
  "Checklist formal com assinaturas (ex.: comité de mudança).",
  "Campos customizados obrigatórios (orçamento, classificação de risco, patrocinador).",
  "Integração com ITSM (incidente/ticket resolvido antes do go-live).",
  "Janela de manutenção / blackout dates para deploy.",
  "Duas aprovações distintas (quatro olhos) para produção.",
  "Limite de WIP por fase ou por PO.",
  "Wiki/documentação gerada com status “pronta”.",
  "Dependências entre projetos ou épicos concluídos.",
];

function ruleKeyLabel(key: string) {
  return RULE_KEY_OPTIONS.find((o) => o.value === key)?.label ?? key;
}

function ruleKeyIcon(key: string) {
  return RULE_KEY_OPTIONS.find((o) => o.value === key)?.icon ?? "rule";
}

async function loadRules() {
  loadErr.value = "";
  try {
    const raw = await api<GovernanceRule[]>("/governance-advance-rules");
    rules.value = raw.map((r) => ({
      ...r,
      on_violation: r.on_violation === "alerta" ? "alerta" : "bloqueio",
    }));
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : "Erro ao carregar regras";
  }
}

onMounted(async () => {
  if (!canAccess.value) return;
  await loadRules();
});

const filtered = computed(() => {
  let list = rules.value.slice();
  const q = searchQ.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q) ||
        ruleKeyLabel(r.rule_key).toLowerCase().includes(q),
    );
  }
  if (filterRuleKey.value !== "all") list = list.filter((r) => r.rule_key === filterRuleKey.value);
  if (filterStatus.value === "active") list = list.filter((r) => r.active);
  if (filterStatus.value === "inactive") list = list.filter((r) => !r.active);
  return list.sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
});

const totalFiltered = computed(() => filtered.value.length);
const totalPages = computed(() => Math.max(1, Math.ceil(totalFiltered.value / pageSize)));

watch([searchQ, filterRuleKey, filterStatus], () => {
  page.value = 1;
});

watch(totalPages, (tp) => {
  if (page.value > tp) page.value = tp;
});

const pageRows = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filtered.value.slice(start, start + pageSize);
});

const compliancePct = computed(() => {
  if (!rules.value.length) return 0;
  return Math.round((rules.value.filter((r) => r.active).length / rules.value.length) * 100);
});

function violationBadge(v: GovernanceRule["on_violation"]) {
  if (v === "alerta") return { label: "Só alerta", cls: "bg-secondary-container text-on-secondary-container" };
  return { label: "Bloqueia avanço", cls: "bg-error-container text-error" };
}

function openCreate() {
  err.value = "";
  editingId.value = null;
  draft.value = {
    name: "",
    description: "",
    rule_key: "require_po_assigned",
    min_tags_value: 1,
    active: true,
    on_violation: "bloqueio",
  };
  modalOpen.value = true;
}

function openEdit(r: GovernanceRule) {
  err.value = "";
  editingId.value = r.id;
  draft.value = {
    name: r.name,
    description: r.description ?? "",
    rule_key: r.rule_key,
    min_tags_value: r.min_tags_value ?? 1,
    active: r.active,
    on_violation: r.on_violation ?? "bloqueio",
  };
  modalOpen.value = true;
}

function closeModal() {
  modalOpen.value = false;
  editingId.value = null;
  err.value = "";
}

async function saveDraft() {
  err.value = "";
  const name = draft.value.name.trim();
  if (!name) {
    err.value = "Informe o nome da regra.";
    return;
  }
  if (draft.value.rule_key === "min_tag_count") {
    const v = Math.max(1, Math.min(50, Number(draft.value.min_tags_value) || 0));
    if (v < 1) {
      err.value = "Informe o mínimo de tags (1–50).";
      return;
    }
    draft.value.min_tags_value = v;
  }
  try {
    if (editingId.value != null) {
      const body: Record<string, unknown> = {
        name,
        description: draft.value.description.trim() || null,
        rule_key: draft.value.rule_key,
        active: draft.value.active,
        on_violation: draft.value.on_violation,
      };
      if (draft.value.rule_key === "min_tag_count") body.min_tags_value = draft.value.min_tags_value;
      else body.min_tags_value = null;
      await api(`/governance-advance-rules/${editingId.value}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    } else {
      await api("/governance-advance-rules", {
        method: "POST",
        body: JSON.stringify({
          name,
          description: draft.value.description.trim() || null,
          rule_key: draft.value.rule_key,
          min_tags_value: draft.value.rule_key === "min_tag_count" ? draft.value.min_tags_value : null,
          active: draft.value.active,
          on_violation: draft.value.on_violation,
        }),
      });
    }
    closeModal();
    await loadRules();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Não foi possível salvar.";
  }
}

async function removeRule(r: GovernanceRule) {
  if (!confirm(`Remover a regra “${r.name}”? Fases que a usam deixam de aplicá-la.`)) return;
  try {
    await api(`/governance-advance-rules/${r.id}`, { method: "DELETE" });
    await loadRules();
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : "Erro ao remover";
  }
}

function applyAiSuggestion() {
  err.value = "";
  editingId.value = null;
  draft.value = {
    name: "Bloqueio por ausência de tag em release",
    description:
      "Exige tag GitHub alinhada ao release antes de homologação, reduzindo deploys sem rastreabilidade.",
    rule_key: "require_github_tag",
    min_tags_value: 1,
    active: true,
    on_violation: "bloqueio",
  };
  modalOpen.value = true;
}

function goPage(p: number) {
  page.value = Math.min(Math.max(1, p), totalPages.value);
}

function detailLine(r: GovernanceRule) {
  if (r.rule_key === "min_tag_count" && r.min_tags_value != null) {
    return `Mínimo: ${r.min_tags_value} tag(s) (separadas por vírgula).`;
  }
  return r.description ?? "—";
}

/** Igual à página Templates: volta no histórico ou abre Configurações. */
function leaveRegrasToPrevious() {
  const pos = (window.history.state as { position?: number } | null)?.position;
  if (pos === 1) {
    void router.push({ name: "config" });
    return;
  }
  void router.back();
}
</script>

<template>
  <div v-if="!canAccess" class="max-w-xl rounded-xl bg-surface-container-low p-8 text-on-surface-variant font-body">
    <div class="mb-4">
      <button
        type="button"
        class="inline-flex items-center gap-2 text-sm font-body font-medium text-on-surface-variant hover:text-primary transition-colors"
        @click="leaveRegrasToPrevious"
      >
        <span class="material-symbols-outlined text-xl leading-none" aria-hidden="true">arrow_back</span>
        Voltar
      </button>
    </div>
    <p class="text-sm">Apenas administradores e coordenadores podem gerir regras de avanço.</p>
  </div>

  <div v-else class="space-y-8 -mt-2 font-body">
    <div class="mb-2">
      <button
        type="button"
        class="inline-flex items-center gap-2 text-sm font-body font-medium text-on-surface-variant hover:text-primary transition-colors"
        @click="leaveRegrasToPrevious"
      >
        <span class="material-symbols-outlined text-xl leading-none" aria-hidden="true">arrow_back</span>
        Voltar
      </button>
    </div>
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div>
        <h1 class="font-headline text-4xl font-extrabold text-on-surface tracking-tight mb-2">Governança de fluxo</h1>
        <p class="text-on-surface-variant max-w-2xl text-lg font-light leading-relaxed">
          Catálogo único de regras usadas nas fases do Kanban. Edite aqui; em Templates → Configuração de fases, selecione quais regras
          aplicam a cada etapa.
        </p>
      </div>
      <button
        type="button"
        class="editorial-gradient text-on-primary px-6 py-3 rounded-md font-bold flex items-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all shadow-lg shrink-0 font-label text-sm uppercase tracking-wide"
        @click="openCreate"
      >
        <span class="material-symbols-outlined text-lg">add</span>
        Nova regra
      </button>
    </div>

    <p v-if="loadErr" class="text-error text-sm">{{ loadErr }}</p>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 bg-surface-container-low p-2 rounded-xl">
      <div class="relative flex items-center min-w-0">
        <span class="material-symbols-outlined absolute left-4 text-outline pointer-events-none">search</span>
        <input
          v-model="searchQ"
          type="search"
          class="w-full bg-surface-container-lowest border-none rounded-lg pl-12 pr-4 py-3 text-sm text-on-surface focus:ring-1 focus:ring-primary/20 placeholder:text-outline/60 outline-none"
          placeholder="Buscar por nome ou tipo..."
        />
      </div>
      <select
        v-model="filterRuleKey"
        class="bg-surface-container-lowest border-none rounded-lg py-3 px-4 text-sm text-on-surface focus:ring-1 focus:ring-primary/20 outline-none"
      >
        <option value="all">Todos os tipos</option>
        <option v-for="o in RULE_KEY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <select
        v-model="filterStatus"
        class="bg-surface-container-lowest border-none rounded-lg py-3 px-4 text-sm text-on-surface focus:ring-1 focus:ring-primary/20 outline-none"
      >
        <option value="all">Todos os status</option>
        <option value="active">Ativo</option>
        <option value="inactive">Inativo</option>
      </select>
      <div class="flex items-center justify-end px-2 md:px-4">
        <button
          type="button"
          class="text-xs font-bold uppercase tracking-widest text-primary flex items-center gap-2 hover:underline font-label"
          @click="showAdvanced = !showAdvanced"
        >
          <span class="material-symbols-outlined text-sm">info</span>
          Dicas
        </button>
      </div>
    </div>

    <div
      v-if="showAdvanced"
      class="text-xs text-on-surface-variant bg-surface-container-low/80 rounded-xl px-4 py-3 border border-outline-variant/10 space-y-3"
    >
      <p>
        <strong class="text-on-surface">Bloqueio vs. alerta:</strong> em “Bloqueia avanço”, o cartão não muda de coluna e a API devolve
        erro (mensagem visível no quadro). Em “Só alerta”, o avanço é permitido e as mensagens aparecem após o movimento como aviso de
        governança.
      </p>
      <p>
        Regras inativas não entram na validação. Para “mínimo de tags”, crie entradas distintas (ex.: 2 vs. 3 tags) e escolha a adequada em
        cada fase.
      </p>
      <div>
        <p class="font-bold text-on-surface mb-1">Ideias para novas validações (roadmap)</p>
        <ul class="list-disc pl-5 space-y-1">
          <li v-for="(idea, i) in ROADMAP_IDEAS" :key="i">{{ idea }}</li>
        </ul>
      </div>
    </div>

    <div class="bg-surface-container-low rounded-xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full border-separate border-spacing-y-2 px-4 min-w-[720px]">
          <thead>
            <tr class="text-left text-xs font-bold text-outline-variant uppercase tracking-widest font-label">
              <th class="py-4 px-4">Regra</th>
              <th class="py-4 px-4">O que valida</th>
              <th class="py-4 px-4">Se violar</th>
              <th class="py-4 px-4">Status</th>
              <th class="py-4 px-4 text-right">Ações</th>
            </tr>
          </thead>
          <tbody class="text-sm">
            <tr
              v-for="r in pageRows"
              :key="r.id"
              class="bg-surface-container-lowest hover:-translate-y-0.5 transition-transform duration-200 shadow-sm"
            >
              <td class="py-5 px-4 rounded-l-lg align-top">
                <div class="flex flex-col gap-1">
                  <span class="font-bold text-on-surface text-base font-headline">{{ r.name }}</span>
                  <span class="text-on-surface-variant font-normal leading-snug">{{ detailLine(r) }}</span>
                </div>
              </td>
              <td class="py-5 px-4 align-top">
                <div class="flex items-center gap-2">
                  <span class="material-symbols-outlined text-on-surface-variant text-lg">{{ ruleKeyIcon(r.rule_key) }}</span>
                  <span class="font-medium text-on-surface text-xs leading-tight max-w-[10rem]">{{ ruleKeyLabel(r.rule_key) }}</span>
                </div>
              </td>
              <td class="py-5 px-4 align-top">
                <span
                  class="px-3 py-1 rounded-full text-xs font-bold uppercase tracking-tight font-label"
                  :class="violationBadge(r.on_violation).cls"
                >
                  {{ violationBadge(r.on_violation).label }}
                </span>
              </td>
              <td class="py-5 px-4 align-top">
                <div class="flex items-center gap-1.5" :class="r.active ? '' : 'opacity-40'">
                  <div class="w-2 h-2 rounded-full shrink-0" :class="r.active ? 'bg-on-tertiary-container' : 'bg-outline'" />
                  <span
                    class="font-semibold font-label text-xs uppercase tracking-tight"
                    :class="r.active ? 'text-on-tertiary-container' : 'text-outline'"
                  >
                    {{ r.active ? "Ativo" : "Inativo" }}
                  </span>
                </div>
              </td>
              <td class="py-5 px-4 rounded-r-lg text-right align-top">
                <div class="flex justify-end gap-1">
                  <button
                    type="button"
                    class="p-2 hover:bg-surface-container text-on-surface-variant rounded-lg transition-colors"
                    title="Editar"
                    @click="openEdit(r)"
                  >
                    <span class="material-symbols-outlined text-[20px]">edit</span>
                  </button>
                  <button
                    type="button"
                    class="p-2 hover:bg-error-container/20 text-error rounded-lg transition-colors"
                    title="Remover"
                    @click="removeRule(r)"
                  >
                    <span class="material-symbols-outlined text-[20px]">delete</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="pageRows.length === 0 && !loadErr"
        class="px-8 py-12 text-center text-on-surface-variant text-sm italic"
      >
        Nenhuma regra corresponde aos filtros.
      </div>

      <div class="px-8 py-6 flex flex-col sm:flex-row justify-between items-center gap-4 bg-surface-container-low border-t border-outline-variant/10">
        <span class="text-xs font-medium text-on-surface-variant tracking-wider uppercase font-label text-center sm:text-left">
          Mostrando {{ pageRows.length }} de {{ totalFiltered }} regra(s)
        </span>
        <div v-if="totalPages > 1" class="flex gap-2 items-center">
          <button
            type="button"
            class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-surface-container-highest transition-colors disabled:opacity-30"
            :disabled="page <= 1"
            aria-label="Página anterior"
            @click="goPage(page - 1)"
          >
            <span class="material-symbols-outlined text-sm">chevron_left</span>
          </button>
          <button
            v-for="p in totalPages"
            :key="p"
            type="button"
            class="w-8 h-8 flex items-center justify-center rounded-lg text-xs font-bold transition-colors"
            :class="p === page ? 'bg-primary text-on-primary' : 'hover:bg-surface-container-highest text-on-surface'"
            @click="goPage(p)"
          >
            {{ p }}
          </button>
          <button
            type="button"
            class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-surface-container-highest transition-colors disabled:opacity-30"
            :disabled="page >= totalPages"
            aria-label="Próxima página"
            @click="goPage(page + 1)"
          >
            <span class="material-symbols-outlined text-sm">chevron_right</span>
          </button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div class="col-span-1 p-6 bg-surface-container-lowest rounded-xl space-y-4 shadow-sm">
        <div class="flex justify-between items-start">
          <span class="text-[10px] font-black uppercase tracking-widest text-outline font-label">Catálogo</span>
          <span class="material-symbols-outlined text-tertiary-fixed-dim" style="font-variation-settings: 'FILL' 1">bolt</span>
        </div>
        <div class="space-y-1">
          <h2 class="font-headline text-2xl font-extrabold tracking-tight text-on-surface">{{ compliancePct }}%</h2>
          <p class="text-sm text-on-surface-variant leading-snug">Regras ativas no catálogo (disponíveis para vincular às fases).</p>
        </div>
        <div class="w-full bg-surface-container rounded-full h-1 overflow-hidden">
          <div class="bg-tertiary-fixed-dim h-1 rounded-full transition-all duration-500" :style="{ width: `${compliancePct}%` }" />
        </div>
      </div>

      <div class="col-span-1 md:col-span-2 relative overflow-hidden p-6 bg-primary-container text-white rounded-xl flex flex-col sm:flex-row items-start sm:items-center gap-6">
        <div class="relative z-10 flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-2 h-2 rounded-full bg-tertiary-fixed animate-pulse shrink-0" />
            <span class="text-[10px] font-black uppercase tracking-widest text-primary-fixed font-label">Sugestão</span>
          </div>
          <h3 class="font-headline text-xl font-bold mb-2 text-white">Padronizar tag de release</h3>
          <p class="text-sm text-outline-variant leading-relaxed">
            Crie uma regra “Tag GitHub informada” e associe-a às fases após desenvolvimento para reforçar rastreabilidade.
          </p>
        </div>
        <div class="relative z-10 shrink-0 w-full sm:w-auto">
          <button
            type="button"
            class="w-full sm:w-auto bg-tertiary-fixed text-on-tertiary-fixed px-4 py-2 rounded-md font-bold text-sm whitespace-nowrap hover:scale-[1.02] active:scale-[0.98] transition-transform font-label"
            @click="applyAiSuggestion"
          >
            Usar modelo
          </button>
        </div>
        <div
          class="absolute inset-0 opacity-20 pointer-events-none"
          style="background: radial-gradient(circle at top right, #6bff8f, transparent)"
        />
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="modalOpen"
        class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-primary-container/40 backdrop-blur-sm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="advance-rule-modal-title"
        @click.self="closeModal"
      >
        <div class="w-full max-w-xl bg-surface-container-lowest rounded-xl shadow-2xl p-6 md:p-8 max-h-[90vh] overflow-y-auto">
          <div class="flex justify-between items-center mb-6 gap-4">
            <h2 id="advance-rule-modal-title" class="text-2xl font-black font-headline tracking-tight text-on-surface">
              {{ editingId != null ? "Editar regra" : "Nova regra" }}
            </h2>
            <button type="button" class="text-outline hover:text-on-surface transition-colors p-1 rounded-lg" aria-label="Fechar" @click="closeModal">
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>

          <p v-if="err" class="text-error text-sm mb-4">{{ err }}</p>

          <form class="space-y-6" @submit.prevent="saveDraft">
            <div class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-outline font-label block">Nome</label>
              <input
                v-model="draft.name"
                type="text"
                class="w-full border-b border-outline-variant/40 focus:border-primary focus:ring-0 px-0 py-2 text-base outline-none bg-transparent text-on-surface"
                placeholder="Ex.: PO obrigatório na homologação"
              />
            </div>
            <div class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-outline font-label block">Descrição (opcional)</label>
              <textarea
                v-model="draft.description"
                rows="2"
                class="w-full border border-outline-variant/15 rounded-lg focus:border-primary focus:ring-1 focus:ring-primary/20 p-3 text-sm outline-none bg-surface-container-low/50 text-on-surface"
              />
            </div>
            <div class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-outline font-label block">O que valida no avanço</label>
              <select
                v-model="draft.rule_key"
                class="w-full border-b border-outline-variant/40 focus:border-primary focus:ring-0 px-0 py-2 text-sm outline-none bg-transparent text-on-surface"
              >
                <option v-for="o in RULE_KEY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div v-if="draft.rule_key === 'min_tag_count'" class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-outline font-label block">Mínimo de tags</label>
              <input
                v-model.number="draft.min_tags_value"
                type="number"
                min="1"
                max="50"
                class="w-full rounded-md border border-outline-variant/20 px-3 py-2 text-sm bg-surface-container-lowest"
              />
            </div>
            <div class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-outline font-label block">Se não cumprir a regra</label>
              <select
                v-model="draft.on_violation"
                class="w-full border-b border-outline-variant/40 focus:border-primary focus:ring-0 px-0 py-2 text-sm outline-none bg-transparent text-on-surface"
              >
                <option value="bloqueio">Bloquear avanço (mostrar erro ao mover)</option>
                <option value="alerta">Permitir avanço e mostrar alerta depois</option>
              </select>
            </div>
            <label class="flex items-center gap-3 py-2 cursor-pointer select-none">
              <input v-model="draft.active" type="checkbox" class="rounded border-outline-variant text-primary focus:ring-primary/30 w-4 h-4" />
              <span class="text-sm font-bold text-on-surface">Regra ativa</span>
            </label>
            <div class="pt-4 flex flex-col-reverse sm:flex-row gap-3">
              <button
                type="button"
                class="flex-1 py-3 px-4 rounded-md border border-outline-variant/20 text-sm font-bold hover:bg-surface-container transition-colors font-label"
                @click="closeModal"
              >
                Cancelar
              </button>
              <button
                type="submit"
                class="flex-1 py-3 px-4 rounded-md bg-primary text-on-primary text-sm font-bold hover:opacity-90 transition-opacity font-label"
              >
                Salvar
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>
