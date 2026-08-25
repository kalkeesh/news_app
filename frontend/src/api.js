export const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://ai-news-aggregator-backend-nine.vercel.app';
const API_URL_STORAGE_KEY = 'signal.apiBaseUrl';

export function getApiBaseUrl() {
  return localStorage.getItem(API_URL_STORAGE_KEY) || DEFAULT_API_BASE_URL;
}

export function isValidApiBaseUrl(value) {
  try {
    const url = new URL(value.trim());
    return ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname);
  } catch {
    return false;
  }
}

export function setApiBaseUrl(value) {
  const normalized = value.trim().replace(/\/$/, '');
  if (!isValidApiBaseUrl(normalized)) throw new Error('Enter a valid HTTP or HTTPS backend URL.');
  localStorage.setItem(API_URL_STORAGE_KEY, normalized);
  return normalized;
}

export function resetApiBaseUrl() {
  localStorage.removeItem(API_URL_STORAGE_KEY);
  return DEFAULT_API_BASE_URL;
}

export async function fetchNews(filters, page = 1) {
  const params = new URLSearchParams({ page, limit: 12, sort: filters.sort });
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined && key !== 'sort') params.set(key, value);
  });
  const response = await fetch(`${getApiBaseUrl()}/news?${params}`);
  if (!response.ok) throw new Error(`News API returned ${response.status}`);
  return response.json();
}

export async function fetchStats() {
  const response = await fetch(`${getApiBaseUrl()}/stats`);
  if (!response.ok) throw new Error(`Stats API returned ${response.status}`);
  return response.json();
}

export async function testApiConnection(baseUrl = getApiBaseUrl()) {
  const response = await fetch(`${baseUrl}/`);
  if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}.`);
  return response.json();
}
