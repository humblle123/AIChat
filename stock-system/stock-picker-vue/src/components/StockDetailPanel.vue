<template>
  <section class="rounded-3xl border border-white/10 bg-slate-950/80 p-4 shadow-glow backdrop-blur">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-xs uppercase tracking-[0.28em] text-slate-500">Detail</p>
        <h2 class="mt-1 text-lg font-semibold text-slate-50">个股详情</h2>
      </div>
      <span class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium text-slate-300">
        {{ detail?.basic?.market || 'SSE' }}
      </span>
    </div>

    <div v-if="detail" class="mt-4 space-y-4">
      <div class="rounded-3xl border border-white/8 bg-white/5 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-2xl font-semibold text-slate-50">{{ detail.basic.name }}</h3>
            <p class="mt-1 font-mono text-sm text-slate-400">{{ detail.basic.code }} · {{ detail.basic.industry }}</p>
          </div>
          <div class="text-right">
            <div class="font-mono text-2xl font-semibold text-emerald-300">{{ formatMoney(detail.quote.price) }}</div>
            <div class="font-mono text-sm text-rose-300">{{ formatPct(detail.quote.change_pct) }}</div>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div class="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-slate-500">最新交易日</div>
            <div class="mt-2 font-mono text-sm text-slate-50">{{ detail.quote.trade_date }}</div>
          </div>
          <div class="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-slate-500">上市天数</div>
            <div class="mt-2 font-mono text-sm text-slate-50">{{ detail.basic.listed_days || '--' }}</div>
          </div>
          <div class="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-slate-500">RPS50</div>
            <div class="mt-2 font-mono text-sm text-slate-50">{{ formatScore(detail.technicals.rps50) }}</div>
          </div>
          <div class="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <div class="text-[10px] uppercase tracking-[0.24em] text-slate-500">RPS120</div>
            <div class="mt-2 font-mono text-sm text-slate-50">{{ formatScore(detail.technicals.rps120) }}</div>
          </div>
        </div>
      </div>

      <KlineChart :code="detail.basic.code" />

      <div class="rounded-3xl border border-white/8 bg-white/5 p-4">
        <h4 class="text-sm font-semibold text-slate-100">命中策略</h4>
        <div class="mt-3 space-y-2">
          <div
            v-for="hit in detail.template_hits"
            :key="`${hit.template_id}-${hit.strategy_id}`"
            class="rounded-2xl border border-white/8 bg-slate-900/70 p-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm font-medium text-slate-100">{{ hit.name }}</div>
                <div class="text-xs text-slate-500">{{ hit.strategy_id }}</div>
              </div>
              <span class="rounded-full bg-emerald-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-emerald-200">
                matched
              </span>
            </div>
            <p class="mt-2 text-xs leading-5 text-slate-400">{{ hit.reason }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="mt-6 rounded-3xl border border-dashed border-white/10 bg-white/5 px-4 py-12 text-center">
      <p class="text-sm text-slate-400">选中一只股票后，这里会显示详情、指标和命中策略。</p>
    </div>
  </section>
</template>

<script setup>
import KlineChart from './KlineChart.vue';

const props = defineProps({
  detail: { type: Object, default: null },
});

function formatMoney(value) {
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
