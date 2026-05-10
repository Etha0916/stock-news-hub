<script setup lang="ts">
/**
 * K-line chart wrapper around TradingView's lightweight-charts.
 *
 * Re-creates the chart on container mount; replaces series data when the
 * `candles` prop updates. ResizeObserver keeps the chart fluid on phone
 * rotation / sidebar collapse.
 */
import { ref, watch, onMounted, onBeforeUnmount } from "vue";
// Type-only imports get erased at compile, so no runtime cost.
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
} from "lightweight-charts";
import type { Candle } from "@/types";

// `lightweight-charts` runtime (~140KB gzipped) is dynamically imported
// inside build() so it only ships in the chunk loaded when the user
// actually visits a /ticker/* route, not in the home-page bundle.

const props = defineProps<{
  candles: Candle[];
  loading?: boolean;
  error?: string | null;
}>();

const container = ref<HTMLDivElement | null>(null);
let chart: IChartApi | null = null;
let series: ISeriesApi<"Candlestick"> | null = null;
let resizeObserver: ResizeObserver | null = null;

function toLwc(c: Candle[]): CandlestickData[] {
  return c.map((b) => ({
    time: b.time as unknown as Time, // unix seconds — accepted by lwc
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));
}

async function build() {
  if (!container.value) return;
  // Dynamic import — Vite emits this in a separate chunk
  const lwc = await import("lightweight-charts");
  if (!container.value) return; // guard: component may have unmounted

  chart = lwc.createChart(container.value, {
    autoSize: false,
    width: container.value.clientWidth,
    height: 320,
    layout: {
      background: { type: lwc.ColorType.Solid, color: "#161a22" },
      textColor: "#9aa0a6",
    },
    grid: {
      vertLines: { color: "#2a2f3a" },
      horzLines: { color: "#2a2f3a" },
    },
    timeScale: {
      borderColor: "#2a2f3a",
      timeVisible: false,
    },
    rightPriceScale: {
      borderColor: "#2a2f3a",
    },
    crosshair: {
      vertLine: { color: "#4c8bf5", width: 1, style: 3 },
      horzLine: { color: "#4c8bf5", width: 1, style: 3 },
    },
  });
  series = chart.addCandlestickSeries({
    upColor: "#10b981",
    downColor: "#f43f5e",
    borderVisible: false,
    wickUpColor: "#10b981",
    wickDownColor: "#f43f5e",
  });
  if (props.candles.length) {
    series.setData(toLwc(props.candles));
    chart.timeScale().fitContent();
  }
}

onMounted(async () => {
  await build();
  if (container.value) {
    resizeObserver = new ResizeObserver(() => {
      if (chart && container.value) {
        chart.applyOptions({ width: container.value.clientWidth });
      }
    });
    resizeObserver.observe(container.value);
  }
});

watch(
  () => props.candles,
  (val) => {
    if (series && val.length) {
      series.setData(toLwc(val));
      chart?.timeScale().fitContent();
    }
  }
);

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart?.remove();
  chart = null;
  series = null;
});
</script>

<template>
  <div class="relative bg-surface-1 border border-surface-border rounded-xl overflow-hidden">
    <div ref="container" class="w-full h-80"></div>
    <div
      v-if="loading && candles.length === 0"
      class="absolute inset-0 flex items-center justify-center text-ink-low text-sm"
    >
      Loading candles…
    </div>
    <div
      v-else-if="error"
      class="absolute inset-0 flex items-center justify-center text-rose-400 text-sm px-4 text-center"
    >
      {{ error }}
    </div>
    <div
      v-else-if="candles.length === 0"
      class="absolute inset-0 flex items-center justify-center text-ink-low text-sm"
    >
      No data
    </div>
  </div>
</template>
