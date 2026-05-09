<script setup lang="ts">
import { ref } from "vue";
import { useWatchlistStore } from "@/stores/watchlist";
import { useUiStore } from "@/stores/ui";

const watchlist = useWatchlistStore();
const ui = useUiStore();

const open = ref(false);
const input = ref("");
const busy = ref(false);
const message = ref<{ kind: "ok" | "err"; text: string } | null>(null);

async function submit() {
  const sym = input.value.trim().toUpperCase();
  if (!sym) return;
  busy.value = true;
  message.value = null;
  const res = await watchlist.add(sym);
  busy.value = false;
  if (res.ok) {
    message.value = {
      kind: "ok",
      text: ui.lang === "zh"
        ? `已新增 ${sym}(抓到 ${res.fresh_articles ?? 0} 篇新聞)`
        : `Added ${sym} (${res.fresh_articles ?? 0} articles fetched)`,
    };
    input.value = "";
    setTimeout(() => { message.value = null; open.value = false; }, 1800);
  } else {
    const errMap: Record<string, string> = {
      invalid_symbol: ui.lang === "zh" ? "格式錯誤(1-6 個英文字母)" : "Invalid format",
      already_added:  ui.lang === "zh" ? "已在你的關注清單" : "Already in watchlist",
      ticker_not_found: ui.lang === "zh" ? "找不到此代號" : "Ticker not found",
      validation_failed: ui.lang === "zh" ? "驗證失敗,稍後再試" : "Validation failed",
      db_register_failed: ui.lang === "zh" ? "DB 寫入失敗" : "DB error",
      network_error: ui.lang === "zh" ? "網路錯誤" : "Network error",
    };
    message.value = {
      kind: "err",
      text: errMap[res.error ?? ""] ?? (res.error ?? "Unknown"),
    };
  }
}

function toggle() {
  open.value = !open.value;
  if (open.value) {
    setTimeout(() => {
      const el = document.getElementById("watchlist-input");
      el?.focus();
    }, 0);
  }
}
</script>

<template>
  <div class="mt-1.5">
    <button
      v-if="!open"
      class="w-full text-left text-xs px-2 py-1.5 rounded-md bg-surface-2 hover:bg-surface-border text-ink-low hover:text-ink-mid"
      @click="toggle"
    >
      {{ ui.lang === "zh" ? "+ 新增 ticker" : "+ Add ticker" }}
    </button>

    <div v-else class="flex flex-col gap-1.5">
      <div class="flex gap-1">
        <input
          id="watchlist-input"
          v-model="input"
          type="text"
          maxlength="6"
          class="flex-1 px-2 py-1 rounded bg-surface-0 border border-surface-border text-sm uppercase focus:border-brand outline-none"
          :placeholder="ui.lang === 'zh' ? '例如 BABA' : 'e.g. BABA'"
          :disabled="busy"
          @keyup.enter="submit"
          @keyup.escape="open = false"
        />
        <button
          class="px-2 py-1 text-xs rounded bg-brand hover:bg-brand-dark text-white disabled:bg-surface-2"
          :disabled="busy || !input.trim()"
          @click="submit"
        >
          {{ busy
            ? (ui.lang === "zh" ? "驗證中…" : "...")
            : (ui.lang === "zh" ? "加入" : "Add")
          }}
        </button>
        <button
          class="px-2 py-1 text-xs rounded text-ink-low hover:text-ink-high"
          @click="open = false"
        >
          ✕
        </button>
      </div>
      <div
        v-if="message"
        class="text-[11px]"
        :class="message.kind === 'ok' ? 'text-emerald-400' : 'text-rose-400'"
      >
        {{ message.text }}
      </div>
    </div>
  </div>
</template>
