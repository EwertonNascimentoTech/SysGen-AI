<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { renderPrdAssistantMarkdown } from "@/utils/prdChatMarkdown";
import { looksLikePrdMarkdown } from "@/utils/prdSaveDetect";

type Role = "user" | "assistant";
type Msg = {
  role: Role;
  content: string;
  prdSaveRecommended?: boolean;
  prdSaved?: boolean;
  /** Número da versão criada no servidor ao guardar (histórico `project_prd_versions`). */
  prdSavedVersion?: number;
};
type PendingFile = { name: string; mime: string; base64: string };

const props = withDefaults(
  defineProps<{
    projectId: number;
    /** Quando o separador PRD do projecto está visível; usado para voltar a pedir o estado da IA. */
    prdTabActive?: boolean;
  }>(),
  { prdTabActive: true },
);

const emit = defineEmits<{ "prd-saved": [] }>();
const auth = useAuthStore();
const canSavePrdToServer = computed(() => auth.hasRole("admin", "coordenador", "po"));

const messages = ref<Msg[]>([]);
const input = ref("");
const pendingFiles = ref<PendingFile[]>([]);
const sending = ref(false);
const err = ref("");
const azureOk = ref(false);
const fileRef = ref<HTMLInputElement | null>(null);
const scrollRef = ref<HTMLElement | null>(null);
const listening = ref(false);

/** Modo «chamada»: microfone contínuo + resposta falada pela IA. */
const callActive = ref(false);
const callListening = ref(false);
const callPhase = ref<"idle" | "listening" | "thinking" | "speaking">("idle");

const savingPrdIndex = ref<number | null>(null);
const prdSaveFeedback = ref("");

/** Modo ecrã inteiro: melhora leitura de mensagens longas (teleport para `body`). */
const chatExpanded = ref(false);

const storageKey = computed(() => `prd-chat-${props.projectId}`);

/** Ordem do mais recente ao mais antigo — `flex-col-reverse` no scroll coloca o recente junto ao compositor. */
const messagesNewestFirst = computed(() => {
  const arr = messages.value;
  const out: { m: Msg; i: number }[] = [];
  for (let idx = arr.length - 1; idx >= 0; idx--) {
    out.push({ m: arr[idx]!, i: idx });
  }
  return out;
});

function normalizeStoredMsg(m: Msg): Msg {
  if (m.role !== "assistant") return m;
  if (m.prdSaveRecommended !== undefined) return m;
  return { ...m, prdSaveRecommended: looksLikePrdMarkdown(m.content) };
}

function loadLocal() {
  try {
    const raw = localStorage.getItem(storageKey.value);
    if (!raw) return;
    const j = JSON.parse(raw) as { messages?: Msg[] };
    if (Array.isArray(j.messages)) messages.value = j.messages.map(normalizeStoredMsg);
  } catch {
    /* ignore */
  }
}

function saveLocal() {
  try {
    localStorage.setItem(storageKey.value, JSON.stringify({ messages: messages.value }));
  } catch {
    /* ignore */
  }
}

watch(messages, saveLocal, { deep: true });

async function refreshAzureStatus() {
  try {
    const s = await api<{ configured: boolean }>(`/projects/${props.projectId}/prd/azure-status`);
    azureOk.value = s.configured;
  } catch {
    azureOk.value = false;
  }
}

function setBodyScrollLocked(locked: boolean) {
  document.body.style.overflow = locked ? "hidden" : "";
}

function toggleChatExpanded() {
  chatExpanded.value = !chatExpanded.value;
}

function onExpandKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && chatExpanded.value) {
    e.preventDefault();
    chatExpanded.value = false;
  }
}

watch(chatExpanded, (v) => {
  setBodyScrollLocked(v);
});

onMounted(() => {
  loadLocal();
  void nextTick(() => scrollToBottom());
  window.addEventListener("keydown", onExpandKeydown);
});

watch(
  () => [props.projectId, props.prdTabActive] as const,
  ([, active]) => {
    if (active === false) return;
    void refreshAzureStatus();
  },
  { immediate: true },
);

onUnmounted(() => {
  stopCallSession();
  window.removeEventListener("keydown", onExpandKeydown);
  setBodyScrollLocked(false);
});

