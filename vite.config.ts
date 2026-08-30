import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import vue from '@vitejs/plugin-vue';

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
			'/command': 'http://localhost:8000',
			'/cover': 'http://localhost:8000',
			'/library': 'http://localhost:8000',
			'/lrc': 'http://localhost:8000',
			'/scan': 'http://localhost:8000',
			'/stream': 'http://localhost:8000',
			'/ws': {
				target: 'ws://localhost:8000',
				ws: true,
			},
		},
	},
});
