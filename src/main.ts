import { Capacitor } from '@capacitor/core';
import { createApp } from 'vue';

// Importamos los estilos globales (configuración de Tailwind v4 y CSS personalizado)
import './style.css';

// Componente raíz que maneja el layout y las pestañas
import App from './App.vue';
import { isNativeAndroidHost, reportAndroidWebError } from './composables/useAndroidHost';
import { setupServiceWorker } from './pwa/registerSw';

// Creamos y montamos la aplicación de Vue
const app = createApp(App);

app.config.errorHandler = (err, _instance, info) => {
	const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
	console.error('[VueError]', info, err);
	reportAndroidWebError(msg, `vue:${info}`);
};

if (typeof window !== 'undefined' && isNativeAndroidHost()) {
	window.addEventListener('error', (event) => {
		const msg = event.error instanceof Error ? `${event.error.name}: ${event.error.message}` : event.message;
		reportAndroidWebError(msg || 'Unhandled window error', `${event.filename || 'window'}:${event.lineno || 0}`);
	});
	window.addEventListener('unhandledrejection', (event) => {
		const reason = event.reason;
		const msg = reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason);
		reportAndroidWebError(msg || 'Unhandled promise rejection', 'unhandledrejection');
	});
}

app.mount('#app');

if (Capacitor.isNativePlatform()) {
	void setupServiceWorker();
} else if (typeof window !== 'undefined') {
	window.addEventListener('load', () => {
		void setupServiceWorker();
	});
}
