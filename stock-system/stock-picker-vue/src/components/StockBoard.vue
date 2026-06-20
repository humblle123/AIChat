<template>
  <div class="stock-board">
    <div class="stock-board-scroll">
      <table class="stock-table">
        <thead>
          <tr>
            <th style="width:40px">#</th>
            <th class="sortable" @click="toggleSort('code')">
              代码 <span class="sort-arrow">{{ sortArrow('code') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('name')">
              名称 <span class="sort-arrow">{{ sortArrow('name') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('price')">
              现价 <span class="sort-arrow">{{ sortArrow('price') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('change_pct')">
              涨跌幅 <span class="sort-arrow">{{ sortArrow('change_pct') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('rps50')">
              RPS50 <span class="sort-arrow">{{ sortArrow('rps50') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('rps120')">
              RPS120 <span class="sort-arrow">{{ sortArrow('rps120') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('rps250')">
              RPS250 <span class="sort-arrow">{{ sortArrow('rps250') }}</span>
            </th>
            <th class="sortable" @click="toggleSort('score')">
              评分 <span class="sort-arrow">{{ sortArrow('score') }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, index) in sortedItems"
            :key="item.code"
            :ref="setRowRef(item.code)"
            :class="{ selected: item.code === selectedCode }"
            @click="$emit('select', item.code)"
          >
            <td class="td-index">{{ index + 1 }}</td>
            <td class="td-code">{{ item.code }}</td>
            <td>{{ item.name }}</td>
            <td class="td-price">{{ formatMoney(item.price) }}</td>
            <td>
              <span class="td-change" :class="item.change_pct >= 0 ? 'up' : 'down'">
                {{ formatPct(item.change_pct) }}
              </span>
            </td>
            <td class="td-metric">{{ formatScore(item.rps50) }}</td>
            <td class="td-metric">{{ formatScore(item.rps120) }}</td>
            <td class="td-metric">{{ formatScore(item.rps250) }}</td>
            <td>
              <span class="score-bar">
                <span class="score-fill" :style="{ width: `${score(item)}%` }"></span>
              </span>
              <span class="score-value">{{ score(item) }}</span>
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="9" class="empty-state">
              <div class="empty-state-icon">📊</div>
              暂无结果
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue';

const props = defineProps({
  items: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  selectedCode: { type: String, default: '' },
});

const emit = defineEmits(['select']);
const rowRefs = new Map();

const sortKey = ref('');
const sortAsc = ref(true);

function toggleSort(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortKey.value = key;
    sortAsc.value = true;
  }
}

function sortArrow(key) {
  if (sortKey.value !== key) return '';
  return sortAsc.value ? '\u25B2' : '\u25BC';
}

function getSortValue(item, key) {
  if (key === 'score') return score(item);
  const v = item[key];
  return v === null || v === undefined || v === '' ? -Infinity : v;
}

const sortedItems = computed(() => {
  const list = [...props.items];
  if (!sortKey.value) return list;
  list.sort((a, b) => {
    const va = getSortValue(a, sortKey.value);
    const vb = getSortValue(b, sortKey.value);
    if (typeof va === 'string' && typeof vb === 'string') {
      return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    return sortAsc.value ? va - vb : vb - va;
  });
  return list;
});

function setRowRef(code) {
  return (el) => {
    if (el) {
      rowRefs.set(code, el);
    } else {
      rowRefs.delete(code);
    }
  };
}

watch(
  () => props.selectedCode,
  async (code) => {
    if (!code) return;
    await nextTick();
    rowRefs.get(code)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  },
  { immediate: true },
);

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

function score(item) {
  const values = [item?.rps50, item?.rps120, item?.rps250]
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (!values.length) return 0;
  return Math.max(0, Math.min(100, Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)));
}

defineExpose({ sortedItems });
</script>
