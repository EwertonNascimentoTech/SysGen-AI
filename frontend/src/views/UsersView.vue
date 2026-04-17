<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type UserRow = {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  github_login?: string | null;
};

/** Perfis alinhados ao seed da API (`roles` na base). */
const ROLE_OPTIONS = [
  { code: "admin", label: "Administrador" },
  { code: "coordenador", label: "Coordenador" },
  { code: "po", label: "Product Owner" },
  { code: "dev", label: "Desenvolvedor" },
  { code: "visualizador", label: "Visualizador" },
] as const;

const auth = useAuthStore();
const router = useRouter();
const rows = ref<UserRow[]>([]);
const err = ref("");
const msg = ref("");
const showBanner = ref(true);
const showForm = ref(false);
const page = ref(1);
const pageSize = 8;

const form = ref({ email: "", full_name: "", password: "", github_login: "", role_codes: ["dev"] as string[] });

const showEdit = ref(false);
const savingEdit = ref(false);
const editId = ref<number | null>(null);
const editForm = ref({
  email: "",
  full_name: "",
  password: "",
  github_login: "",
  role_codes: [] as string[],
  is_active: true,
});

onMounted(async () => {
  if (!auth.hasRole("admin")) return;
  try {
    rows.value = await api<UserRow[]>("/users");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
});

const activeCount = computed(() => rows.value.filter((u) => u.is_active).length);
const totalCount = computed(() => rows.value.length);

const pageCount = computed(() => Math.max(1, Math.ceil(rows.value.length / pageSize)));

watch(pageCount, (n) => {
  if (page.value > n) page.value = n;
});

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize;
  return rows.value.slice(start, start + pageSize);
});

const securityPulse = computed(() => {
  if (!totalCount.value) return 0;
  return Math.round((activeCount.value / totalCount.value) * 100);
});

