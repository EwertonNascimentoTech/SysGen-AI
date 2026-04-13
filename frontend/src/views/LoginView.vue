<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const email = ref("admin@empresa.com.br");
const password = ref("admin123");
const error = ref("");
const loading = ref(false);
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

async function submit() {
  error.value = "";
  loading.value = true;
  try {
    await auth.login(email.value, password.value);
    const r = (route.query.redirect as string) || "/";
    await router.replace(r);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Falha no login";
  } finally {
    loading.value = false;
  }
}

function githubLogin() {
  window.location.assign("/api/auth/github/authorize?next=%2F");
}
</script>

<template>
  <div class="bg-surface text-on-surface min-h-screen flex items-center justify-center p-4">
    <div
      class="w-full max-w-6xl grid grid-cols-1 md:grid-cols-12 gap-0 overflow-hidden rounded-xl bg-surface-container-lowest shadow-2xl"
      style="box-shadow: 0 40px 60px -20px rgba(25, 28, 30, 0.08)"
    >
      <div class="hidden md:flex md:col-span-7 tech-gradient p-12 flex-col justify-between relative overflow-hidden">
        <div class="absolute inset-0 opacity-20 pointer-events-none bg-gradient-to-br from-white/10 to-transparent" />
        <div class="relative z-10">
          <div class="mb-12">
            <span class="text-white text-xl font-headline font-extrabold tracking-tight">SysGen AI</span>
          </div>
          <h1 class="text-white text-4xl md:text-5xl font-headline font-extrabold tracking-tight leading-tight max-w-lg mb-6">
            Inteligência Corporativa
            <br />
            <span class="text-tertiary-fixed opacity-90">Governança por Design</span>
          </h1>
          <p class="text-primary-fixed-dim font-body text-lg max-w-md leading-relaxed opacity-90">
            Gestão, rastreabilidade e documentação de projetos com IA — Kanban, GitHub, Wiki e Cursor Hub.
          </p>
        </div>
        <div class="relative z-10 flex gap-8 text-sm font-body text-white/90">
          <div>
            <p class="text-[0.65rem] font-label font-bold uppercase tracking-[0.1em] text-primary-fixed-dim mb-1">MVP</p>
            <p class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-tertiary-fixed" /> PRD alinhado
            </p>
          </div>
        </div>
      </div>
      <div class="md:col-span-5 p-8 md:p-14 flex flex-col justify-center bg-surface-container-lowest">
        <div class="mb-8 text-center md:text-left">
          <h2 class="text-3xl font-headline font-bold text-on-surface mb-2 tracking-tight">Entrar</h2>
          <p class="text-on-surface-variant font-body text-sm">
            Console de governança — login local ou ligação da conta via OAuth GitHub.
          </p>
        </div>
        <form class="space-y-5" @submit.prevent="submit">
          <div class="space-y-1.5">
            <label class="text-[0.65rem] font-label font-bold uppercase tracking-[0.1em] text-on-surface-variant ml-1" for="email"
              >E-mail</label
            >
            <input
              id="email"
              v-model="email"
              type="email"
              required
              class="block w-full px-4 py-3.5 bg-surface-container-low border-0 rounded-lg text-on-surface text-sm font-body placeholder:text-outline/60 focus:ring-2 focus:ring-primary-container focus:bg-white transition-all outline-none"
 placeholder="nome@empresa.com.br"
            />
          </div>
          <div class="space-y-1.5">
            <label class="text-[0.65rem] font-label font-bold uppercase tracking-[0.1em] text-on-surface-variant ml-1" for="pw"
              >Senha</label
            >
            <input
              id="pw"
              v-model="password"
              type="password"
              required
              class="block w-full px-4 py-3.5 bg-surface-container-low border-0 rounded-lg text-on-surface text-sm focus:ring-2 focus:ring-primary-container focus:bg-white transition-all outline-none"
            />
          </div>
          <p v-if="error" class="text-error text-sm font-body">{{ error }}</p>
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-3.5 rounded-md bg-primary text-on-primary font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {{ loading ? "Entrando…" : "Acessar plataforma" }}
          </button>
          <button
            type="button"
            class="w-full py-3 rounded-md bg-surface-container-high text-on-surface font-semibold text-sm hover:bg-surface-variant transition-colors"
            @click="githubLogin"
          >
            Entrar com GitHub
          </button>
        </form>
        <p class="mt-6 text-xs text-on-surface-variant font-body text-center md:text-left">
          Seed: <code class="bg-surface-container-low px-1 rounded">admin@empresa.com.br</code> /
          <code class="bg-surface-container-low px-1 rounded">admin123</code>
        </p>
      </div>
    </div>
  </div>
</template>
