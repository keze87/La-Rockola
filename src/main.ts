import { createApp } from 'vue';

// Import global styles (Tailwind v4 configuration and custom CSS)
import './style.css';

// Import the root component that holds your layout and tabs
import App from './App.vue';

// Create and mount the Vue application
const app = createApp(App);
app.mount('#app');
