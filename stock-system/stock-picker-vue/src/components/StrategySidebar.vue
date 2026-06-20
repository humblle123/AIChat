<template>
  <aside class="panel">
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
import { computed } from 'vue';

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