/** Com `flex-col-reverse`, o fundo da conversa corresponde a scrollTop === 0. */
function scrollToBottom() {
  requestAnimationFrame(() => {
    const el = scrollRef.value;
    if (el) el.scrollTop = 0;
  });
}

watch(
  () => messages.value.length,
  () => {
    void nextTick(() => scrollToBottom());
  },
);

watch(
  () => props.prdTabActive,
  (active) => {
    if (active) void nextTick(() => scrollToBottom());
  },
);

function pickFiles(ev: Event) {
  const inp = ev.target as HTMLInputElement;
  const files = inp.files;
  if (!files?.length) return;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    if (f.size > 6 * 1024 * 1024) {
      err.value = `Ficheiro demasiado grande: ${f.name} (máx. 6 MB por ficheiro).`;
      continue;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const r = reader.result as string;
      const base64 = r.includes(",") ? r.split(",")[1]! : r;
      pendingFiles.value = [...pendingFiles.value, { name: f.name, mime: f.type || "application/octet-stream", base64 }];
    };
    reader.readAsDataURL(f);
  }
  inp.value = "";
}

function removePending(i: number) {
  pendingFiles.value = pendingFiles.value.filter((_, j) => j !== i);
}

/** Troca com a API: adiciona utilizador + assistente; em erro remove a mensagem do utilizador. */
async function exchange(userText: string): Promise<string> {
  err.value = "";
  if (!azureOk.value) {
    err.value = "A IA não está configurada no servidor (Azure AI Agents ou Azure OpenAI).";
    throw new Error(err.value);
  }

  const userMsg: Msg = { role: "user", content: userText || "(Anexos)" };
  const atts = pendingFiles.value.map((p) => ({
    filename: p.name,
    mime_type: p.mime,
    content_base64: p.base64,
  }));
  pendingFiles.value = [];
  const next = [...messages.value, userMsg];
  messages.value = next;
  input.value = "";
  sending.value = true;
  callPhase.value = "thinking";
  scrollToBottom();

  try {
    const out = await api<{
      message: string;
      prd_save_recommended?: boolean;
    }>(`/projects/${props.projectId}/prd/chat`, {
      method: "POST",
      body: JSON.stringify({
        messages: next,
        mode: "interview",
        attachments: atts,
      }),
    });
    const prdRec =
      typeof out.prd_save_recommended === "boolean"
        ? out.prd_save_recommended
        : looksLikePrdMarkdown(out.message);
    messages.value = [
      ...messages.value,
      { role: "assistant", content: out.message, prdSaveRecommended: prdRec },
    ];
    scrollToBottom();
    return out.message;
  } catch (e) {
    messages.value = messages.value.slice(0, -1);
    err.value = e instanceof Error ? e.message : "Erro ao contactar a IA.";
    if (callActive.value) {
      callPhase.value = "idle";
    }
    throw e;
  } finally {
    sending.value = false;
  }
}

async function send() {
  const text = input.value.trim();
  if (!text && !pendingFiles.value.length) return;
  try {
    await exchange(text || "(Anexos)");
  } catch {
    /* err já definido */
  }
}

/** Enter envia; Shift+Enter quebra linha; ignora durante composição IME. */
function onComposerKeydown(e: KeyboardEvent) {
  if (e.key !== "Enter") return;
  if (e.shiftKey) return;
  if (e.isComposing) return;
  e.preventDefault();
  void send();
}

async function savePrdToDb(index: number) {
  const m = messages.value[index];
  if (!m || m.role !== "assistant" || m.prdSaved) return;
  err.value = "";
  prdSaveFeedback.value = "";
  savingPrdIndex.value = index;
  try {
    const out = await api<{ version?: number | null }>(`/projects/${props.projectId}/prd/markdown`, {
      method: "PUT",
      body: JSON.stringify({ markdown: m.content }),
    });
    const ver = typeof out.version === "number" ? out.version : undefined;
    messages.value = messages.value.map((msg, i) =>
      i === index ? { ...msg, prdSaved: true, prdSavedVersion: ver } : msg,
    );
    const feedbackMsg =
      ver != null
        ? `PRD guardado na base de dados (versão ${ver}).`
        : "PRD guardado na base de dados.";
    prdSaveFeedback.value = feedbackMsg;
    emit("prd-saved");
    window.setTimeout(() => {
      if (prdSaveFeedback.value === feedbackMsg) prdSaveFeedback.value = "";
    }, 5000);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Não foi possível guardar o PRD.";
  } finally {
    savingPrdIndex.value = null;
  }
}

