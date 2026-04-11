<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type Row = {
  id: number;
  created_at: string;
  actor_email: string;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  detail: string | null;
};

const auth = useAuthStore();
const router = useRouter();
const rows = ref<Row[]>([]);
const err = ref("");
const loading = ref(false);
const searchQ = ref("");
const filterUser = ref("");
const filterModule = ref("");
const filterActionKind = ref("");
const page = ref(1);
const pageSize = 25;

const canAccess = computed(() => auth.hasRole("admin", "coordenador"));

onMounted(async () => {
  if (!canAccess.value) return;
  await load();
});

async function load() {
  loading.value = true;
  err.value = "";
  try {
    rows.value = await api<Row[]>("/audit");
    page.value = 1;
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  } finally {
    loading.value = false;
  }
}

const uniqueEmails = computed(() => {
  const s = new Set(rows.value.map((r) => r.actor_email).filter(Boolean));
  return Array.from(s).sort();
});

const uniqueModules = computed(() => {
  const s = new Set(rows.value.map((r) => (r.entity_type ?? "").trim()).filter(Boolean) as string[]);
  return Array.from(s).sort();
});

function actionKind(action: string): "create" | "update" | "delete" | "other" {
  const a = action.toLowerCase();
  if (/exclu|delete|remove|apag/i.test(a)) return "delete";
  if (/criad|create|post|novo|inser/i.test(a)) return "create";
  if (/atualiz|update|modif|moviment|patch|put|alter/i.test(a)) return "update";
  return "other";
}

function actionPresentation(action: string) {
  const k = actionKind(action);
  if (k === "delete")
    return {
      icon: "delete",
      label: action.length > 32 ? action.slice(0, 32) + "…" : action,
      cls: "bg-error-container text-error",
    };
  if (k === "create")
    return {
      icon: "add_circle",
      label: action.length > 32 ? action.slice(0, 32) + "…" : action,
      cls: "bg-surface-container-high text-on-surface",
    };
  if (k === "update")
    return {
      icon: "update",
      label: action.length > 32 ? action.slice(0, 32) + "…" : action,
      cls: "bg-surface-container-high text-on-surface",
    };
  return {
    icon: "move_item",
    label: action.length > 32 ? action.slice(0, 32) + "…" : action,
    cls: "bg-surface-container-high text-on-surface",
  };
}

function rowState(r: Row) {
  if (actionKind(r.action) === "delete")
    return { label: "Aguardando aprovação", cls: "bg-surface-container-high text-on-surface-variant" };
  return { label: "Verificado", cls: "bg-tertiary-container text-on-tertiary-container" };
}

function formatParts(iso: string) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return { date: iso, time: "" };
    const pad = (n: number) => String(n).padStart(2, "0");
    return {
      date: `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()}`,
      time: `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} local`,
    };
  } catch {
    return { date: iso, time: "" };
  }
}

function initialsFromEmail(email: string) {
  const local = email.split("@")[0] ?? email;
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

function displayName(email: string) {
  const local = email.split("@")[0] ?? email;
  return local.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isSystemActor(email: string) {
  return /system|ia|bot|noreply/i.test(email);
}

const filtered = computed(() => {
  const q = searchQ.value.trim().toLowerCase();
  return rows.value.filter((r) => {
    if (filterUser.value && r.actor_email !== filterUser.value) return false;
    if (filterModule.value && (r.entity_type ?? "") !== filterModule.value) return false;
    if (filterActionKind.value) {
      const k = actionKind(r.action);
      const want = filterActionKind.value;
      if (want === "criacoes" && k !== "create") return false;
      if (want === "modificacoes" && (k === "create" || k === "delete")) return false;
      if (want === "exclusoes" && k !== "delete") return false;
    }
    if (!q) return true;
    const blob = [r.actor_email, r.action, r.entity_type, r.detail, String(r.entity_id)].join(" ").toLowerCase();
    return blob.includes(q);
  });
});

const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)));

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filtered.value.slice(start, start + pageSize);
});

watch([filtered, pageCount], () => {
  if (page.value > pageCount.value) page.value = pageCount.value;
});

function goPage(n: number) {
  page.value = Math.min(Math.max(1, n), pageCount.value);
}

function exportPdfHint() {
  window.alert("Para exportar em PDF, use Imprimir do navegador (Ctrl+P) e escolha “Salvar como PDF”.");
}

