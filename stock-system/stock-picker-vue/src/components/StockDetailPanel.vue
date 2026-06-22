<template>
  <section class="rounded-2xl border border-warm-400/50 bg-warm-100/95 p-4 shadow-sm">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-xs uppercase tracking-[0.28em] text-[#9E9790]">Detail</p>
        <h2 class="mt-1 text-lg font-semibold text-[#1C1A17]" style="font-family:var(--font-serif);letter-spacing:-0.01em">个股详情</h2>
      </div>
      <span class="rounded-full border border-warm-400/50 bg-warm-100/70 px-3 py-1 text-[11px] font-medium text-[#6B665D]">
        {{ detail?.basic?.market || 'SSE' }}
      </span>
    </div>

    <div v-if="detail" class="mt-4 space-y-4">
      <div class="rounded-2xl border border-warm-400/40 bg-warm-100/70 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h3 class="text-2xl font-semibold text-[#1C1A17]" style="font-family:var(--font-serif);letter-spacing:-0.01em">{{ detail.basic.name }}</h3>
              <button
                class="watchlist-btn"
                :class="{ active: store.isFavorited(detail.basic.code) }"
                @click="store.toggleWatchlist(detail.basic.code)"
              >
                {{ store.isFavorited(detail.basic.code) ? '★ 已自选' : '☆ 加自选' }}
              </button>
            </div>
            <p class="mt-1 text-sm text-[#6B665D]" style="font-family:var(--font-mono)">{{ detail.basic.code }} · {{ detail.basic.industry }}</p>
          </div>
          <div class="text-right">
            <div class="text-2xl font-semibold text-[#1C1A17]" style="font-family:var(--font-serif);font-variant-numeric:tabular-nums">{{ formatMoney(detail.quote.price) }}</div>
            <div class="text-sm" :class="detailChangeClass" style="font-family:var(--font-mono)">{{ formatPct(detail.quote.change_pct) }}</div>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">最新交易日</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ detail.quote.trade_date }}</div>
          </div>
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">上市天数</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ detail.basic.listed_days || '--' }}</div>
          </div>
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">RPS50</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ formatScore(detail.technicals.rps50) }}</div>
          </div>
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">RPS120</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ formatScore(detail.technicals.rps120) }}</div>
          </div>
        </div>
      </div>

      <KlineChart :code="detail.basic.code" />

      <div class="rounded-2xl border border-warm-400/40 bg-warm-100/70 p-4">
        <h4 class="text-sm font-semibold text-[#1C1A17]" style="font-family:var(--font-serif);letter-spacing:-0.01em">命中策略</h4>
        <div class="mt-3 space-y-2">
          <div
            v-for="hit in detail.template_hits"
            :key="`${hit.template_id}-${hit.strategy_id}`"
            class="rounded-xl border border-warm-400/40 bg-warm-200/80 p-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm font-medium text-[#1C1A17]" style="font-family:var(--font-serif);letter-spacing:-0.01em">{{ hit.name }}</div>
                <div class="text-xs text-[#9E9790]">{{ hit.strategy_id }}</div>
              </div>
              <span class="rounded-full bg-[#2E7D40]/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-[#2E7D40]">
                matched
              </span>
            </div>
            <p class="mt-2 text-xs leading-5 text-[#6B665D]">{{ hit.reason }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-2xl border border-warm-400/40 bg-warm-100/70 p-4">
        <h4 class="text-sm font-semibold text-[#1C1A17]" style="font-family:var(--font-serif);letter-spacing:-0.01em">基本面</h4>
        <div class="mt-3 grid grid-cols-3 gap-3">
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">PE (TTM)</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ detail.fundamentals?.pe_ttm || '--' }}</div>
          </div>
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">PB</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ detail.fundamentals?.pb || '--' }}</div>
          </div>
          <div class="rounded-xl border border-warm-400/40 bg-warm-200/80 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-[#9E9790]">ROE</div>
            <div class="mt-2 text-sm text-[#1C1A17]" style="font-family:var(--font-mono)">{{ detail.fundamentals?.roe_ttm || '--' }}%</div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="mt-4 py-12 text-center text-sm text-[#9E9790]">
      请选择一只股票查看详情
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue';
import KlineChart from './KlineChart.vue';
import { usePickerStore } from '../stores/picker';

const store = usePickerStore();

const props = defineProps({
  detail: { type: Object, default: null },
});

const detailChangeClass = computed(() => {
  const v = Number(props.detail?.quote?.change_pct);
  if (!Number.isFinite(v) || v === 0) return 'text-[#1C1A17]';
  return v > 0 ? 'text-[#B8403A]' : 'text-[#2E7D40]';
});

  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(2);
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function formatScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(1);
}
</script>