// ——— Reconhecimento de voz (botão «Falar») ———
let recognition: { stop: () => void; start: () => void } | null = null;

function toggleVoice() {
  if (callActive.value) return;
  err.value = "";
  const w = window as unknown as {
    SpeechRecognition?: new () => RecInstance;
    webkitSpeechRecognition?: new () => RecInstance;
  };
  type RecInstance = {
    lang: string;
    interimResults: boolean;
    maxAlternatives: number;
    continuous: boolean;
    onresult: ((ev: { results: { 0: { transcript: string }[] }[] }) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
    start: () => void;
    stop: () => void;
  };
  const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!SR) {
    err.value = "O teu browser não suporta reconhecimento de voz (experimenta Chrome).";
    return;
  }
  if (listening.value) {
    recognition?.stop();
    listening.value = false;
    return;
  }
  const rec = new SR();
  rec.lang = "pt-PT";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.continuous = false;
  rec.onresult = (ev) => {
    const t = ev.results[0]?.[0]?.transcript;
    if (t) input.value = `${input.value} ${t}`.trim();
  };
  rec.onerror = () => {
    listening.value = false;
  };
  rec.onend = () => {
    listening.value = false;
  };
  recognition = rec;
  listening.value = true;
  rec.start();
}

// ——— Ligação IA (voz contínua + TTS) ———
let callRecognition: { stop: () => void; start: () => void } | null = null;

