import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import vue from '@vitejs/plugin-vue';

const apiPort = process.env.ROCKOLA_PORT || '8000';

export default defineConfig({
	base: './',
	plugins: [vue(), tailwindcss()],
	resolve: {
		alias: {
			'@': fileURLToPath(new URL('./src', import.meta.url)),
		},
	},
	server: {
		proxy: {
			'/api': `http://127.0.0.1:${apiPort}`,
			'/command': `http://127.0.0.1:${apiPort}`,
			'/cover': `http://127.0.0.1:${apiPort}`,
			'/library': `http://127.0.0.1:${apiPort}`,
			'/lrc': `http://127.0.0.1:${apiPort}`,
			'/scan': `http://127.0.0.1:${apiPort}`,
			'/stream': `http://127.0.0.1:${apiPort}`,
			'/ws': {
				target: `ws://127.0.0.1:${apiPort}`,
				ws: true,
			},
		},
	},
});
