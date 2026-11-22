const CACHE_NAME = 'rockola-shell-v2';
const SHELL_ASSETS = ['./', './index.html', './manifest.webmanifest', './favicon.png', './icon-192.png'];
const BYPASS_SEGMENTS = [
	'api',
	'stream',
	'ws',
	'cover',
	'lrc',
	'lyrics',
	'command',
	'scan',
	'library',
	'system',
	'mpv',
	'weather',
	'health',
	'test',
];

function getScopeBasePath() {
	try {
		const scopeUrl = new URL((self.registration && self.registration.scope) || './', self.location.href);
		const p = scopeUrl.pathname || '/';
		return p.endsWith('/') ? p : `${p}/`;
	} catch {
		return '/';
	}
}

const OFFLINE_HTML = `<!doctype html>
<html lang="es-AR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>La Rockola del Carpincho — Sin conexión</title>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #1f1a17; color: #f6efe7; display: grid; place-items: center; min-height: 100dvh; padding: 24px; text-align: center; }
    main { max-width: 360px; background: #2c241f; border: 1px solid #4e3f35; border-radius: 16px; padding: 24px; }
    h1 { font-size: 1.15rem; margin: 0 0 8px; }
    p { opacity: 0.85; font-size: 0.95rem; line-height: 1.45; margin: 0 0 16px; }
    button { background: #a67c52; color: #fff; border: 0; border-radius: 999px; padding: 12px 20px; font-weight: 600; cursor: pointer; }
  </style>
</head>
<body>
  <main>
    <h1>Sin conexión con la Rockola</h1>
    <p>No se pudo contactar al servidor y esta ruta todavía no está en caché. Revisá tu red Wi-Fi y volvé a intentar.</p>
    <button type="button" onclick="location.reload()">Reconectar</button>
  </main>
</body>
</html>`;

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then((cache) => cache.addAll(SHELL_ASSETS).catch(() => {}))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

self.addEventListener('fetch', (event) => {
	const req = event.request;
	if (!req || req.method !== 'GET') return;

	let url;
	try {
		url = new URL(req.url);
	} catch {
		return;
	}

	if (url.origin !== self.location.origin) return;
	const basePath = getScopeBasePath();
	if (!url.pathname.startsWith(basePath)) return;
	const relPath = '/' + url.pathname.slice(basePath.length);
	if (BYPASS_SEGMENTS.some((seg) => relPath === `/${seg}` || relPath.startsWith(`/${seg}/`))) return;

	const isShellRequest =
		req.mode === 'navigate' ||
		relPath === '/' ||
		relPath === '/index.html' ||
		relPath.startsWith('/assets/') ||
		relPath.endsWith('.webmanifest');

	if (!isShellRequest) return;

	event.respondWith(
		fetch(req)
			.then((res) => {
				if (res && res.ok) {
					const copy = res.clone();
					const writePromise = caches
						.open(CACHE_NAME)
						.then((cache) => cache.put(req, copy))
						.catch(() => {});
					if (typeof event.waitUntil === 'function') {
						event.waitUntil(writePromise);
					}
				}
				return res;
			})
			.catch(async () => {
				const cached = await caches.match(req);
				if (cached) return cached;
				return new Response(OFFLINE_HTML, {
					status: 503,
					headers: { 'Content-Type': 'text/html; charset=utf-8' },
				});
			})
	);
});
