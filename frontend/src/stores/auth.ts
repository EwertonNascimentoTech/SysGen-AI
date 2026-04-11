import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api, getToken, setToken } from "@/api/client";

export type Me = {
  id: number;
  email: string;
  full_name: string;
  roles: string[];
  /** Identidade OAuth GitHub ligada (token para API). */
  has_github?: boolean;
};

export const useAuthStore = defineStore("auth", () => {
  const me = ref<Me | null>(null);
  const loaded = ref(false);
  /** localStorage não é reativo — este ref mantém o router e o layout alinhados ao token */
  const hasSession = ref(!!getToken());

  const isAuthenticated = computed(() => hasSession.value);

  function setAuthToken(token: string | null) {
    setToken(token);
    hasSession.value = !!token;
    if (!token) me.value = null;
  }

  async function login(email: string, password: string) {
    const tok = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(tok.access_token);
    await fetchMe();
  }

  async function fetchMe() {
    if (!getToken()) {
      setAuthToken(null);
      loaded.value = true;
      return;
    }
    try {
      me.value = await api<Me>("/auth/me");
    } catch {
      setAuthToken(null);
    } finally {
      loaded.value = true;
    }
  }

  function logout() {
    setAuthToken(null);
  }

  function hasRole(...codes: string[]) {
    const r = new Set(me.value?.roles ?? []);
    return codes.some((c) => r.has(c));
  }

  return { me, loaded, isAuthenticated, login, fetchMe, logout, hasRole, setAuthToken };
});