function leaveAuditToPrevious() {
  const pos = (window.history.state as { position?: number } | null)?.position;
  if (pos === 1) {
    void router.push({ name: "config" });
    return;
  }
  void router.back();
}
</script>

<template>
  <div class="-mx-2 md:-mx-4 space-y-8 px-2 md:px-4 pb-12">
    <div class="mb-2">
      <button
        type="button"
        class="inline-flex items-center gap-2 text-sm font-body font-medium text-on-surface-variant hover:text-primary transition-colors"
        @click="leaveAuditToPrevious"
      >
        <span class="material-symbols-outlined text-xl leading-none" aria-hidden="true">arrow_back</span>
        Voltar
      </button>
    </div>
    <template v-if="!canAccess">
      <div>
        <span class="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant font-label block">Integridade do sistema</span>
        <h2 class="text-3xl md:text-4xl font-headline font-extrabold tracking-tight text-on-surface mt-2">Trilha de auditoria</h2>
        <p class="text-sm text-on-surface-variant mt-2 max-w-2xl font-body">RF-20 — eventos de governança registrados no ledger.</p>
      </div>
      <div class="bg-surface-container-low border border-outline-variant/10 rounded-xl p-8 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant mb-2">lock</span>
        <p class="text-on-surface font-medium font-body">Acesso restrito a administradores e coordenadores.</p>
      </div>
    </template>

    <template v-else>
      <div class="flex flex-col lg:flex-row lg:justify-between lg:items-end gap-4">
        <div>
          <span class="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant font-label block">Integridade do sistema</span>
          <h2 class="text-3xl md:text-4xl font-headline font-extrabold tracking-tight text-on-surface mt-2">Trilha de auditoria</h2>
        </div>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="px-4 py-2 bg-surface-container-high text-on-surface text-sm font-semibold rounded-md flex items-center hover:bg-surface-container transition-colors font-body"
            @click="exportPdfHint"
          >
            <span class="material-symbols-outlined text-sm mr-2">download</span>
            Exportar PDF
          </button>
          <button
            type="button"
            class="px-4 py-2 bg-primary text-on-primary text-sm font-semibold rounded-md flex items-center shadow-lg shadow-black/5 font-body hover:opacity-90 disabled:opacity-50"
            :disabled="loading"
            @click="load"
          >
            <span class="material-symbols-outlined text-sm mr-2">refresh</span>
            Atualização em tempo real
          </button>
        </div>
      </div>

      <!-- Filtros (protótipo auditoria_governan_a_pt_br) -->
      <section class="p-6 bg-surface-container-low rounded-xl flex flex-wrap items-end gap-6 border border-outline-variant/5">
        <div class="flex flex-col flex-1 min-w-[200px]">
          <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant mb-2 font-label">Busca global</label>
          <div class="flex items-center bg-surface-container-lowest px-3 py-2 rounded-md shadow-sm border border-outline-variant/10">
            <span class="material-symbols-outlined text-sm text-outline mr-2">search</span>
            <input
              v-model="searchQ"
              type="search"
              class="flex-1 bg-transparent border-none text-sm font-medium outline-none font-body"
              placeholder="Filtrar logs de governança…"
              @input="page = 1"
            />
          </div>
        </div>
        <div class="flex flex-col">
          <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant mb-2 font-label">Acesso do usuário</label>
          <select
            v-model="filterUser"
            class="bg-surface-container-lowest border-none text-sm font-medium py-2 px-3 rounded-md shadow-sm min-w-[200px] focus:ring-1 focus:ring-primary font-body border border-outline-variant/10"
            @change="page = 1"
          >
            <option value="">Todos os colaboradores</option>
            <option v-for="e in uniqueEmails" :key="e" :value="e">{{ displayName(e) }}</option>
          </select>
        </div>
        <div class="flex flex-col">
          <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant mb-2 font-label">Módulo</label>
          <select
            v-model="filterModule"
            class="bg-surface-container-lowest border-none text-sm font-medium py-2 px-3 rounded-md shadow-sm min-w-[180px] focus:ring-1 focus:ring-primary font-body border border-outline-variant/10"
            @change="page = 1"
          >
            <option value="">Todos os módulos</option>
            <option v-for="m in uniqueModules" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <div class="flex flex-col">
          <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant mb-2 font-label">Tipo de ação</label>
          <select
            v-model="filterActionKind"
            class="bg-surface-container-lowest border-none text-sm font-medium py-2 px-3 rounded-md shadow-sm min-w-[160px] focus:ring-1 focus:ring-primary font-body border border-outline-variant/10"
            @change="page = 1"
          >
            <option value="">Tudo</option>
            <option value="criacoes">Criações</option>
            <option value="modificacoes">Modificações</option>
            <option value="exclusoes">Exclusões</option>
          </select>
        </div>
        <div class="flex justify-end items-end">
          <button
            type="button"
            class="bg-surface-container-highest text-on-surface p-2.5 rounded-md hover:bg-outline-variant/40 transition-colors border border-outline-variant/20"
            title="Redefinir filtros"
            @click="
              searchQ = '';
              filterUser = '';
              filterModule = '';
              filterActionKind = '';
              page = 1;
            "
          >
            <span class="material-symbols-outlined">filter_list</span>
          </button>
        </div>
      </section>

      <p v-if="err" class="text-error text-sm font-body">{{ err }}</p>
      <p v-if="loading" class="text-sm text-on-surface-variant font-body">A carregar eventos…</p>

      <div class="bg-surface-container-lowest rounded-xl overflow-hidden border border-outline-variant/10">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-separate border-spacing-0 min-w-[900px]">
            <thead>
              <tr class="bg-surface-container-low">
                <th class="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant border-b border-outline-variant/10 font-label">
                  Data e hora
                </th>
                <th class="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant border-b border-outline-variant/10 font-label">
                  Responsável
                </th>
                <th class="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant border-b border-outline-variant/10 font-label">
                  Ação
                </th>
                <th class="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant border-b border-outline-variant/10 font-label">
                  Entidade de recurso
                </th>
                <th class="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant border-b border-outline-variant/10 font-label">
                  Detalhes de telemetria
                </th>
                <th
                  class="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant border-b border-outline-variant/10 text-right font-label"
                >
                  Estado
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-variant/5">
              <tr v-for="r in pagedRows" :key="r.id" class="hover:bg-surface-container-low/50 transition-colors group">
                <td class="px-6 py-5 align-top">
                  <div class="text-sm font-bold text-on-surface font-body">{{ formatParts(String(r.created_at)).date }}</div>
                  <div class="text-xs text-on-surface-variant mt-0.5 font-body">{{ formatParts(String(r.created_at)).time }}</div>
                </td>
                <td class="px-6 py-5 align-top">
                  <div class="flex items-center">
                    <div
                      v-if="isSystemActor(r.actor_email)"
                      class="w-7 h-7 rounded-full bg-tertiary-fixed text-[10px] flex items-center justify-center text-on-tertiary-fixed mr-3"
                    >
                      <span class="material-symbols-outlined text-xs" style="font-variation-settings: 'FILL' 1">auto_awesome</span>
                    </div>
                    <div
                      v-else
                      class="w-7 h-7 rounded-full bg-primary-container text-[10px] flex items-center justify-center text-primary-fixed mr-3 font-bold"
                    >
                      {{ initialsFromEmail(r.actor_email) }}
                    </div>
                    <div class="text-sm font-semibold text-on-surface font-body">{{ displayName(r.actor_email) }}</div>
                  </div>
                </td>
                <td class="px-6 py-5 align-top">
                  <span
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium font-body"
                    :class="actionPresentation(r.action).cls"
                  >
                    <span class="material-symbols-outlined text-sm mr-1">{{ actionPresentation(r.action).icon }}</span>
                    {{ actionPresentation(r.action).label }}
                  </span>
                </td>
                <td class="px-6 py-5 align-top">
                  <div class="text-xs font-mono bg-surface-container-low px-2 py-1 rounded w-fit text-on-surface-variant max-w-[200px] truncate">
                    {{ r.entity_type ?? "—" }}<template v-if="r.entity_id != null"> #{{ r.entity_id }}</template>
                  </div>
                </td>
                <td class="px-6 py-5 align-top">
                  <p class="text-xs text-on-surface-variant leading-relaxed max-w-xs font-body">
                    {{ r.detail || "—" }}
                  </p>
                </td>
                <td class="px-6 py-5 align-top text-right">
                  <span class="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-tight font-label" :class="rowState(r).cls">{{
                    rowState(r).label
                  }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="px-6 py-4 bg-surface-container-low flex flex-col sm:flex-row justify-between items-center gap-3 border-t border-outline-variant/10">
          <div class="text-xs text-on-surface-variant font-medium font-body">
            Exibindo
            <span class="text-on-surface">{{
              filtered.length ? (page - 1) * pageSize + 1 : 0
            }}</span>
            –
            <span class="text-on-surface">{{ Math.min(page * pageSize, filtered.length) }}</span>
            de
            <span class="text-on-surface">{{ filtered.length }}</span>
            eventos
          </div>
          <div class="flex space-x-2">
            <button
              type="button"
              class="w-8 h-8 flex items-center justify-center rounded border border-outline-variant/30 hover:bg-surface-container text-on-surface-variant transition-colors disabled:opacity-30"
              :disabled="page <= 1"
              @click="goPage(page - 1)"
            >
              <span class="material-symbols-outlined text-lg">chevron_left</span>
            </button>
            <button
              type="button"
              class="w-8 h-8 flex items-center justify-center rounded bg-primary text-on-primary font-bold text-xs"
              @click="goPage(1)"
            >
              {{ page }}
            </button>
            <button
              type="button"
              class="w-8 h-8 flex items-center justify-center rounded border border-outline-variant/30 hover:bg-surface-container text-on-surface-variant transition-colors disabled:opacity-30"
              :disabled="page >= pageCount"
              @click="goPage(page + 1)"
            >
              <span class="material-symbols-outlined text-lg">chevron_right</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Insight + conformidade -->
      <div class="grid grid-cols-12 gap-6">
        <div class="col-span-12 md:col-span-8 p-8 bg-surface-container-lowest border-l-4 border-tertiary-fixed rounded-r-xl shadow-sm border border-outline-variant/5">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h3 class="text-lg font-headline font-bold text-on-surface mb-2">Insight de integridade</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed mb-6 font-body">
                O ledger regista
                <span class="text-on-tertiary-container font-semibold">{{ filtered.length }} evento(s)</span>
                com os filtros atuais. Consulte ações sensíveis (exclusões) no estado “Aguardando aprovação” quando aplicável.
              </p>
              <div class="flex flex-wrap gap-8">
                <div class="flex flex-col">
                  <span class="text-[10px] font-bold uppercase tracking-widest text-outline font-label">Volume</span>
                  <span class="text-xl font-headline font-bold">{{ rows.length }}</span>
                </div>
                <div class="flex flex-col">
                  <span class="text-[10px] font-bold uppercase tracking-widest text-outline font-label">Tipos de entidade</span>
                  <span class="text-xl font-headline font-bold text-on-tertiary-container">{{ uniqueModules.length }}</span>
                </div>
              </div>
            </div>
            <div class="hidden lg:flex w-16 h-16 rounded-full bg-tertiary-fixed/15 items-center justify-center shrink-0">
              <span class="material-symbols-outlined text-3xl text-tertiary-fixed/40">verified_user</span>
            </div>
          </div>
        </div>
        <div class="col-span-12 md:col-span-4 p-8 bg-primary-container text-primary-fixed rounded-xl flex flex-col justify-between relative overflow-hidden">
          <div class="relative z-10">
            <h3 class="text-sm font-bold uppercase tracking-widest mb-4 font-label text-on-primary-container">Status de conformidade</h3>
            <div class="space-y-4 text-on-primary-container">
              <div class="flex justify-between items-center text-xs font-body">
                <span>Cobertura de auditoria</span>
                <span class="font-bold">{{ rows.length ? "100%" : "—" }}</span>
              </div>
              <div class="w-full bg-slate-800/50 h-1 rounded-full overflow-hidden">
                <div class="bg-tertiary-fixed h-full transition-all" :style="{ width: rows.length ? '100%' : '0%' }" />
              </div>
              <div class="flex justify-between items-center text-xs font-body">
                <span>Retenção local</span>
                <span class="font-bold text-tertiary-fixed">Ativo</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            class="relative z-10 mt-8 py-2 w-full bg-primary-fixed text-on-primary-fixed text-xs font-bold rounded-md hover:opacity-90 transition-opacity font-label"
            @click="load"
          >
            Atualizar trilha
          </button>
          <div class="absolute -bottom-16 -right-16 w-48 h-48 bg-tertiary-fixed/10 rounded-full blur-2xl pointer-events-none" />
        </div>
      </div>
    </template>
  </div>
</template>
