<template>
  <aside class="panel">
    <!-- 自选股入口 -->
    <div class="panel-section">
      <button
        class="watchlist-main-btn"
        :class="{ active: store.watchlistMode }"
        @click="store.loadWatchlistItems()"
      >
        <span>★ 我的自选</span>
        <span class="watchlist-count">{{ store.watchlistCodes.length }} 只</span>
      </button>

      <div v-if="store.watchlistMode" class="watchlist-tools">
        <div class="watchlist-actions">
          <button class="wl-btn" @click="importOpen = !importOpen">📥 导入</button>
          <button class="wl-btn" @click="exportCsv">📤 导出</button>
          <button class="wl-btn" @click="store.leaveWatchlistMode()">✕ 关闭</button>
        </div>
        <div v-if="importOpen" class="import-panel">
          <textarea
            v-model="importText"
            class="import-textarea"
            placeholder="粘贴股票代码，每行一个或用逗号分隔&#10;例如：&#10;000001&#10;600519&#10;000858"
            rows="5"
          />
          <button class="wl-btn primary" @click="doImport">确认导入</button>
          <span v-if="importMsg" class="import-msg">{{ importMsg }}</span>
        </div>
      </div>
    </div>

    <div class="panel-section">
      <div class="section-title">当前公式</div>

      <div class="formula-header">
        <div class="formula-avatar">{{ activeTemplate?.strategy_id?.toUpperCase() || '📈' }}</div>
        <div class="formula-info">
          <div class="formula-name">{{ activeTemplate?.name || '未选择公式' }}</div>
          <div class="formula-desc">{{ activeTemplate?.description || '请选择一个选股策略' }}</div>
        </div>
        <span class="strategy-tag" :class="activeTemplate?.strategy_id || ''">
          {{ activeTemplate?.strategy_id?.toUpperCase() || '--' }}
        </span>
      </div>

      <div class="editor-box">
        <div class="editor-content">
          <textarea class="formula-textarea" readonly :value="activeTemplate?.expression || '请选择左侧策略后执行选股'" />
          <div class="editor-actions">
            <button class="btn primary" type="button" :disabled="loading" @click="$emit('refresh')">
              {{ loading ? '刷新中...' : '执行选股' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="panel-section formula-panel">
      <div class="section-title">公式列表</div>

      <div class="formula-list">
        <button
          v-for="item in formulas"
          :key="item.id"
          type="button"
          class="formula-item"
          :class="{ active: String(item.id) === String(activeTemplateId) }"
          @click="$emit('select', item.id)"
        >
          <div class="formula-icon" :class="item.strategy_id">{{ item.icon }}</div>
          <div class="formula-item-info">
            <div class="formula-item-name">{{ item.name }}</div>
            <div class="formula-item-count">{{ item.countLabel }}</div>
          </div>
          <span class="strategy-tag" :class="item.strategy_id">{{ item.strategy_id }}</span>
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue';
import { usePickerStore } from '../stores/picker';

const store = usePickerStore();

const props = defineProps({
  templates: { type: Array, default: () => [] },
  summaries: { type: Array, default: () => [] },
  activeTemplateId: { type: [String, Number], default: null },
  activeTemplate: { type: Object, default: null },
  activeSummary: { type: Object, default: null },
  latestDate: { type: String, default: '' },
  cacheHit: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
});

defineEmits(['select', 'refresh']);

const importOpen = ref(false);
const importText = ref('');
const importMsg = ref('');

async function doImport() {
  const raw = importText.value;
  if (!raw.trim()) return;
  const codes = raw.split(/[\n,，\s]+/).filter(Boolean);
  const result = await store.importWatchlist(codes);
  importMsg.value = `成功导入 ${result.imported} 只（共 ${codes.length} 条）`;
  importText.value = '';
}

function exportCsv() {
  const rows = ['code,name'];
  for (const c of store.watchlistCodes) {
    const item = store.items.find((i) => i.code === c);
    rows.push(`${c},${item?.name || ''}`);
  }
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'watchlist.csv';
  a.click();
  URL.revokeObjectURL(url);
}

const iconByStrategy = {
  b1: '📊',
  s2: '🌙',
  s3: '📈',
  kd1: '⚡',
};

const displayCount = (summary) => {
  const total = Number(summary?.total);
  if (Number.isFinite(total) && total >= 0) {
    return `${total} 只`;
  }
  return '未更新';
};

const formulas = computed(() =>
  props.templates.map((item) => {
    const summary = props.summaries.find((row) => Number(row.template_id) === Number(item.id)) || null;
    return {
      ...item,
      icon: iconByStrategy[item.strategy_id] || '📌',
      countLabel: displayCount(summary),
    };
  }),
);
</script>
