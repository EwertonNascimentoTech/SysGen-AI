<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const msg = ref("Concluindo login…");

function rawQueryParam(v: string | string[] | undefined): string | undefined {
  if (v == null) return undefined;
  return typeof v === "string" ? v : v[0];
}

/** Evita open redirect: só caminhos relativos à app. */
function isSafeInternalNext(p: string): boolean {
  if (!p || p.length > 768) return false;
  if (!p.startsWith("/") || p.startsWith("//")) return false;
  if (p.includes("://")) return false;
  if (p.includes("\n") || p.includes("\r")) return false;
  return true;
}

onMounted(async () => {
  const err = rawQueryParam(route.query.error as string | string[] | undefined);
  if (err) {
    msg.value =
      err === "no_user"
        ? "E-mail GitHub não cadastrado. Peça ao administrador para criar seu usuário com o mesmo e-mail."
        : `Erro OAuth: ${err}`;
    return;
  }
  const token = rawQueryParam(route.query.token as string | string[] | undefined);
  if (!token) {
    msg.value = "Token ausente na resposta.";
    return;
  }
  const nextRaw = rawQueryParam(route.query.next as string | string[] | undefined);
  auth.setAuthToken(token);
  await auth.fetchMe();
  const dest = nextRaw && isSafeInternalNext(nextRaw) ? nextRaw : "/";
  await router.replace(dest);
});
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-surface font-body text-on-surface">
    <p class="text-sm">{{ msg }}</p>
  </div>
</template>
