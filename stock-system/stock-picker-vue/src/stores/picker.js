import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../lib/api';
import { mockDetail, mockStocks, mockTemplates } from '../data/mock';

function toTemplateId(template) {
  return template?.id ?? null;
}

export const usePickerStore = defineStore('picker', () => {
  const templates = ref([]);
  const summaries = ref([]);
  const activeTemplateId = ref(null);
  const items = ref([]);
  const total = ref(0);
  const page = ref(1);
  const pageSize = ref(5000);
  const date = ref('');
  const selectedCode = ref('');
  const detail = ref(null);
  const detailCache = ref(new Map());
  const cacheHit = ref(false);
  const loadingTemplates = ref(false);
  const loadingResults = ref(false);
  const loadingDetail = ref(false);
  const error = ref('');

  // ---- 自选股 ----
  const watchlistCodes = ref([]);
  const loadingWatchlist = ref(false);

  function restoreWatchlist() {
    try {
      const raw = localStorage.getItem('watchlist_codes');
      if (raw) watchlistCodes.value = JSON.parse(raw);
    } catch {
      watchlistCodes.value = [];
    }
  }

  function persistWatchlist() {
    localStorage.setItem('watchlist_codes', JSON.stringify(watchlistCodes.value));
  }

  function isFavorited(code) {
    return watchlistCodes.value.includes(code);
  }

  async function loadWatchlist() {
    loadingWatchlist.value = true;
    try {
      const data = await api.watchlist.list();
      watchlistCodes.value = (data || []).map((i) => i.code);
      persistWatchlist();
    } catch {
      restoreWatchlist();
    } finally {
      loadingWatchlist.value = false;
    }
  }

  async function toggleWatchlist(code) {
    if (!code) return;
    const idx = watchlistCodes.value.indexOf(code);
    if (idx >= 0) {
      watchlistCodes.value.splice(idx, 1);
      try { await api.watchlist.remove(code); } catch { /* offline ok */ }
    } else {
      watchlistCodes.value.push(code);
      try { await api.watchlist.add(code); } catch { /* offline ok */ }
    }
    persistWatchlist();
  }

  const activeTemplate = computed(() => templates.value.find((item) => item.id === activeTemplateId.value) || null);

  const summaryMap = computed(() => {
    const map = new Map();
    for (const item of summaries.value) {
      map.set(item.strategy_id, item);
    }
    return map;
  });

  function fallbackTemplates() {
    templates.value = mockTemplates;
    summaries.value = mockTemplates.map((item, index) => ({
      template_id: item.id,
      strategy_id: item.strategy_id,
      name: item.name,
      description: item.description,
      expression: item.expression,
      date: '2026-06-12',
      total: [255, 97, 90, 399][index] || 0,
    }));
    activeTemplateId.value = mockTemplates[2].id;
  }

  function fallbackResults() {
    items.value = mockStocks;
    total.value = mockStocks.length;
    date.value = '2026-06-12';
    selectedCode.value = mockStocks[0]?.code || '';
    detail.value = mockDetail;
    detailCache.value.set(mockDetail.basic.code, mockDetail);
  }

  async function loadTemplates() {
    loadingTemplates.value = true;
    error.value = '';
    try {
      const [templateData, summaryData] = await Promise.all([
        api.templates(),
        api.templateSummary(),
      ]);
      templates.value = templateData.length ? templateData : mockTemplates;
      summaries.value = summaryData.length ? summaryData : [];
      if (!summaries.value.length) {
        summaries.value = templates.value.map((item) => ({
          template_id: item.id,
          strategy_id: item.strategy_id,
          name: item.name,
          description: item.description,
          expression: item.expression,
          date: '',
          total: 0,
        }));
      }
      if (!activeTemplateId.value) {
        activeTemplateId.value = toTemplateId(templates.value[0] || mockTemplates[0]);
      }
    } catch (err) {
      fallbackTemplates();
      error.value = err?.message || '模板加载失败，已使用本地示例数据';
    } finally {
      loadingTemplates.value = false;
    }
  }

  async function loadResults(templateId = activeTemplateId.value, nextPage = 1) {
    if (!templateId) return;
    loadingResults.value = true;
    error.value = '';
    page.value = nextPage;
    try {
      const queryPageSize = pageSize.value;
      const payload = {
        markets: [],
        industries: [],
        concepts: [],
        keyword: '',
        filters: {
          include_st: false,
          exclude_suspended: true,
          min_rps50: 0,
          min_rps120: 0,
          min_rps250: 0,
        },
        formula: '',
        template_id: templateId,
        template_params: {},
        sort_by: 'rps50',
        sort_order: 'desc',
        page: nextPage,
        page_size: queryPageSize,
      };
      const first = await api.templateResults(payload);
      const totalCount = Number(first.total || 0);
      const collected = Array.isArray(first.items) ? [...first.items] : [];
      const totalPages = totalCount > queryPageSize ? Math.ceil(totalCount / queryPageSize) : 1;
      let data = first;
      for (let pageNo = 2; pageNo <= totalPages; pageNo += 1) {
        if (collected.length >= totalCount) break;
        data = await api.templateResults({
          ...payload,
          page: pageNo,
        });
        if (Array.isArray(data.items) && data.items.length) {
          collected.push(...data.items);
        }
        if (!data.items || data.items.length < queryPageSize) break;
      }
      items.value = collected;
      total.value = totalCount || collected.length;
      date.value = data.date || first.date || '';
      cacheHit.value = Boolean(data.cache_hit || first.cache_hit);
      if (items.value.length) {
        selectedCode.value = items.value[0].code;
        await loadDetail(items.value[0].code);
      } else {
        selectedCode.value = '';
        detail.value = null;
      }
    } catch (err) {
      fallbackResults();
      cacheHit.value = false;
      error.value = err?.message || '结果加载失败，已使用本地示例数据';
    } finally {
      loadingResults.value = false;
    }
  }

  async function loadDetail(code) {
    if (!code) return;
    loadingDetail.value = true;
    error.value = '';
    selectedCode.value = code;
    try {
      if (detailCache.value.has(code)) {
        detail.value = detailCache.value.get(code);
        return;
      }
      detail.value = await api.stockDetail(code);
      detailCache.value.set(code, detail.value);
    } catch (err) {
      detail.value = mockDetail;
      detailCache.value.set(code, mockDetail);
      error.value = err?.message || '详情加载失败，已使用本地示例数据';
    } finally {
      loadingDetail.value = false;
    }
  }

  async function selectTemplate(templateId) {
    activeTemplateId.value = templateId;
    page.value = 1;
    await loadResults(templateId, 1);
  }

  async function refreshCurrent() {
    if (!activeTemplateId.value) return;
    await loadResults(activeTemplateId.value, page.value);
  }

  async function boot() {
    restoreWatchlist();
    loadWatchlist();
    await loadTemplates();
    if (activeTemplateId.value) {
      await loadResults(activeTemplateId.value, 1);
    } else {
      fallbackResults();
    }
  }

  function goPage(nextPage) {
    return loadResults(activeTemplateId.value, nextPage);
  }

  async function selectRelative(delta) {
    if (!items.value.length) return;
    const currentIndex = items.value.findIndex((item) => item.code === selectedCode.value);
    const startIndex = currentIndex >= 0 ? currentIndex : 0;
    const nextIndex = (startIndex + delta + items.value.length) % items.value.length;
    const next = items.value[nextIndex];
    if (next?.code) {
      await loadDetail(next.code);
    }
  }

  return {
    templates,
    summaries,
    activeTemplateId,
    activeTemplate,
    summaryMap,
    items,
    total,
    page,
    pageSize,
    date,
    selectedCode,
    detail,
    cacheHit,
    loadingTemplates,
    loadingResults,
    loadingDetail,
    error,
    detailCache,
    boot,
    selectTemplate,
    loadDetail,
    refreshCurrent,
    goPage,
    selectRelative,
    // 自选股
    watchlistCodes,
    loadingWatchlist,
    isFavorited,
    toggleWatchlist,
    loadWatchlist,
  };
});
