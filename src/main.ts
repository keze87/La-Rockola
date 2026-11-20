import { createApp } from 'vue';

// Importamos los estilos globales (configuración de Tailwind v4 y CSS personalizado)
import './style.css';

// Componente raíz que maneja el layout y las pestañas
import App from './App.vue';
import { isNativeAndroidHost } from './composables/useAndroidHost';

// Creamos y montamos la aplicación de Vue
const app = createApp(App);
app.mount('#app');

if (
	import.meta.env.PROD &&
	typeof navigator !== 'undefined' &&
	'serviceWorker' in navigator &&
	!isNativeAndroidHost()
) {
	window.addEventListener('load', () => {
		navigator.serviceWorker.register('./sw.js').catch(() => {});
	});
}
