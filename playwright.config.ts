/**
 * Configuración de Playwright para pruebas end-to-end (E2E) aisladas de La Rockola del Carpincho.
 * Levanta el servidor FastAPI en 127.0.0.1:9199 con base de datos, configuración y carpeta de música
 * temporales en /tmp, y Vite en 127.0.0.1:4177, sin tocar DB/rockola.db ni tu biblioteca real.
 * Uso: npm run test:e2e (desde La Rockola del Carpincho).
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Buscamos Chrome/Chromium del sistema para evitar descargas adicionales de navegadores.
function resolveBrowserExecutable(): string | undefined {
	if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
		return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
	}
	const candidates = [
		'/usr/bin/google-chrome-stable',
		'/usr/bin/google-chrome',
		'/usr/bin/chromium',
		'/usr/bin/chromium-browser',
	];
	return candidates.find((candidate) => fs.existsSync(candidate));
}

// Genera un archivo WAV PCM válido mínimo (silencio) para que el escáner indexe pistas reales sin depender de ~/Music.
function writeSilentWav(filePath: string, seed: number): void {
	const sampleRate = 8000;
	const numSamples = 800; // 0.1s
	const dataSize = numSamples * 2;
	const buf = Buffer.alloc(44 + dataSize);
	buf.write('RIFF', 0);
	buf.writeUInt32LE(36 + dataSize, 4);
	buf.write('WAVE', 8);
	buf.write('fmt ', 12);
	buf.writeUInt32LE(16, 16);
	buf.writeUInt16LE(1, 20); // PCM
	buf.writeUInt16LE(1, 22); // Mono
	buf.writeUInt32LE(sampleRate, 24);
	buf.writeUInt32LE(sampleRate * 2, 28);
	buf.writeUInt16LE(2, 32);
	buf.writeUInt16LE(16, 34);
	buf.write('data', 36);
	buf.writeUInt32LE(dataSize, 40);
	buf.fill(seed & 0xff, 44);
	fs.writeFileSync(filePath, buf);
}

const e2eRoot = path.join(os.tmpdir(), 'rockola-e2e-suite');
const dataDir = path.join(e2eRoot, 'data');
const musicDir = path.join(e2eRoot, 'music');
const configPath = path.join(dataDir, 'rockola_config.json');

fs.mkdirSync(dataDir, { recursive: true });
fs.mkdirSync(musicDir, { recursive: true });

writeSilentWav(path.join(musicDir, '01 - Mate en el Fogón.wav'), 111);
writeSilentWav(path.join(musicDir, '02 - Carpincho Blues.wav'), 222);
writeSilentWav(path.join(musicDir, '03 - Siesta en el Río.wav'), 333);

const backendPort = '9199';
const frontendPort = '4177';
const baseURL = `http://127.0.0.1:${frontendPort}`;
const executablePath = resolveBrowserExecutable();

export default defineConfig({
	testDir: './tests/e2e',
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 30_000,
	expect: {
		timeout: 8_000,
	},
	reporter: [['list']],
	use: {
		baseURL,
		headless: true,
		viewport: { width: 1280, height: 860 },
		launchOptions: executablePath ? { executablePath } : undefined,
		trace: 'on-first-retry',
	},
	webServer: [
		{
			command: `python3 server.py --no-interactive --no-browser --host 127.0.0.1 --port ${backendPort} --dir "${musicDir}" --config "${configPath}"`,
			cwd: path.resolve('.'),
			url: `http://127.0.0.1:${backendPort}/api/health`,
			reuseExistingServer: false,
			timeout: 30_000,
			env: {
				...process.env,
				ROCKOLA_DATA_DIR: dataDir,
				ROCKOLA_SKIP_FRONTEND_BUILD: '1',
				ROCKOLA_ENABLE_TEST_ROUTES: '1',
				ROCKOLA_MPV_VISIBLE: 'false',
				ROCKOLA_RADIO_MODE_ENABLED: 'false',
			},
		},
		{
			command: `npx vite --host 127.0.0.1 --port ${frontendPort} --strictPort`,
			cwd: path.resolve('.'),
			url: `${baseURL}/`,
			reuseExistingServer: false,
			timeout: 30_000,
			env: {
				...process.env,
				ROCKOLA_PORT: backendPort,
			},
		},
	],
});
