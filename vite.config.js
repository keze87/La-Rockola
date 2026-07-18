import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
    plugins: [vue(), tailwindcss()],
    server: {
        proxy: {
            '/command': 'http://localhost:8000',
            '/library': 'http://localhost:8000',
            '/scan': 'http://localhost:8000',
            '/stream': 'http://localhost:8000',
            '/lrc': 'http://localhost:8000',
            '/cover': 'http://localhost:8000',
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true,
            },
        },
    },
});
