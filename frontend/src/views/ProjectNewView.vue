<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

type Dir = { id: number; name: string };
type Tpl = { id: number; name: string; status: string };

const router = useRouter();
const auth = useAuthStore();
const dirs = ref<Dir[]>([]);
const templates = ref<Tpl[]>([]);
const err = ref("");

const form = ref({
  name: "",
  product_owner: "",
  directory_id: 0,
  methodology: "prd" as "prd" | "base44",
  planned_start: "",
  planned_end: "",
  template_id: 0,
});

onMounted(async () => {
  dirs.value = await api<Dir[]>("/directories");
  templates.value = await api<Tpl[]>("/kanban-templates");
  if (dirs.value[0]) form.value.directory_id = dirs.value[0].id;
  if (templates.value[0]) form.value.template_id = templates.value[0].id;
});

async function save() {
  err.value = "";
  try {
    const body = {
      name: form.value.name,
      product_owner: form.value.product_owner,
      directory_id: form.value.directory_id,
      methodology: form.value.methodology,
      planned_start: form.value.planned_start,
      planned_end: form.value.planned_end,
      template_id: form.value.template_id,
    };
    const p = await api<{ id: number }>("/projects", { method: "POST", body: JSON.stringify(body) });
    await router.push(`/projetos/${p.id}`);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Erro ao salvar";
  }
}
</script>

<template>
  <section class="max-w-3xl space-y-6" v-if="auth.hasRole('admin', 'coordenador')">
    <div>
      <h2 class="text-3xl font-headline font-bold">Novo projeto</h2>
      <p class="text-sm text-on-surface-variant mt-1 font-body">Campos obrigatórios conforme PRD (RF-01, RF-02, RF-05).</p>
    </div>
    <form class="space-y-4 bg-surface-container-low p-6 rounded-lg" @submit.prevent="save">
      <div class="grid md:grid-cols-2 gap-4">
        <label class="block text-sm font-body">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Nome</span>
          <input v-model="form.name" required class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none focus:ring-2 focus:ring-primary-container" />
        </label>
        <label class="block text-sm font-body">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">PO</span>
          <input v-model="form.product_owner" required class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none focus:ring-2 focus:ring-primary-container" />
        </label>
        <label class="block text-sm font-body">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Diretoria</span>
          <select v-model.number="form.directory_id" required class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none">
            <option v-for="d in dirs" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </label>
        <label class="block text-sm font-body">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Metodologia</span>
          <select v-model="form.methodology" class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none">
            <option value="prd">PRD</option>
            <option value="base44">Base 44</option>
          </select>
        </label>
        <label class="block text-sm font-body">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Previsão início</span>
          <input v-model="form.planned_start" type="date" required class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none" />
        </label>
        <label class="block text-sm font-body">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Previsão entrega</span>
          <input v-model="form.planned_end" type="date" required class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none" />
        </label>
        <label class="block text-sm font-body md:col-span-2">
          <span class="text-[0.65rem] uppercase tracking-widest text-on-surface-variant font-bold">Template Kanban (publicado)</span>
          <select v-model.number="form.template_id" required class="mt-1 w-full rounded-lg bg-surface-container-lowest px-3 py-2 outline-none">
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </label>
      </div>
      <p v-if="err" class="text-error text-sm">{{ err }}</p>
      <button type="submit" class="px-4 py-2 bg-primary text-on-primary rounded-md text-sm font-semibold">Salvar projeto</button>
    </form>
  </section>
  <p v-else class="text-on-surface-variant text-sm">Sem permissão para criar projetos.</p>
</template>
