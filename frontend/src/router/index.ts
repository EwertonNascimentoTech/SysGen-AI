import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/auth/callback", component: () => import("@/views/AuthCallbackView.vue") },
    { path: "/login", component: () => import("@/views/LoginView.vue") },
    {
      path: "/",
      component: () => import("@/components/AppLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", name: "dashboard", component: () => import("@/views/DashboardView.vue") },
        { path: "projetos", name: "projetos", component: () => import("@/views/ProjectsView.vue") },
        { path: "projetos/novo", name: "projeto-novo", component: () => import("@/views/ProjectNewView.vue") },
        { path: "projetos/:id", name: "projeto-detalhe", component: () => import("@/views/ProjectDetailView.vue") },
        { path: "kanban", name: "kanban", component: () => import("@/views/KanbanView.vue") },
        { path: "templates", name: "templates", component: () => import("@/views/TemplatesView.vue") },
        {
          path: "regras-avanco",
          name: "regras-avanco",
          component: () => import("@/views/AdvanceRulesView.vue"),
        },
        {
          path: "templates/:templateId/fluxo",
          name: "templates-fluxo",
          component: () => import("@/views/TemplatesView.vue"),
        },
        { path: "wiki", name: "wiki", component: () => import("@/views/WikiProjectsListView.vue") },
        { path: "detalhes-wiki", redirect: { name: "wiki" } },
        {
          path: "detalhes-wiki/:projectId",
          name: "detalhes-wiki",
          component: () => import("@/views/GitHubWikiView.vue"),
        },
        { path: "github-wiki", redirect: { name: "wiki" } },
        { path: "cursor-hub", name: "cursor", component: () => import("@/views/CursorHubView.vue") },
        { path: "usuarios", name: "usuarios", component: () => import("@/views/UsersView.vue") },
        { path: "auditoria", name: "auditoria", component: () => import("@/views/AuditView.vue") },
        { path: "configuracoes", name: "config", component: () => import("@/views/SettingsView.vue") },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.loaded) await auth.fetchMe();
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (to.path === "/login" && auth.isAuthenticated) return { path: "/" };
});

export default router;
