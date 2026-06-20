<template>
  <div class="app-shell">
    <div v-if="showLoading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载数据...</div>
    </div>

    <header class="header">
      <div class="logo">
        <div class="logo-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M3.5 18.5l6-6 4 4L22 6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M22 6.5h-5m5 0v5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
        Smart Stock Picker
      </div>
      <div class="header-date">{{ headerDateLabel }}</div>
    </header>

    <main class="main-layout">
      <StrategySidebar
        :templates="store.templates"
        :summaries="store.summaries"
        :active-template-id="store.activeTemplateId"
        :active-template="store.activeTemplate"
        :active-summary="activeSummary"
        :latest-date="store.date"
        :cache-hit="store.cacheHit"
        :loading="store.loadingTemplates || store.loadingResults"
        @select="store.selectTemplate"
        @refresh="store.refreshCurrent"
      />

      <section class="results-panel">
        <div class="date-banner">
          <div class="date-info">
            <span class="date-main">{{ displayDate }}</span>
            <span class="date-weekday">{{ displayWeekday }}</span>
          </div>
          <div class="date-status">
            <span class="status-dot"></span>
            {{ store.cacheHit ? '缓存命中' : '交易日' }}
          </div>
        </div>

        <div class="results-header">
          <div class="results-title">
            <span class="results-name">{{ store.activeTemplate?.name || '选股结果' }}</span>
            <span class="results-count">{{ store.total }}</span>
          </div>
          <div class="results-time">{{ store.date || '--' }}</div>
        </div>

        <div class="content-area">
          <div class="kline-section">
            <div class="kline-header">
              <div class="stock-info">
                <span class="stock-name">{{ klineName }}</span>
                <span class="stock-code">{{ klineCode }}</span>
                <span class="stock-price">{{ klinePrice }}</span>
                <span class="stock-change" :class="klineChangeClass">{{ klineChange }}</span>
              </div>
              <div class="kline-controls">
                <button
                  v-for="item in periods"
                  :key="item.key"
                  type="button"
                  class="period-btn"
                  :class="{ active: selectedPeriod === item.key }"
                  @click="selectedPeriod = item.key"
                >
                  {{ item.label }}
                </button>
              </div>
            </div>

            <KlineChart :code="selectedCode" :period="selectedPeriod" />
          </div>

          <div class="stock-list-section">
            <StockBoard
              ref="stockBoardRef"
              :items="store.items"
              :total="store.total"
              :selected-code="store.selectedCode"
              @select="store.loadDetail"
            />
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { usePickerStore } from './stores/picker';
import StrategySidebar from './components/StrategySidebar.vue';
import StockBoard from './components/StockBoard.vue';
import KlineChart from './components/KlineChart.vue';

const store = usePickerStore();
const selectedPeriod = ref('day');
const stockBoardRef = ref(null);
const periods = [
  { key: 'day', label: '日线' },
  { key: 'week', label: '周线' },
  { key: 'month', label: '月线' },
];

const selectedCode = computed(() => store.detail?.basic?.code || store.selectedCode || '');
const activeSummary = computed(
  () => store.summaryMap.get(store.activeTemplate?.strategy_id) || null,
);
const showLoading = computed(
  () => (store.loadingTemplates || store.loadingResults) && !store.items.length,
);

function toChineseDateLabel(value) {
  if (!value) return '--';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}年${month}月${day}日`;
}

function weekdayLabel(value) {
  if (!value) return '--';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return '--';
  return ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][date.getDay()];
}

const displayDate = computed(() => toChineseDateLabel(store.date || store.detail?.quote?.trade_date));
const displayWeekday = computed(() => weekdayLabel(store.date || store.detail?.quote?.trade_date));
const headerDateLabel = computed(() => {
  const date = store.date || store.detail?.quote?.trade_date;
  return date ? `${toChineseDateLabel(date)} · 真实数据` : '等待数据';
});
const klineName = computed(() => store.detail?.basic?.name || '--');
const klineCode = computed(() => store.detail?.basic?.code || '--');
const klinePrice = computed(() => formatMoney(store.detail?.quote?.price));
const klineChange = computed(() => formatPct(store.detail?.quote?.change_pct));
const klineChangeClass = computed(() => {
  const value = Number(store.detail?.quote?.change_pct);
  if (!Number.isFinite(value) || value === 0) return '';
  return value >= 0 ? 'up' : 'down';
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

function isEditableTarget(target) {
  if (!target) return false;
  const element = target instanceof Element ? target : null;
  if (!element) return false;
  const tag = element.tagName?.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || element.isContentEditable;
}

function handleGlobalKeydown(event) {
  if (isEditableTarget(event.target)) return;
  if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
  event.preventDefault();
  const list = stockBoardRef.value?.sortedItems;
  if (!list || !list.length) return;
  const code = store.selectedCode;
  const idx = list.findIndex((item) => item.code === code);
  const cur = idx < 0 ? 0 : idx;
  const next = cur + (event.key === 'ArrowUp' ? -1 : 1);
  const clamped = Math.max(0, Math.min(next, list.length - 1));
  const item = list[clamped];
  if (item?.code && item.code !== code) {
    store.loadDetail(item.code);
  }
}

onMounted(() => {
  store.boot();
  window.addEventListener('keydown', handleGlobalKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown);
});
</script>
