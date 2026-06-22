<template>
  <div class="kline-stack">
    <section class="indicator-panel">
      <div class="indicator-header">
        <div>
          <h4 class="indicator-title">K 线</h4>
          <p class="indicator-desc">鼠标移到图上查看日期，主图叠加 ZXDQ / ZXDKX</p>
        </div>
        <div class="indicator-legend">
          <span class="legend-item rise">阳线</span>
          <span class="legend-item fall">阴线</span>
          <span class="legend-item volume">成交量</span>
          <span class="legend-item zxdq">ZXDQ</span>
          <span class="legend-item zxdkx">ZXDKX</span>
        </div>
      </div>
      <div class="kline-chart-wrap">
        <div ref="mainRef" class="kline-chart main-chart"></div>
        <div
          v-if="tooltipVisible"
          class="kline-tooltip"
          :style="{ left: `${tooltipX}px`, top: `${tooltipY}px` }"
        >
          <div class="kline-tooltip-date">{{ tooltipText.date }}</div>
          <div class="kline-tooltip-row" :class="tooltipText.upClass">
            <span class="label">涨跌幅</span>
            <span class="value">{{ tooltipText.up }}</span>
          </div>
          <div class="kline-tooltip-row">
            <span class="label">开盘</span>
            <span class="value">{{ tooltipText.open }}</span>
          </div>
          <div class="kline-tooltip-row">
            <span class="label">最高</span>
            <span class="value">{{ tooltipText.high }}</span>
          </div>
          <div class="kline-tooltip-row">
            <span class="label">最低</span>
            <span class="value">{{ tooltipText.low }}</span>
          </div>
          <div class="kline-tooltip-row">
            <span class="label">收盘</span>
            <span class="value">{{ tooltipText.close }}</span>
          </div>
        </div>
        <div v-if="!code" class="kline-empty">请选择一只股票查看K线</div>
      </div>
    </section>

    <section class="indicator-panel">
      <div class="indicator-header compact">
        <div>
          <h4 class="indicator-title">KDJ 指标</h4>
          <p class="indicator-desc">K / D / J</p>
        </div>
      </div>
      <div ref="kdjRef" class="kline-chart sub-chart"></div>
    </section>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ColorType, CrosshairMode, createChart } from 'lightweight-charts';
import { api } from '../lib/api';

const props = defineProps({
  code: { type: String, default: '' },
  period: { type: String, default: 'day' },
});

const mainRef = ref(null);
const kdjRef = ref(null);
const tooltipVisible = ref(false);
const tooltipText = ref({
  date: '',
  up: '--',
  upClass: '',
  open: '--',
  high: '--',
  low: '--',
  close: '--',
});
const tooltipX = ref(12);
const tooltipY = ref(12);
const barIndex = new Map();

let mainChart = null;
let kdjChart = null;
let candleSeries = null;
let volumeSeries = null;
let zxdqSeries = null;
let zxdkxSeries = null;
let kSeries = null;
let dSeries = null;
let jSeries = null;
let resizeObserver = null;
let mainCrosshairHandler = null;
let syncLock = false;
let visibleRangeHandlers = [];
let abortController = null;

function parseTime(value) {
  const text = String(value || '').slice(0, 10);
  const [year, month, day] = text.split('-').map(Number);
  return { year, month, day };
}

function formatDateLabel(time) {
  if (!time) return '';
  const data = typeof time === 'string' ? parseTime(time) : time;
  if (!data?.year || !data?.month || !data?.day) return '';
  return `${String(data.year)}年${String(data.month).padStart(2, '0')}月${String(data.day).padStart(2, '0')}日`;
}

function formatDateSlash(time) {
  if (!time) return '';
  const data = typeof time === 'string' ? parseTime(time) : time;
  if (!data?.year || !data?.month || !data?.day) return '';
  return `${String(data.year)}/${String(data.month).padStart(2, '0')}/${String(data.day).padStart(2, '0')}`;
}

function timeKey(time) {
  if (!time) return '';
  const data = typeof time === 'string' ? parseTime(time) : time;
  if (!data?.year || !data?.month || !data?.day) return '';
  return `${data.year}-${String(data.month).padStart(2, '0')}-${String(data.day).padStart(2, '0')}`;
}

function formatPrice(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  return num >= 100 ? num.toFixed(2) : num.toFixed(3);
}

function formatPct(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  const sign = num > 0 ? '+' : '';
  return `${sign}${num.toFixed(2)}%`;
}

