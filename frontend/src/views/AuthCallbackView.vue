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
    if (err === "no_user") {
      msg.value =
        "Nenhum utilizador foi encontrado com o mesmo e-mail verificado no GitHub. " +
        "Peça ao administrador para criar a sua conta com esse e-mail ou para preencher o campo «Login GitHub» no seu utilizador (Hub de governança) com o mesmo nome de utilizador do GitHub, depois tente de novo.";
    } else if (err === "no_email") {
      msg.value =
        "O GitHub não devolveu e-mails verificados. Em github.com/settings/emails, confira se há um e-mail verificado e se a opção de privacidade permite o acesso ao app OAuth.";
    } else if (err === "github_email") {
      msg.value =
        "Não foi possível ler a lista de e-mails do GitHub (API user/emails). Tente de novo; se persistir, verifique o scope do OAuth App e se a API do GitHub está acessível.";
    } else if (err === "inactive_user") {
      msg.value = "Sua conta existe mas está inativa. Contacte o administrador.";
    } else if (err === "invalid_state") {
      msg.value =
        "Sessão OAuth expirada ou inválida (ex.: reinício do servidor com SECRET_KEY diferente). Abra de novo «Entrar com GitHub» a partir da aplicação.";
    } else {
      msg.value = `Erro OAuth: ${err}`;
    }
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
