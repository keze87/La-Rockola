export {};

declare module '*.css';
declare module 'vue-sonner/style.css';

declare global {
	interface Window {
		webkitAudioContext: typeof AudioContext;
	}
}