function normalizePayload(payload) {
  const rows = Array.isArray(payload?.data) ? payload.data : Array.isArray(payload) ? payload : [];
  const bars = rows
    .map((item, index) => {
      const prevClose = index > 0 ? Number(rows[index - 1]?.close) : Number(item.pre_close);
      const close = Number(item.close);
      const up = Number.isFinite(Number(item.up))
        ? Number(item.up)
        : Number.isFinite(close) && Number.isFinite(prevClose) && prevClose !== 0
          ? ((close - prevClose) / prevClose) * 100
          : Number.NaN;

      return {
        time: parseTime(item.date),
        open: Number(item.open),
        high: Number(item.high),
        low: Number(item.low),
        close,
        volume: Number(item.volume || 0),
        up,
      };
    })
    .filter((item) =>
      Number.isFinite(item.open) &&
      Number.isFinite(item.high) &&
      Number.isFinite(item.low) &&
      Number.isFinite(item.close),
    );

  const kValues = Array.isArray(payload?.k) ? payload.k : [];
  const dValues = Array.isArray(payload?.d) ? payload.d : [];
  const jValues = Array.isArray(payload?.j) ? payload.j : [];

  const kdj = bars.map((bar, index) => ({
    time: bar.time,
    K: Number(kValues[index]),
    D: Number(dValues[index]),
    J: Number(jValues[index]),
  })).filter((item) => Number.isFinite(item.K) || Number.isFinite(item.D) || Number.isFinite(item.J));
  return { bars, kdj };
}

function buildLineSeriesData(rows, key) {
  return rows
    .map((row) => ({
      time: row.time,
      value: row[key],
    }))
    .filter((item) => Number.isFinite(item.value));
}

function smaSeries(values, period) {
  const result = [];
  const weight = 1 / period;
  for (let i = 0; i < values.length; i += 1) {
    const current = values[i];
    if (!Number.isFinite(current)) {
      result.push(Number.NaN);
      continue;
    }
    if (i === 0 || !Number.isFinite(result[i - 1])) {
      result.push(current);
    } else {
      result.push(current * weight + result[i - 1] * (1 - weight));
    }
  }
  return result;
}

function emaSeries(values, period) {
  const result = [];
  const weight = 2 / (period + 1);
  for (let i = 0; i < values.length; i += 1) {
    const current = values[i];
    if (!Number.isFinite(current)) {
      result.push(Number.NaN);
      continue;
    }
    if (i === 0 || !Number.isFinite(result[i - 1])) {
      result.push(current);
    } else {
      result.push(current * weight + result[i - 1] * (1 - weight));
    }
  }
  return result;
}

function buildPriceOverlaySeries(bars) {
  const closes = bars.map((bar) => bar.close);
  const zxdq = emaSeries(emaSeries(closes, 10), 10);
  const s14 = smaSeries(closes, 14);
  const s28 = smaSeries(closes, 28);
  const s57 = smaSeries(closes, 57);
  const s114 = smaSeries(closes, 114);

  return bars.map((bar, index) => ({
    time: bar.time,
    zxdq: zxdq[index],
    zxdkx: [s14[index], s28[index], s57[index], s114[index]].every((value) => Number.isFinite(value))
      ? (s14[index] + s28[index] + s57[index] + s114[index]) / 4
      : Number.NaN,
  }));
}

function applyData(main, kdj) {
  if (!candleSeries || !volumeSeries || !zxdqSeries || !zxdkxSeries || !kSeries || !dSeries || !jSeries) return;

  barIndex.clear();
  main.bars.forEach((bar) => {
    barIndex.set(timeKey(bar.time), bar);
  });

  candleSeries.setData(main.bars);
  volumeSeries.setData(
    main.bars.map((bar) => ({
      time: bar.time,
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(184,64,58,0.35)' : 'rgba(46,125,64,0.35)',
    })),
  );
  const overlay = buildPriceOverlaySeries(main.bars);
  zxdqSeries.setData(
    overlay
      .map((row) => ({ time: row.time, value: row.zxdq }))
      .filter((item) => Number.isFinite(item.value)),
  );
  zxdkxSeries.setData(
    overlay
      .map((row) => ({ time: row.time, value: row.zxdkx }))
      .filter((item) => Number.isFinite(item.value)),
  );
  kSeries.setData(buildLineSeriesData(kdj, 'K'));
  dSeries.setData(buildLineSeriesData(kdj, 'D'));
  jSeries.setData(buildLineSeriesData(kdj, 'J'));

  mainChart?.timeScale().fitContent();
  kdjChart?.timeScale().fitContent();
}

async function loadChartData() {
  if (!props.code || !mainChart || !kdjChart) return;
  if (abortController) abortController.abort();
  abortController = new AbortController();
  const { signal } = abortController;
  try {
    const payload = await api.kline(props.code, props.period, signal);
    if (signal.aborted) return;
    const data = normalizePayload(payload);
    applyData(data, data.kdj);
  } catch (e) {
    if (e.name === 'AbortError') return;
    candleSeries?.setData([]);
    volumeSeries?.setData([]);
    kSeries?.setData([]);
    dSeries?.setData([]);
    jSeries?.setData([]);
    zxdqSeries?.setData([]);
    zxdkxSeries?.setData([]);
  }
}