function initials(name: string) {
  const p = name.trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return (p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function roleBadges(roles: string[]) {
  const out: { icon: string; label: string; cls: string }[] = [];
  const r = new Set(roles.map((x) => x.toLowerCase()));
  if (r.has("admin")) out.push({ icon: "shield_person", label: "Admin", cls: "bg-primary-container text-on-primary-container" });
  if (r.has("coordenador")) out.push({ icon: "account_tree", label: "Coord.", cls: "bg-tertiary-container text-on-tertiary-container" });
  if (r.has("po")) out.push({ icon: "account_tree", label: "PO", cls: "bg-secondary-container text-on-secondary-container" });
  if (r.has("dev")) out.push({ icon: "code", label: "Dev", cls: "bg-surface-container-highest text-on-surface-variant" });
  if (r.has("visualizador")) out.push({ icon: "visibility", label: "Visualiz.", cls: "bg-surface-container-highest text-on-surface-variant" });
  if (!out.length) out.push({ icon: "person", label: "Perfil", cls: "bg-surface-container-highest text-on-surface-variant" });
  return out.slice(0, 4);
}

function openEdit(u: UserRow) {
  showForm.value = false;
  err.value = "";
  msg.value = "";
  editId.value = u.id;
  editForm.value = {
    email: u.email,
    full_name: u.full_name,
    password: "",
    github_login: u.github_login ?? "",
    role_codes: [...u.roles],
    is_active: u.is_active,
  };
  showEdit.value = true;
}

function cancelEdit() {
  showEdit.value = false;
  editId.value = null;
  editForm.value = { email: "", full_name: "", password: "", github_login: "", role_codes: [], is_active: true };
}

async function saveEdit() {
  if (editId.value == null) return;
  err.value = "";
  msg.value = "";
  savingEdit.value = true;
  try {
    const role_codes = [...new Set(editForm.value.role_codes.map((c) => c.trim()).filter(Boolean))];
    if (!role_codes.length) {
      err.value = "Indique pelo menos um perfil.";
      return;
    }
    const gl = editForm.value.github_login.trim();
    const payload: Record<string, unknown> = {
      email: editForm.value.email.trim(),
      full_name: editForm.value.full_name.trim(),
      role_codes,
      is_active: editForm.value.is_active,
      github_login: gl.length ? gl : null,
    };
    const pw = editForm.value.password.trim();
    if (pw.length) {
      if (pw.length < 6) {
        err.value = "Nova senha deve ter pelo menos 6 caracteres.";
        return;
      }
      payload.password = pw;
    }
    await api(`/users/${editId.value}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    rows.value = await api<UserRow[]>("/users");
    msg.value = "Usuário atualizado.";
    cancelEdit();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  } finally {
    savingEdit.value = false;
  }
}

async function create() {
  err.value = "";
  msg.value = "";
  try {
    const role_codes = [...new Set(form.value.role_codes.map((c) => c.trim()).filter(Boolean))];
    if (!role_codes.length) {
      err.value = "Selecione pelo menos um nível de acesso.";
      return;
    }
    const body: Record<string, unknown> = {
      email: form.value.email,
      full_name: form.value.full_name,
      password: form.value.password,
      role_codes,
    };
    const ngl = form.value.github_login.trim();
    if (ngl.length) body.github_login = ngl;
    await api("/users", {
      method: "POST",
      body: JSON.stringify(body),
    });
    rows.value = await api<UserRow[]>("/users");
    form.value = { email: "", full_name: "", password: "", github_login: "", role_codes: ["dev"] };
    showForm.value = false;
    page.value = 1;
    msg.value = "Usuário criado.";
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro";
  }
}

function goPage(n: number) {
  page.value = Math.min(Math.max(1, n), pageCount.value);
}

function leaveUsersToPrevious() {
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
        @click="leaveUsersToPrevious"
      >
        <span class="material-symbols-outlined text-xl leading-none" aria-hidden="true">arrow_back</span>
        Voltar
      </button>
    </div>
    <!-- Não administrador: shell alinhado ao protótipo com aviso -->
    <template v-if="!auth.hasRole('admin')">
      <div>
        <span class="text-[10px] font-bold tracking-[0.1em] text-on-surface-variant uppercase font-label">Governança corporativa</span>
        <h2 class="text-3xl font-extrabold font-headline tracking-tight text-on-surface mt-1">Hub de governança</h2>
        <p class="text-on-surface-variant mt-2 max-w-2xl text-sm font-body leading-relaxed">
          Gestão centralizada de identidades e permissões. Apenas administradores visualizam a lista completa de usuários.
        </p>
      </div>
      <div class="bg-surface-container-low border border-outline-variant/10 rounded-xl p-8 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant mb-2">lock</span>
        <p class="text-on-surface font-medium font-body">Acesso restrito a administradores.</p>
        <p class="text-sm text-on-surface-variant mt-2 font-body">Entre com uma conta de administrador para gerir usuários.</p>
      </div>
    </template>

    <template v-else>
      <!-- Faixa de aviso (protótipo gest_o_de_usu_rios_pt_br) -->
      <div
        v-if="showBanner"
        class="bg-tertiary-container/15 border border-tertiary-container/30 rounded-lg p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
      >
        <div class="flex gap-3">
          <span class="material-symbols-outlined text-on-tertiary-container shrink-0">gavel</span>
          <p class="text-sm text-on-surface font-medium font-body">
            <span class="font-bold text-on-tertiary-container">Apenas administradores</span>
            podem criar e editar usuários e perfis (RF-18). Alterações são auditáveis.
          </p>
        </div>
        <button
          type="button"
          class="text-on-surface-variant hover:text-on-surface p-1 self-end sm:self-auto"
          aria-label="Fechar aviso"
          @click="showBanner = false"
        >
          <span class="material-symbols-outlined text-lg">close</span>
        </button>
      </div>

      <div class="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
        <div>
          <span class="text-[10px] font-bold tracking-[0.1em] text-on-surface-variant uppercase font-label">Governança corporativa</span>
          <h2 class="text-3xl font-extrabold font-headline tracking-tight text-on-surface mt-1">Hub de governança</h2>
          <p class="text-on-surface-variant mt-2 max-w-2xl text-sm font-body leading-relaxed">
            Gestão centralizada de identidades, perfis de acesso e políticas de segurança para a plataforma.
          </p>
        </div>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="flex items-center px-4 py-2 bg-surface-container-high text-on-surface font-semibold rounded-md hover:bg-surface-container-highest transition-colors text-sm font-body opacity-60 cursor-not-allowed"
            title="Em breve"
            disabled
          >
            <span class="material-symbols-outlined mr-2 text-lg">admin_panel_settings</span>
            Permissões
          </button>
          <button
            type="button"
            class="flex items-center px-4 py-2 bg-primary text-on-primary font-semibold rounded-md hover:opacity-90 transition-opacity text-sm font-body"
            @click="
              showForm = !showForm;
              if (showForm) cancelEdit();
            "
          >
            <span class="material-symbols-outlined mr-2 text-lg">person_add</span>
            Novo usuário
          </button>
        </div>
      </div>

      <!-- Editar usuário -->
      <div v-if="showEdit" class="bg-surface-container-low rounded-xl p-6 border border-outline-variant/10 max-w-3xl space-y-3">
        <h3 class="font-headline font-bold text-sm">Editar usuário</h3>
        <form class="grid md:grid-cols-2 gap-3" @submit.prevent="saveEdit">
          <input
            v-model="editForm.email"
            type="email"
            required
            class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
            placeholder="E-mail"
          />
          <input
            v-model="editForm.full_name"
            required
            class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
            placeholder="Nome completo"
          />
          <input
            v-model="editForm.password"
            type="password"
            class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
            placeholder="Nova senha (deixe vazio para não alterar)"
            autocomplete="new-password"
          />
          <div class="flex flex-col gap-1">
            <label class="text-xs text-on-surface-variant font-body" for="edit-github-login">Login GitHub (opcional)</label>
            <input
              id="edit-github-login"
              v-model="editForm.github_login"
              type="text"
              autocomplete="off"
              class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
              placeholder="ex.: octocat"
            />
            <span class="text-[11px] text-on-surface-variant leading-snug"
              >Se o e-mail do GitHub não for o mesmo da plataforma, indique o nome de utilizador exactamente como no perfil (github.com/nome).</span
            >
          </div>
          <label class="flex flex-col gap-1 min-h-0">
            <span class="text-xs text-on-surface-variant font-body">Nível de acesso</span>
            <select
              v-model="editForm.role_codes"
              multiple
              required
              :size="ROLE_OPTIONS.length"
              class="w-full min-h-[8.5rem] rounded-lg bg-surface-container-lowest px-2 py-1.5 text-sm outline-none border border-outline-variant/10 font-body"
            >
              <option v-for="opt in ROLE_OPTIONS" :key="opt.code" :value="opt.code">{{ opt.label }}</option>
            </select>
            <span class="text-[11px] text-on-surface-variant leading-snug">Selecione um ou mais perfis (Ctrl ou ⌘ + clique).</span>
          </label>
          <label class="md:col-span-2 flex items-center gap-2 text-sm text-on-surface font-body cursor-pointer">
            <input v-model="editForm.is_active" type="checkbox" class="rounded border-outline-variant" />
            Conta ativa
          </label>
          <div class="md:col-span-2 flex gap-2">
            <button
              type="submit"
              class="px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold font-body disabled:opacity-50"
              :disabled="savingEdit"
            >
              {{ savingEdit ? "A guardar…" : "Guardar alterações" }}
            </button>
            <button
              type="button"
              class="px-4 py-2 text-sm text-on-surface-variant font-body hover:text-on-surface"
              :disabled="savingEdit"
              @click="cancelEdit"
            >
              Cancelar
            </button>
          </div>
        </form>
      </div>

      <!-- Formulário expansível -->
      <div v-if="showForm" class="bg-surface-container-low rounded-xl p-6 border border-outline-variant/10 max-w-3xl space-y-3">
        <h3 class="font-headline font-bold text-sm">Novo usuário</h3>
        <form class="grid md:grid-cols-2 gap-3" @submit.prevent="create">
          <input
            v-model="form.email"
            type="email"
            required
            class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
            placeholder="E-mail"
          />
          <input
            v-model="form.full_name"
            required
            class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
            placeholder="Nome completo"
          />
          <input
            v-model="form.password"
            type="password"
            required
            class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
            placeholder="Senha"
          />
          <div class="flex flex-col gap-1">
            <label class="text-xs text-on-surface-variant font-body" for="new-github-login">Login GitHub (opcional)</label>
            <input
              id="new-github-login"
              v-model="form.github_login"
              type="text"
              autocomplete="off"
              class="rounded-lg bg-surface-container-lowest px-3 py-2 text-sm outline-none border border-outline-variant/10 font-body"
              placeholder="ex.: octocat"
            />
          </div>
          <label class="flex flex-col gap-1 min-h-0">
            <span class="text-xs text-on-surface-variant font-body">Nível de acesso</span>
            <select
              v-model="form.role_codes"
              multiple
              required
              :size="ROLE_OPTIONS.length"
              class="w-full min-h-[8.5rem] rounded-lg bg-surface-container-lowest px-2 py-1.5 text-sm outline-none border border-outline-variant/10 font-body"
            >
              <option v-for="opt in ROLE_OPTIONS" :key="opt.code" :value="opt.code">{{ opt.label }}</option>
            </select>
            <span class="text-[11px] text-on-surface-variant leading-snug">Selecione um ou mais perfis (Ctrl ou ⌘ + clique).</span>
          </label>
          <div class="md:col-span-2 flex gap-2">
            <button type="submit" class="px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold font-body">Criar</button>
            <button type="button" class="px-4 py-2 text-sm text-on-surface-variant font-body hover:text-on-surface" @click="showForm = false">
              Cancelar
            </button>
          </div>
        </form>
      </div>

      <p v-if="msg" class="text-sm text-tertiary-fixed font-body">{{ msg }}</p>
      <p v-if="err" class="text-error text-sm font-body">{{ err }}</p>

      <!-- Tabela -->
      <div class="bg-surface-container-low rounded-xl border border-outline-variant/10 overflow-hidden">
        <div class="p-4 border-b border-outline-variant/10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div class="flex flex-wrap gap-2">
            <span class="px-3 py-1 rounded-full bg-surface-container-highest text-[10px] font-bold uppercase tracking-wide text-on-surface font-label">
              Usuários ativos: {{ activeCount }}
            </span>
            <span class="px-3 py-1 rounded-full bg-surface-container-highest text-[10px] font-bold uppercase tracking-wide text-on-surface-variant font-label">
              Autenticação: JWT + credenciais locais
            </span>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse min-w-[720px]">
            <thead>
              <tr class="bg-surface-container-high/50 text-[10px] uppercase tracking-widest text-on-surface-variant font-label">
                <th class="px-6 py-4 font-bold">Identidade</th>
                <th class="px-6 py-4 font-bold">Perfil operacional</th>
                <th class="px-6 py-4 font-bold">Tipo de autenticação</th>
                <th class="px-6 py-4 font-bold">Status</th>
                <th class="px-6 py-4 font-bold text-right">Ações</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-variant/10">
              <tr v-for="u in pagedRows" :key="u.id" class="hover:bg-surface-container-high/30 transition-colors group">
                <td class="px-6 py-4">
                  <div class="flex items-center gap-3">
                    <div
                      class="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-xs font-headline"
                    >
                      {{ initials(u.full_name || u.email) }}
                    </div>
                    <div>
                      <p class="text-sm font-bold text-on-surface font-headline">{{ u.full_name || "—" }}</p>
                      <p class="text-xs text-on-surface-variant font-body">{{ u.email }}</p>
                      <p v-if="u.github_login" class="text-[11px] text-on-surface-variant/80 font-body font-mono">
                        GitHub: @{{ u.github_login }}
                      </p>
                    </div>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <div class="flex flex-wrap gap-1">
                    <span
                      v-for="(b, i) in roleBadges(u.roles)"
                      :key="i"
                      class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase font-label"
                      :class="b.cls"
                    >
                      <span class="material-symbols-outlined text-[14px]">{{ b.icon }}</span>
                      {{ b.label }}
                    </span>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <span class="text-xs font-medium text-on-surface-variant font-body">Local / JWT</span>
                </td>
                <td class="px-6 py-4">
                  <span
                    class="px-2 py-0.5 rounded text-[10px] font-bold uppercase font-label"
                    :class="u.is_active ? 'bg-tertiary-container/20 text-tertiary-fixed' : 'bg-error-container/20 text-error'"
                  >
                    {{ u.is_active ? "Ativo" : "Inativo" }}
                  </span>
                </td>
                <td class="px-6 py-4 text-right">
                  <button
                    type="button"
                    class="text-on-surface-variant hover:text-primary p-1"
                    title="Editar usuário"
                    @click="openEdit(u)"
                  >
                    <span class="material-symbols-outlined text-xl">edit_square</span>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="p-4 bg-surface-container-high/20 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs text-on-surface-variant font-body">
          <p>
            Mostrando {{ pagedRows.length ? (page - 1) * pageSize + 1 : 0 }}–{{ Math.min(page * pageSize, totalCount) }} de {{ totalCount }}
          </p>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="p-1 rounded hover:bg-surface-container-high disabled:opacity-40"
              :disabled="page <= 1"
              @click="goPage(page - 1)"
            >
              <span class="material-symbols-outlined text-sm">chevron_left</span>
            </button>
            <span class="font-mono">{{ page }} / {{ pageCount }}</span>
            <button
              type="button"
              class="p-1 rounded hover:bg-surface-container-high disabled:opacity-40"
              :disabled="page >= pageCount"
              @click="goPage(page + 1)"
            >
              <span class="material-symbols-outlined text-sm">chevron_right</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Rodapé insight + pulso -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div class="lg:col-span-8 bg-surface-container-low p-6 rounded-xl border border-outline-variant/5 relative overflow-hidden">
          <div class="relative z-10">
            <div class="flex items-center gap-2 mb-2">
              <span class="material-symbols-outlined text-primary text-sm">auto_awesome</span>
              <span class="text-[10px] font-bold tracking-widest text-primary uppercase font-label">Insight de governança</span>
            </div>
            <h4 class="font-headline font-bold text-on-surface mb-2">Distribuição de perfis</h4>
            <p class="text-sm text-on-surface-variant font-body max-w-xl leading-relaxed">
              Mantenha o mínimo de contas com perfil administrativo. Utilize <strong class="text-on-surface">PO</strong> e
              <strong class="text-on-surface">Dev</strong> para o dia a dia dos projetos.
            </p>
          </div>
          <span class="material-symbols-outlined absolute -right-4 -bottom-4 text-[120px] text-primary/5 pointer-events-none">hub</span>
        </div>
        <div class="lg:col-span-4 bg-surface-container-low p-6 rounded-xl border border-outline-variant/5 flex flex-col justify-center">
          <h4 class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest mb-4 font-label">Pulso de segurança</h4>
          <div class="flex items-end justify-between mb-2">
            <span class="text-2xl font-bold text-on-surface font-headline">{{ securityPulse }}%</span>
            <span class="text-[10px] text-tertiary-fixed font-bold uppercase font-label">Contas ativas / total</span>
          </div>
          <div class="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden">
            <div class="h-full bg-primary rounded-full transition-all duration-500" :style="{ width: securityPulse + '%' }" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
