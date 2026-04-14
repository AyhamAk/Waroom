/* ══════════════════════════════════════════════
   WAR ROOM — WEB SEARCH TOOL
   Optional: set SERPER_API_KEY in .env
   Falls back gracefully with empty string if no key.
   ══════════════════════════════════════════════ */

async function webSearch(query, apiKey) {
  const key = apiKey || process.env.SERPER_API_KEY;
  if (!key) return '';

  try {
    const response = await fetch('https://google.serper.dev/search', {
      method: 'POST',
      headers: { 'X-API-KEY': key, 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: query, num: 3 }),
    });
    if (!response.ok) return '';
    const data = await response.json();
    const results = (data.organic || []).slice(0, 3);
    if (!results.length) return '';
    return results
      .map((r, i) => `[${i + 1}] ${r.title}: ${r.snippet}`)
      .join('\n');
  } catch {
    return '';
  }
}

function buildSearchQuery(agentId, live) {
  const brief = (live.brief || '').slice(0, 80);
  const feature = (live.featurePriority || '').slice(0, 60);
  const category = live.category || 'tech-startup';

  if (agentId === 'ceo') {
    return `best features for ${brief} ${category} web app 2025`;
  }
  if (agentId === 'lead-eng') {
    const topic = feature || brief;
    return `best javascript libraries for ${topic} web app 2025`;
  }
  return '';
}

module.exports = { webSearch, buildSearchQuery };