function makeChart(container, height) {
  return createChart(container, {
    width: container.clientWidth,
    height,
    layout: {
      background: { type: ColorType.Solid, color: '#F5F0E8' },
      textColor: '#6B665D',
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: '#E4DDD0' },
      horzLines: { color: '#E4DDD0' },
    },
    rightPriceScale: {
      borderColor: '#E4DDD0',
    },
    timeScale: {
      borderColor: '#E4DDD0',
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: () => '',
      rightBarStaysOnScroll: true,
    },
    crosshair: {
      mode: CrosshairMode.Normal,
    },
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: false,
    },
    handleScale: {
      mouseWheel: true,
      pinch: true,
      axisPressedMouseMove: true,
    },
  });
}

function bindVisibleRangeSync(sourceChart, targetCharts) {
  const handler = (range) => {
    if (syncLock || !range) return;
    syncLock = true;
    targetCharts.forEach((target) => {
      target.timeScale().setVisibleLogicalRange(range);
    });
    syncLock = false;
  };
  sourceChart.timeScale().subscribeVisibleLogicalRangeChange(handler);
  visibleRangeHandlers.push({ chart: sourceChart, handler });
}

function initCharts() {
  if (!mainRef.value || !kdjRef.value) return;

  mainChart = makeChart(mainRef.value, 280);
  kdjChart = makeChart(kdjRef.value, 110);

  candleSeries = mainChart.addCandlestickSeries({
    upColor: '#B8403A',
    downColor: '#2E7D40',
    borderUpColor: '#ef4444',
    borderDownColor: '#22c55e',
    wickUpColor: '#ef4444',
    wickDownColor: '#22c55e',
  });

  volumeSeries = mainChart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
    color: 'rgba(196, 122, 90, 0.18)',
  });
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.78, bottom: 0 },
  });

  zxdqSeries = mainChart.addLineSeries({
    color: '#C47A5A',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
  });
  zxdkxSeries = mainChart.addLineSeries({
    color: '#7C6B5E',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
  });

  kSeries = kdjChart.addLineSeries({
    color: '#C47A5A',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
  });
  dSeries = kdjChart.addLineSeries({
    color: '#7C6B5E',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
  });
  jSeries = kdjChart.addLineSeries({
    color: '#6B665D',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
  });

  resizeObserver = new ResizeObserver(() => {
    if (!mainRef.value || !kdjRef.value) return;
    mainChart?.applyOptions({ width: mainRef.value.clientWidth, height: 280 });
    kdjChart?.applyOptions({ width: kdjRef.value.clientWidth, height: 110 });
  });
  resizeObserver.observe(mainRef.value);
  resizeObserver.observe(kdjRef.value);

  mainCrosshairHandler = (param) => {
    if (!param?.point || !param.time) {
      tooltipVisible.value = false;
      return;
    }
    const bar = barIndex.get(timeKey(param.time));
    const upValue = Number.isFinite(bar?.up) ? bar.up : Number.NaN;
    tooltipVisible.value = true;
    tooltipText.value = {
      date: formatDateSlash(param.time),
      up: formatPct(upValue),
      upClass: Number.isFinite(upValue) ? (upValue >= 0 ? 'up' : 'down') : '',
      open: formatPrice(bar?.open),
      high: formatPrice(bar?.high),
      low: formatPrice(bar?.low),
      close: formatPrice(bar?.close),
    };
    tooltipX.value = Math.min(Math.max(param.point.x + 12, 12), mainRef.value.clientWidth - 180);
    tooltipY.value = Math.min(Math.max(param.point.y + 12, 12), 12 + 280 - 128);
  };
  mainChart.subscribeCrosshairMove(mainCrosshairHandler);

  bindVisibleRangeSync(mainChart, [kdjChart]);
  bindVisibleRangeSync(kdjChart, [mainChart]);
}

watch(
  () => [props.code, props.period],
  () => {
    loadChartData();
  },
);

onMounted(() => {
  initCharts();
  loadChartData();
});

onBeforeUnmount(() => {
  abortController?.abort();
  resizeObserver?.disconnect();
  if (mainChart && mainCrosshairHandler) {
    mainChart.unsubscribeCrosshairMove(mainCrosshairHandler);
  }
  visibleRangeHandlers.forEach(({ chart, handler }) => {
    chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
  });
  mainChart?.remove();
  kdjChart?.remove();
  mainChart = null;
  kdjChart = null;
  candleSeries = null;
  volumeSeries = null;
  zxdqSeries = null;
  zxdkxSeries = null;
  kSeries = null;
  dSeries = null;
  jSeries = null;
  mainCrosshairHandler = null;
  visibleRangeHandlers = [];
});
</script>
