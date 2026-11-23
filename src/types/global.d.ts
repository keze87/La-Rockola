/// <reference types="vite/client" />

export {};

declare module '*.css';
declare module 'vue-sonner/style.css';

declare global {
	interface Window {
		webkitAudioContext: typeof AudioContext;
		__rockolaHandleBack?: () => boolean;
		__rockolaOnBackProgress?: (progress: number) => void;
		__rockolaOpenFogon?: () => void;
		__rockolaOpenLibrary?: () => void;
		__rockolaOpenQueue?: () => void;
		__rockolaOpenTops?: () => void;
		__rockolaSetPipMode?: (active: boolean) => void;
		__rockolaOnMediaVolumeChanged?: (level: number, muted: boolean) => void;
		__rockolaOnNativeCommandError?: (cmd: string, code: string, message: string) => void;
	}
}
