import { createApp } from 'vue';

// Importamos los estilos globales (configuración de Tailwind v4 y CSS personalizado)
import './style.css';

// Componente raíz que maneja el layout y las pestañas
import App from './App.vue';

// Creamos y montamos la aplicación de Vue
const app = createApp(App);
app.mount('#app');
