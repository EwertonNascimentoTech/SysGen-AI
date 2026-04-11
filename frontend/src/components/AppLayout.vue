<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

function onLogout() {
  auth.logout();
  void router.replace("/login");
}

const allNav = [
  { to: "/", label: "Painel", icon: "dashboard", match: /^\/$/ },
  { to: "/projetos", label: "Projetos", icon: "folder_managed", match: /^\/projetos/ },
  { to: "/kanban", label: "Kanban", icon: "view_kanban", match: /^\/kanban/ },
  { to: "/wiki", label: "Wiki", icon: "menu_book", match: /^\/(wiki|detalhes-wiki)/ },
  { to: "/cursor-hub", label: "Cursor Hub", icon: "integration_instructions", match: /^\/cursor-hub/ },
  { to: "/configuracoes", label: "Configurações", icon: "settings", match: /^\/configuracoes/ },
];

function isActive(m: RegExp) {
  return m.test(route.path);
}

const canAdmin = computed(() => auth.hasRole("admin"));

const nav = computed(() => allNav.filter((item) => !item.adminOnly || canAdmin.value));

/** Rótulo do cabeçalho alinhado ao protótipo (ex.: Admin) */
const headerRoleLabel = computed(() => {
  if (!auth.me) return "";
  if (auth.hasRole("admin")) return "Admin";
  if (auth.hasRole("coordenador")) return "Coordenador";
  if (auth.hasRole("po")) return "PO";
  const r = auth.me.roles[0];
  return r ? r.charAt(0).toUpperCase() + r.slice(1) : "Utilizador";
});
</script>

<template>
  <div class="min-h-screen text-on-surface">
    <aside
      class="bg-primary-container h-screen w-64 fixed left-0 top-0 flex flex-col py-6 font-headline tracking-tight z-50"
    >
      <!-- Marca -->
      <div class="px-6 mb-10">
        <div class="min-w-0 leading-tight">
          <div class="text-[15px] font-bold text-white tracking-tight font-headline">The Sovereign</div>
          <div class="text-[15px] font-bold text-white tracking-tight font-headline">Ledger</div>
          <p class="text-[10px] uppercase tracking-[0.12em] text-on-primary-container mt-1.5 font-label">
            Governança Projetos IA
          </p>
        </div>
      </div>
      <nav class="flex-1 px-4 space-y-1">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 px-3 py-2 rounded transition-colors"
          :class="
            isActive(item.match)
              ? 'text-primary-fixed font-semibold border-r-2 border-primary-fixed bg-[#1C253B]/80'
              : 'text-outline-variant hover:bg-[#1C253B]/60 text-[#C6C6CD]'
          "
        >
          <span class="material-symbols-outlined">{{ item.icon }}</span>
          <span class="text-sm">{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="px-4 pt-4 mt-auto border-t border-white/10 space-y-1">
        <div
          class="flex items-center gap-3 px-3 py-2 rounded text-sm text-[#C6C6CD] pointer-events-none select-none"
          :title="auth.me?.email ?? undefined"
        >
          <span class="material-symbols-outlined shrink-0 text-[22px] leading-none">person</span>
          <span class="truncate font-body">{{ auth.me?.full_name }}</span>
        </div>
        <button
          type="button"
          class="w-full flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors text-[#C6C6CD] hover:bg-[#1C253B]/60 font-body text-left"
          @click="onLogout"
        >
          <span class="material-symbols-outlined shrink-0 text-[22px] leading-none">logout</span>
          Sair
        </button>
      </div>
    </aside>
    <main class="ml-64 min-h-screen min-w-0 w-[calc(100%-16rem)] max-w-none bg-surface flex flex-col">
      <header
        class="flex justify-between items-center px-8 h-16 sticky top-0 z-40 bg-white border-b border-outline-variant/10"
      >
        <div class="flex items-center flex-1 min-w-0 pr-6">
          <div class="relative w-full max-w-xl">
            <span
              class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px] pointer-events-none"
              >search</span
            >
            <input
              type="search"
              class="w-full bg-surface-container-low border-none rounded-full pl-11 pr-5 py-2.5 text-sm text-on-surface focus:ring-1 focus:ring-primary/30 focus:bg-surface-container-lowest transition-all outline-none font-body placeholder:text-on-surface-variant/70"
              placeholder="Buscar projetos, templates ou artefatos..."
              disabled
              aria-label="Busca global (em breve)"
            />
          </div>
        </div>
        <div class="flex items-center gap-5 shrink-0">
          <span class="text-sm font-medium text-on-surface font-body hidden sm:inline">{{ headerRoleLabel }}</span>
          <button
            type="button"
            class="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low rounded-full p-1.5 transition-colors"
            aria-label="Notificações"
            disabled
          >
            <span class="material-symbols-outlined text-[22px] leading-none">notifications</span>
          </button>
        </div>
      </header>
      <div class="w-full max-w-none min-w-0 min-h-0 flex-1 flex flex-col px-3 py-5 sm:px-4 md:px-5 md:py-6">
        <RouterView class="flex flex-1 flex-col min-h-0 min-w-0" />
      </div>
    </main>
  </div>
</template>