function getSpeechRecognitionCtor(): (new () => RecInst) | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => RecInst;
    webkitSpeechRecognition?: new () => RecInst;
  };
  type RecInst = {
    lang: string;
    interimResults: boolean;
    maxAlternatives: number;
    continuous: boolean;
    onresult: ((ev: { results: { 0: { transcript: string }[] }[] }) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
    start: () => void;
    stop: () => void;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function stopCallListening() {
  try {
    callRecognition?.stop();
  } catch {
    /* ignore */
  }
  callRecognition = null;
  callListening.value = false;
}

function speakAssistant(text: string): Promise<void> {
  return new Promise((resolve) => {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "pt-PT";
    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      const pt =
        voices.find((v) => v.lang.toLowerCase().startsWith("pt-pt")) ||
        voices.find((v) => v.lang.toLowerCase().startsWith("pt"));
      if (pt) u.voice = pt;
    };
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;

    u.onstart = () => {
      callPhase.value = "speaking";
    };
    u.onend = () => {
      callPhase.value = callActive.value ? "idle" : "idle";
      resolve();
    };
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

async function runCallTurn() {
  if (!callActive.value || sending.value) return;
  const SR = getSpeechRecognitionCtor();
  if (!SR) {
    err.value = "Reconhecimento de voz indisponível neste browser.";
    callActive.value = false;
    return;
  }

  stopCallListening();
  callPhase.value = "listening";

  const rec = new SR();
  rec.lang = "pt-PT";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.continuous = false;

  let gotResult = false;

  rec.onresult = async (ev) => {
    gotResult = true;
    const t = ev.results[0]?.[0]?.transcript?.trim() ?? "";
    stopCallListening();
    if (!callActive.value) return;
    if (!t) {
      scheduleNextListen();
      return;
    }
    try {
      const reply = await exchange(t);
      if (!callActive.value) return;
      await speakAssistant(reply);
      if (callActive.value) scheduleNextListen();
    } catch {
      if (callActive.value) scheduleNextListen();
    }
  };

  rec.onerror = () => {
    stopCallListening();
    if (callActive.value) scheduleNextListen();
  };

  rec.onend = () => {
    if (!gotResult && callActive.value && !sending.value && callPhase.value === "listening") {
      scheduleNextListen();
    }
  };

  callRecognition = rec;
  callListening.value = true;
  try {
    rec.start();
  } catch {
    callListening.value = false;
    scheduleNextListen();
  }
}

let listenTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleNextListen() {
  if (!callActive.value) return;
  callPhase.value = "idle";
  if (listenTimer) clearTimeout(listenTimer);
  listenTimer = setTimeout(() => {
    listenTimer = null;
    if (callActive.value && !sending.value) void runCallTurn();
  }, 400);
}

function toggleCallSession() {
  err.value = "";
  if (callActive.value) {
    stopCallSession();
    return;
  }
  if (!azureOk.value) {
    err.value = "A IA não está configurada no servidor (Azure AI Agents ou Azure OpenAI).";
    return;
  }
  const SR = getSpeechRecognitionCtor();
  if (!SR) {
    err.value = "O teu browser não suporta reconhecimento de voz (experimenta Chrome).";
    return;
  }
  listening.value = false;
  recognition?.stop();
  callActive.value = true;
  void runCallTurn();
}

function stopCallSession() {
  callActive.value = false;
  stopCallListening();
  window.speechSynthesis.cancel();
  callPhase.value = "idle";
  if (listenTimer) {
    clearTimeout(listenTimer);
    listenTimer = null;
  }
}

</script>

<template>
  <Teleport to="body" :disabled="!chatExpanded">
    <div
      :class="[
        'flex flex-col gap-6',
        chatExpanded
          ? 'fixed inset-0 z-[90] box-border flex min-h-0 cursor-default flex-col overflow-hidden bg-black/30 p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-[max(0.5rem,env(safe-area-inset-top))] backdrop-blur-[1px] sm:p-4 sm:pb-5'
          : 'w-full',
      ]"
      @click.self="chatExpanded = false"
    >
      <div
        :class="chatExpanded ? 'mx-auto flex min-h-0 w-full max-w-[min(100rem,calc(100vw-1rem))] flex-1 flex-col' : 'w-full'"
      >
    <!-- Cartão único: cabeçalho + conversa + compositor (título e ícone dentro da div branca) -->
    <div
      :class="[
        'flex flex-col overflow-hidden rounded-xl border border-outline-variant/15 bg-surface-container-lowest shadow-[0_4px_28px_-8px_rgba(25,28,30,0.09)]',
        chatExpanded ? 'min-h-0 flex-1 shadow-2xl' : 'h-[min(72vh,760px)] min-h-[22rem]',
      ]"
    >
      <header
        class="flex shrink-0 flex-col gap-1 border-b border-outline-variant/15 bg-surface-container-lowest px-5 pb-4 pt-5 sm:flex-row sm:items-start sm:justify-between sm:gap-4 sm:px-6"
      >
        <div class="min-w-0 flex-1 pr-2">
          <h2 class="font-headline text-2xl font-extrabold tracking-tight text-on-surface md:text-3xl">Entrevista PRD</h2>
          <p class="font-body text-sm font-medium text-on-surface-variant">Módulo de engenharia de PRD em tempo real</p>
          <p v-if="!azureOk" class="mt-2 max-w-xl font-body text-xs text-error">
            Configure <code class="font-mono text-[11px]">AZURE_AI_*</code> (Agents) ou
            <code class="font-mono text-[11px]">AZURE_OPENAI_*</code> no servidor para activar o chat.
          </p>
        </div>
        <button
          type="button"
          class="mt-2 inline-flex shrink-0 items-center justify-center self-start rounded-lg border border-outline-variant/25 bg-surface-container-low p-2 text-on-surface shadow-sm transition-colors hover:bg-surface-container-high sm:mt-0"
          :aria-expanded="chatExpanded"
          :aria-label="chatExpanded ? 'Sair do modo expandido' : 'Expandir conversa'"
          :title="chatExpanded ? 'Sair do modo expandido (Esc)' : 'Expandir conversa'"
          @click="toggleChatExpanded"
        >
          <span class="material-symbols-outlined text-2xl text-primary" aria-hidden="true">{{
            chatExpanded ? "close_fullscreen" : "open_in_full"
          }}</span>
        </button>
      </header>
      <section
        ref="scrollRef"
        class="prd-chat-scroll flex min-h-0 flex-1 flex-col-reverse gap-8 overflow-y-auto overscroll-contain p-6"
      >
        <div
          v-if="!messages.length"
          class="rounded-xl bg-surface-container-low/80 px-6 py-10 text-center"
        >
          <p class="mx-auto max-w-lg font-body text-sm italic leading-relaxed text-on-surface-variant">
            Ex.: descreve o âmbito do produto ou os stakeholders. A IA conduz a entrevista para fechares o PRD.
          </p>
        </div>

        <template v-for="({ m, i }) in messagesNewestFirst" :key="i">
          <!-- Assistente -->
          <div v-if="m.role === 'assistant'" class="flex max-w-[85%] gap-4">
            <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-container">
              <span class="material-symbols-outlined text-lg text-white" style="font-variation-settings: 'FILL' 1"
                >smart_toy</span
              >
            </div>
            <div class="flex min-w-0 flex-1 flex-col gap-3">
              <div class="rounded-2xl rounded-tl-none bg-surface-container-low p-5 text-sm leading-relaxed text-on-surface">
                <div class="prd-chat-markdown font-body" v-html="renderPrdAssistantMarkdown(m.content)" />
                <div
                  v-if="(m.prdSaveRecommended && !m.prdSaved && canSavePrdToServer) || m.prdSaved"
                  class="mt-4 flex flex-wrap items-center justify-end gap-3 border-t border-outline-variant/25 pt-4"
                >
                  <button
                    v-if="m.prdSaveRecommended && !m.prdSaved && canSavePrdToServer"
                    type="button"
                    class="inline-flex items-center gap-2 font-label text-[11px] font-bold uppercase tracking-wider text-primary transition-opacity hover:opacity-70 disabled:opacity-50"
                    :disabled="savingPrdIndex === i"
                    @click="savePrdToDb(i)"
                  >
                    <span class="material-symbols-outlined text-base" :class="{ 'animate-spin': savingPrdIndex === i }">{{
                      savingPrdIndex === i ? "progress_activity" : "save_as"
                    }}</span>
                    {{ savingPrdIndex === i ? "A guardar…" : "Guardar PRD (MD)" }}
                  </button>
                  <span v-if="m.prdSaved" class="font-body text-[10px] font-semibold text-primary">
                    {{ m.prdSavedVersion != null ? `Guardado · v${m.prdSavedVersion}` : "Guardado no servidor" }}
                  </span>
                </div>
              </div>
              <span class="ml-1 font-label text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant">
                Assistente IA · Governança
              </span>
            </div>
          </div>
          <!-- Utilizador -->
          <div v-else class="ml-auto flex max-w-[85%] flex-row-reverse gap-4">
            <div
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-outline-variant/30 bg-surface-container-highest"
            >
              <span class="material-symbols-outlined text-on-surface-variant text-[20px]">person</span>
            </div>
            <div class="flex min-w-0 flex-1 flex-col items-end gap-2 text-right">
              <div class="rounded-2xl rounded-tr-none bg-primary p-4 text-sm text-on-primary shadow-sm">
                <p class="whitespace-pre-wrap text-left font-body leading-relaxed">{{ m.content }}</p>
              </div>
              <div class="mr-1 flex items-center gap-1">
                <span class="font-label text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant">Tu</span>
                <span class="material-symbols-outlined text-sm text-on-tertiary-container">done_all</span>
              </div>
            </div>
          </div>
        </template>
      </section>

      <div
        v-if="pendingFiles.length"
        class="shrink-0 space-y-2 border-t border-outline-variant/15 bg-surface-container-lowest px-6 py-4"
      >
        <div
          v-for="(f, i) in pendingFiles"
          :key="i"
          class="flex items-center gap-4 rounded-xl bg-surface-container-low p-3"
        >
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-container-highest">
            <span class="material-symbols-outlined text-on-surface-variant">description</span>
          </div>
          <div class="min-w-0 flex-1">
            <span class="block truncate font-body text-xs font-bold text-primary">{{ f.name }}</span>
            <span class="text-[10px] font-medium text-on-surface-variant">Pronto a enviar</span>
          </div>
          <button
            type="button"
            class="material-symbols-outlined shrink-0 text-on-surface-variant transition-colors hover:text-error"
            aria-label="Remover"
            @click="removePending(i)"
          >
            close
          </button>
        </div>
      </div>

      <div v-if="prdSaveFeedback || err" class="shrink-0 space-y-1 border-t border-outline-variant/10 px-6 py-3">
        <p v-if="prdSaveFeedback" class="text-center font-body text-sm font-semibold text-primary">{{ prdSaveFeedback }}</p>
        <p v-if="err" class="text-center font-body text-sm text-error">{{ err }}</p>
      </div>

      <!-- Compositor (Stitch: caixa interior + barra de acções) -->
      <footer class="shrink-0 border-t border-outline-variant/20 bg-surface-container-lowest p-6">
        <input ref="fileRef" type="file" class="hidden" multiple accept="image/*,.txt,.md,.json,.xml,text/*" @change="pickFiles" />
        <div
          class="rounded-xl border border-transparent bg-surface-container-low p-3 transition-all focus-within:border-outline-variant/35 focus-within:shadow-sm"
        >
          <textarea
            v-model="input"
            rows="3"
            class="min-h-[80px] w-full resize-none border-none bg-transparent font-body text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-0 disabled:opacity-50"
            placeholder="Descreve novos requisitos ou responde à IA…"
            :disabled="sending || callActive"
            @keydown="onComposerKeydown"
          />
          <div class="mt-2 flex flex-col gap-3 border-t border-outline-variant/20 pt-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex flex-wrap items-center gap-1">
              <button
                type="button"
                class="rounded-lg p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high disabled:opacity-40"
                title="Anexar ficheiros"
                :disabled="sending || callActive"
                @click="fileRef?.click()"
              >
                <span class="material-symbols-outlined text-xl">attach_file</span>
              </button>
              <button
                type="button"
                class="rounded-lg p-2 transition-colors hover:bg-surface-container-high disabled:opacity-40"
                :class="listening ? 'text-error' : 'text-on-surface-variant'"
                title="Ditado (uma frase)"
                :disabled="sending || callActive"
                @click="toggleVoice"
              >
                <span class="material-symbols-outlined text-xl">{{ listening ? "mic_off" : "mic" }}</span>
              </button>
              <div class="mx-1 hidden h-6 w-px bg-outline-variant/30 sm:block" />
              <button
                type="button"
                class="rounded-lg p-2 transition-colors hover:bg-surface-container-high disabled:opacity-40"
                :class="
                  callActive
                    ? 'text-error ring-1 ring-error/25'
                    : 'text-on-surface-variant'
                "
                :title="callActive ? 'Terminar ligação com a IA' : 'Ligação de voz contínua com a IA'"
                :disabled="sending || (!azureOk && !callActive)"
                @click="toggleCallSession"
              >
                <span class="material-symbols-outlined text-xl">{{ callActive ? "call_end" : "call" }}</span>
              </button>
              <span class="ml-1 hidden font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-variant/80 sm:inline"
                >Voz contínua</span
              >
            </div>
            <div class="flex flex-1 items-center justify-end gap-4 sm:flex-initial">
              <span class="hidden font-body text-[9px] font-medium text-on-surface-variant/70 sm:inline"
                >Markdown • Máx. 6 MB / ficheiro</span
              >
              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 font-label text-xs font-bold uppercase tracking-widest text-on-primary shadow-lg shadow-primary/10 transition-all hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
                :disabled="sending || callActive || (!input.trim() && !pendingFiles.length)"
                @click="send"
              >
                <span v-if="sending" class="material-symbols-outlined animate-spin text-base">progress_activity</span>
                <template v-else>
                  <span>Enviar</span>
                  <span class="material-symbols-outlined text-base" style="font-variation-settings: 'FILL' 1">send</span>
                </template>
              </button>
            </div>
          </div>
        </div>
      </footer>
    </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.prd-chat-scroll {
  overflow-anchor: none;
}
.prd-chat-scroll::-webkit-scrollbar {
  width: 4px;
}
.prd-chat-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.prd-chat-scroll::-webkit-scrollbar-thumb {
  background: rgb(198 198 205 / 0.8);
  border-radius: 10px;
}
</style>
