import { useEffect, useState } from 'react';
import { ArrowUpRight, BarChart3, Bot, CheckCircle2, ChevronLeft, ChevronRight, Clock3, ExternalLink, Filter, Flame, Menu, Search, Settings, X } from 'lucide-react';
import { DEFAULT_API_BASE_URL, fetchNews, fetchStats, getApiBaseUrl, isValidApiBaseUrl, resetApiBaseUrl, setApiBaseUrl, testApiConnection } from './api';

const categories = [
  { key: '', label: 'All signals', icon: '◈' },
  { key: 'AI', label: 'AI', icon: '✦' },
  { key: 'Technology', label: 'Technology', icon: '⌘' },
  { key: 'Indian Politics', label: 'Indian Politics', icon: '◎' },
];

function relativeTime(value) {
  if (!value) return 'Recently';
  const date = new Date(value);
  const minutes = Math.max(1, Math.round((Date.now() - date) / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
}

function Score({ value, label }) {
  return <span className="score"><strong>{Number(value || 0).toFixed(label === 'Impact' ? 1 : 2)}</strong><small>{label}</small></span>;
}

function ArticleCard({ article, featured = false }) {
  return <article className={`article-card ${featured ? 'featured' : ''}`}>
    <div className="card-image">
      {article.image_url ? <img src={article.image_url} alt="" loading="lazy" onError={(event) => { event.currentTarget.style.display = 'none'; }} /> : <div className="image-fallback"><Bot size={featured ? 42 : 30} /></div>}
      <span className="category-badge">{article.category || 'Signal'}</span>
    </div>
    <div className="card-content">
      <div className="meta"><span>{article.source || 'Unknown source'}</span><span><Clock3 size={13} /> {relativeTime(article.published_at)}</span></div>
      <h3>{article.title}</h3>
      {article.subcategory && <p className="subcategory">{article.subcategory}</p>}
      {article.summary && <p className="summary">{article.summary}</p>}
      {article.topics?.length > 0 && <div className="topics">{article.topics.slice(0, 4).map((topic) => <span key={topic}>{topic}</span>)}</div>}
      {article.why_it_matters && <div className="why"><b>Why it matters</b><p>{article.why_it_matters}</p></div>}
      <div className="card-footer"><div className="scores"><Score value={article.importance_score} label="Impact" /><Score value={article.ai_relevance_score} label="AI rel." /></div><a href={article.url} target="_blank" rel="noreferrer">Read article <ArrowUpRight size={15} /></a></div>
    </div>
  </article>;
}

function Skeleton() { return <div className="skeleton-card"><div className="skeleton image" /><div className="skeleton line wide" /><div className="skeleton line" /><div className="skeleton line short" /></div>; }

export default function App() {
  const [filters, setFilters] = useState({ category: '', subcategory: '', source: '', topic: '', min_importance: '', min_ai_relevance: '', search: '', sort: 'important' });
  const [data, setData] = useState({ articles: [], total: 0, page: 1, limit: 12 });
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [mobileFilters, setMobileFilters] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftApiUrl, setDraftApiUrl] = useState(getApiBaseUrl());
  const [apiError, setApiError] = useState('');
  const [connectionState, setConnectionState] = useState('idle');
  const [connectionError, setConnectionError] = useState('');

  async function load(page = 1) {
    setLoading(true); setError('');
    try { const [news, summary] = await Promise.all([fetchNews(filters, page), fetchStats()]); setData(news); setStats(summary); }
    catch (err) { setError('The signal feed is unavailable. Check that FastAPI is running.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(1); }, [filters]);
  const update = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const featured = data.articles.filter((article) => Number(article.importance_score) >= 7).slice(0, 3);
  const pageCount = Math.max(1, Math.ceil(data.total / data.limit));
  const openSettings = () => { setDraftApiUrl(getApiBaseUrl()); setApiError(''); setConnectionState('idle'); setConnectionError(''); setSettingsOpen(true); };
  const saveApiUrl = (event) => { event.preventDefault(); if (!isValidApiBaseUrl(draftApiUrl)) { setApiError('Enter a valid HTTP or HTTPS URL, for example http://localhost:8000.'); return; } setApiError(''); setApiBaseUrl(draftApiUrl); setDraftApiUrl(getApiBaseUrl()); setConnectionState('idle'); };
  const resetApiUrl = () => { const defaultUrl = resetApiBaseUrl(); setDraftApiUrl(defaultUrl); setApiError(''); setConnectionState('idle'); setConnectionError(''); };
  const checkConnection = async () => { if (!isValidApiBaseUrl(draftApiUrl)) { setApiError('Enter a valid HTTP or HTTPS URL before testing.'); return; } setConnectionState('checking'); setConnectionError(''); try { await testApiConnection(draftApiUrl.trim().replace(/\/$/, '')); setConnectionState('connected'); } catch (error) { setConnectionState('failed'); setConnectionError(error.message || 'Could not reach the backend.'); } };

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark">S</span><span>signal<span className="brand-dot">.</span></span></a><nav><a href="#feed">The feed</a><a href="#filters">Explore</a><a href="#about">About signal</a><button className="settings-link" onClick={openSettings}><Settings size={15} /> Settings</button></nav><div className="mobile-actions"><button className="mobile-settings" onClick={openSettings} aria-label="Open settings"><Settings size={18} /></button><button className="menu-button" onClick={() => setMobileFilters(!mobileFilters)} aria-label="Toggle filters">{mobileFilters ? <X /> : <Menu />}</button></div></header>
    <main>
      <section className="hero"><div><p className="eyebrow"><span className="pulse" /> Live intelligence brief</p><h1>What matters<br /><em>next.</em></h1><p className="hero-copy">A focused read on AI, technology and the forces reshaping India. No noise. Just the signals worth your time.</p></div><div className="hero-orbit"><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="orbit-core"><Bot size={34} /><span>AI<br />FIRST</span></div></div></section>
      <section className="stats-row">{[['total', 'Stories tracked'], ['ai', 'AI signals'], ['technology', 'Tech signals'], ['indian_politics', 'India / policy']].map(([key, label]) => <div className="stat" key={key}><span>{key === 'ai' ? '✦' : key === 'technology' ? '⌘' : key === 'indian_politics' ? '◎' : '◈'}</span><strong>{stats?.[key] ?? '—'}</strong><small>{label}</small></div>)}<div className="updated">Updated {relativeTime(stats?.latest_update)}</div></section>
      <section className="control-panel" id="filters"><div className="section-label"><Filter size={16} /> Refine the signal <button className="mobile-filter-toggle" onClick={() => setMobileFilters(!mobileFilters)}>{mobileFilters ? 'Hide filters' : 'Show filters'}</button></div><div className={`filters ${mobileFilters ? 'open' : ''}`}><div className="search-wrap"><Search size={18} /><input value={filters.search} onChange={(e) => update('search', e.target.value)} placeholder="Search stories, topics, sources..." /></div><div className="category-tabs">{categories.map((item) => <button className={filters.category === item.key ? 'active' : ''} key={item.key} onClick={() => update('category', item.key)}><span>{item.icon}</span>{item.label}</button>)}</div><div className="filter-grid"><input value={filters.subcategory} onChange={(e) => update('subcategory', e.target.value)} placeholder="Subcategory" /><input value={filters.source} onChange={(e) => update('source', e.target.value)} placeholder="Source" /><input value={filters.topic} onChange={(e) => update('topic', e.target.value)} placeholder="Topic" /><label>Min impact<input type="number" min="0" max="10" step="1" value={filters.min_importance} onChange={(e) => update('min_importance', e.target.value)} /></label><label>Min AI relevance<input type="number" min="0" max="1" step="0.1" value={filters.min_ai_relevance} onChange={(e) => update('min_ai_relevance', e.target.value)} /></label><select value={filters.sort} onChange={(e) => update('sort', e.target.value)}><option value="important">Most important</option><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="ai">Highest AI relevance</option></select></div></div></section>
      {error ? <div className="state-box error"><p>{error}</p><button onClick={() => load(data.page)}>Try again</button></div> : <>
        <section className="section-head" id="feed"><div><p className="eyebrow">{filters.category || 'All channels'}</p><h2>Top signals <span>/{data.total}</span></h2></div><div className="head-note"><Flame size={18} /> Ranked by real-world impact</div></section>
        {loading ? <div className="article-grid">{[1, 2, 3].map((item) => <Skeleton key={item} />)}</div> : data.articles.length === 0 ? <div className="state-box"><BarChart3 size={28} /><h3>No signals match</h3><p>Try easing your filters or search a wider topic.</p></div> : <div className="article-grid">{data.articles.map((article, index) => <ArticleCard key={article.url || index} article={article} featured={index === 0 && data.page === 1} />)}</div>}
        {!loading && data.total > data.limit && <div className="pagination"><button disabled={data.page <= 1} onClick={() => load(data.page - 1)}><ChevronLeft size={17} /> Newer</button><span>Page {data.page} of {pageCount}</span><button disabled={data.page >= pageCount} onClick={() => load(data.page + 1)}>Older <ChevronRight size={17} /></button></div>}
      </>}
    </main><footer id="about"><span>signal<span className="brand-dot">.</span></span><p>Independent attention for consequential news.</p><span>AI / TECH / INDIA</span></footer>
    {settingsOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}><section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><div className="modal-heading"><div><p className="eyebrow">Workspace controls</p><h2 id="settings-title">API configuration</h2></div><button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="Close settings"><X size={19} /></button></div><form onSubmit={saveApiUrl}><label className="api-label">Backend API URL<input value={draftApiUrl} onChange={(event) => { setDraftApiUrl(event.target.value); setApiError(''); setConnectionState('idle'); }} placeholder={DEFAULT_API_BASE_URL} autoFocus /></label>{apiError && <p className="field-error">{apiError}</p>}<div className="modal-actions"><button className="secondary-button" type="button" onClick={resetApiUrl}>Reset default</button><button className="primary-button" type="submit">Save URL</button></div></form><div className={`connection-status ${connectionState}`}><div><span className="status-dot" />{connectionState === 'checking' ? 'Testing connection...' : connectionState === 'connected' ? 'Connected' : connectionState === 'failed' ? 'Connection failed' : 'Connection not tested'}</div>{connectionError && <p>{connectionError}</p>}</div><button className="test-button" type="button" onClick={checkConnection}>{connectionState === 'connected' ? <CheckCircle2 size={16} /> : <ExternalLink size={16} />} Test Connection</button><p className="modal-note">Changes are saved in this browser and used for every API request.</p></section></div>}
  </div>;
}
