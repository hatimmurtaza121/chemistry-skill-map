export function mapExportUrl(mapId) {
  return `/api/maps/${encodeURIComponent(mapId)}/export`;
}

let apiProbePromise = null;

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(url, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
      ...options,
    });
    if (!res.ok) {
      throw new Error(`${url} → HTTP ${res.status}`);
    }
    const type = (res.headers.get('content-type') || '').toLowerCase();
    if (type.includes('text/html')) {
      throw new Error(
        'Tunnel returned HTML instead of JSON. Open /data/maps.json in a new tab, click Continue, then reload this page.',
      );
    }
    return res.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(`${url} timed out. Dev tunnel may be blocking data requests — try http://localhost:5000/ locally.`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Load catalog via module import when possible (works better through dev tunnels). */
async function loadCatalog() {
  try {
    const mod = await import('./data/maps.json', { with: { type: 'json' } });
    return mod.default;
  } catch {
    return fetchJson('data/maps.json');
  }
}

/** True when the Python map API is reachable (local server, Lightsail, etc.). */
export function probeMapApi() {
  if (!apiProbePromise) {
    apiProbePromise = fetch('/api/maps/generate', { method: 'OPTIONS' })
      .then((r) => r.ok || r.status === 204)
      .catch(() => false);
  }
  return apiProbePromise;
}

export function setupMapDownload(map) {
  const btn = document.getElementById('map-download');
  if (!btn || !map?.id) return;
  probeMapApi().then((ok) => {
    if (!ok) {
      btn.hidden = true;
      return;
    }
    btn.href = mapExportUrl(map.id);
    btn.download = `${map.id}-skill-map.zip`;
    btn.title = `Download ${map.name} as JSON zip`;
  });
}

export async function loadMapsCatalog() {
  return loadCatalog();
}

export function getSelectedMapId(catalog) {
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get('map');
  if (fromUrl && catalog.maps.some(m => m.id === fromUrl && m.available)) return fromUrl;
  const stored = localStorage.getItem('selectedMap');
  if (stored && catalog.maps.some(m => m.id === stored && m.available)) return stored;
  return catalog.defaultMap;
}

export function persistMapId(mapId) {
  localStorage.setItem('selectedMap', mapId);
}

export function mapDataUrl(map, file) {
  return `data/${map.dataPath}/${file}`;
}

export { fetchJson };

export function viewHref(page, mapId) {
  const base = page.includes('?') ? page : page;
  return `${base}?map=${encodeURIComponent(mapId)}`;
}

export function setupMapSelector(catalog, mapId, onChange) {
  const select = document.getElementById('map-select');
  if (!select) return;
  select.innerHTML = '';
  for (const m of catalog.maps) {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.available ? m.name : `${m.name} — coming soon`;
    opt.disabled = !m.available;
    opt.selected = m.id === mapId;
    select.appendChild(opt);
  }
  probeMapApi().then((ok) => {
    if (!ok) return;
    const createOpt = document.createElement('option');
    createOpt.value = '__create__';
    createOpt.textContent = '+ Create new map…';
    select.appendChild(createOpt);
  });
  select.onchange = () => {
    if (select.value === '__create__') {
      location.href = 'create.html';
      select.value = mapId;
      return;
    }
    const next = catalog.maps.find(m => m.id === select.value && m.available);
    if (!next) return;
    persistMapId(next.id);
    onChange(next.id);
  };
}

export function applyMapHeader(map, subtitleEl) {
  document.title = `${map.name} — Skill Graph`;
  const title = document.getElementById('page-title');
  if (title) title.textContent = map.name;
  if (subtitleEl) {
    subtitleEl.textContent = map.description || `${map.level} · ${map.subject}`;
  }
}
