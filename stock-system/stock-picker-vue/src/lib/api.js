const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

async function request(path, options = {}) {
  const url = `${defaultBaseUrl}${path}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败: ${response.status}`);
  }

  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

export const api = {
  templates: () => request('/formula/templates'),
  templateSummary: (date) => request(`/stocks/template-summary${date ? `?date=${encodeURIComponent(date)}` : ''}`),
  templateResults: (payload) =>
    request('/stocks/template-results', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  stockDetail: (code) => request(`/stocks/${encodeURIComponent(code)}`),
  kline: (code, period = 'day', signal) =>
    request(`/kline/${encodeURIComponent(code)}?period=${encodeURIComponent(period)}`, { signal }),
  watchlist: {
    list: () => request('/watchlist'),
    add: (code) => request('/watchlist', { method: 'POST', body: JSON.stringify({ code }) }),
    remove: (code) => request(`/watchlist/${encodeURIComponent(code)}`, { method: 'DELETE' }),
    check: (code) => request(`/watchlist/${encodeURIComponent(code)}`),
  },
};
