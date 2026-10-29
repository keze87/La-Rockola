/**
 * Composable para el Editor y Sincronizador de Letras ASS de La Rockola.
 * Maneja reproducción en streaming sin desync, búsqueda en BetterLyrics,
 * selección de proveedores, desplazamiento de offset, búsqueda/reemplazo y guardado.
 */

import { ref, computed } from 'vue';
import type { Track } from '../types';
import { apiUrl } from './useApi';

export interface LyricsProviderResult {
	provider: string;
	name: string;
	has_syllables: boolean;
	ass: string;
}

export interface TokenStatus {
	is_configured: boolean;
	status_text: string;
	hours_remaining: number;
}

/**
 * Parsea un timestamp de ASS (h:mm:ss.cs) a segundos.
 */
export function assTimeToSeconds(timeStr: string): number {
	const parts = timeStr.trim().split(':');
	if (parts.length === 3) {
		const h = parseFloat(parts[0]) || 0;
		const m = parseFloat(parts[1]) || 0;
		const s = parseFloat(parts[2]) || 0;
		return h * 3600 + m * 60 + s;
	}
	return parseFloat(timeStr) || 0;
}

/**
 * Formatea segundos a timestamp estándar de ASS (h:mm:ss.cs con centésimas).
 */
export function secondsToAssTime(totalSeconds: number): string {
	const clamped = Math.max(0, totalSeconds);
	const h = Math.floor(clamped / 3600);
	const m = Math.floor((clamped % 3600) / 60);
	const s = Math.floor(clamped % 60);
	const cs = Math.floor(Math.round((clamped - Math.floor(clamped)) * 100));

	const mStr = String(m).padStart(2, '0');
	const sStr = String(s).padStart(2, '0');
	const csStr = String(cs).padStart(2, '0');

	return `${h}:${mStr}:${sStr}.${csStr}`;
}

/**
 * Aplica un desplazamiento (offset en milisegundos) a todos los eventos Dialogue del texto ASS.
 */
export function shiftAssTimestamps(assContent: string, deltaMs: number): string {
	const deltaSeconds = deltaMs / 1000;
	const lines = assContent.split(/\r?\n/);

	const shiftedLines = lines.map((line) => {
		const match = line.match(/^(Dialogue:\s*\d+,)(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2})(,.*)$/);
		if (!match) return line;

		const prefix = match[1];
		const startTime = assTimeToSeconds(match[2]);
		const endTime = assTimeToSeconds(match[3]);
		const rest = match[4];

		const newStart = secondsToAssTime(startTime + deltaSeconds);
		const newEnd = secondsToAssTime(endTime + deltaSeconds);

		return `${prefix}${newStart},${newEnd}${rest}`;
	});

	return shiftedLines.join('\n');
}

export function useLyricsEditor(initialTrack: Track) {
	const track = ref<Track>(initialTrack);

	// 1. Audio en Streaming directo del backend para evitar demoras por red o MPV
	const audioElement = ref<HTMLAudioElement | null>(null);
	const isPlaying = ref(false);
	const currentTime = ref(0);
	const duration = ref(0);

	const audioStreamUrl = computed(() => {
		const encoded = encodeURIComponent(track.value.path);
		return apiUrl(`/stream?path=${encoded}`);
	});

	function play() {
		if (audioElement.value) {
			audioElement.value.play().catch(() => {});
			isPlaying.value = true;
		}
	}

	function pause() {
		if (audioElement.value) {
			audioElement.value.pause();
			isPlaying.value = false;
		}
	}

	function togglePlay() {
		if (isPlaying.value) pause();
		else play();
	}

	function seek(seconds: number) {
		const clamped = Math.max(0, Math.min(seconds, duration.value || 0));
		if (audioElement.value) {
			audioElement.value.currentTime = clamped;
		}
		currentTime.value = clamped;
	}

	// 2. Editor de contenido ASS y control de cambios
	const editorContent = ref('');
	const originalContent = ref('');
	const hasChanges = computed(() => editorContent.value !== originalContent.value);

	// 3. Proveedores desde la respuesta de BetterLyrics
	const providers = ref<LyricsProviderResult[]>([]);
	const selectedProvider = ref<string>('');
	const isSearching = ref(false);
	const searchTitle = ref(initialTrack.title || initialTrack.display_title || '');
	const searchArtist = ref(initialTrack.artist || initialTrack.display_artist || '');

	async function searchLyrics() {
		isSearching.value = true;
		try {
			const qTitle = encodeURIComponent(searchTitle.value.trim());
			const qArtist = encodeURIComponent(searchArtist.value.trim());
			const res = await fetch(apiUrl(`/api/lyrics/search?title=${qTitle}&artist=${qArtist}`));
			if (!res.ok) return;

			const data = await res.json();
			if (data.providers && Array.isArray(data.providers)) {
				providers.value = data.providers;
				// Seleccionamos binimum preferentemente o el primer proveedor disponible
				const preferred =
					data.providers.find((p: LyricsProviderResult) => p.provider === 'binimum') || data.providers[0];
				if (preferred) {
					selectProvider(preferred.provider);
				}
			}
		} catch (err) {
			console.error('Error al buscar letras en BetterLyrics:', err);
		} finally {
			isSearching.value = false;
		}
	}

	function selectProvider(providerKey: string) {
		const found = providers.value.find((p) => p.provider === providerKey);
		if (found) {
			selectedProvider.value = found.provider;
			editorContent.value = found.ass;
		}
	}

	async function loadInitialLyrics() {
		try {
			const encoded = encodeURIComponent(track.value.path);
			const res = await fetch(apiUrl(`/api/lyrics/content?path=${encoded}`));
			if (!res.ok) {
				await searchLyrics();
				return;
			}

			const data = await res.json();
			if (data.exists && data.content) {
				originalContent.value = data.content;
				editorContent.value = data.content;
			} else {
				await searchLyrics();
			}
		} catch {
			await searchLyrics();
		}
	}

	// 4. Desplazamiento de offset en milisegundos
	const offsetMs = ref(0);

	function applyOffset(delta: number) {
		if (delta === 0) return;
		editorContent.value = shiftAssTimestamps(editorContent.value, delta);
		offsetMs.value += delta;
	}

	// 5. Herramienta de Buscar y Reemplazar
	const findText = ref('');
	const replaceText = ref('');

	const matchCount = computed(() => {
		if (!findText.value) return 0;
		const escaped = findText.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		const matches = editorContent.value.match(new RegExp(escaped, 'g'));
		return matches ? matches.length : 0;
	});

	function replaceNext() {
		if (!findText.value) return;
		const idx = editorContent.value.indexOf(findText.value);
		if (idx !== -1) {
			editorContent.value =
				editorContent.value.substring(0, idx) +
				replaceText.value +
				editorContent.value.substring(idx + findText.value.length);
		}
	}

	function replaceAll() {
		if (!findText.value) return;
		const escaped = findText.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		editorContent.value = editorContent.value.replace(new RegExp(escaped, 'g'), replaceText.value);
	}

	// 6. Token de BetterLyrics
	const isTokenModalOpen = ref(false);
	const tokenStatus = ref<TokenStatus>({
		is_configured: false,
		status_text: '',
		hours_remaining: 0,
	});

	async function loadTokenStatus() {
		try {
			const res = await fetch(apiUrl('/api/lyrics/token'));
			if (res.ok) {
				tokenStatus.value = await res.json();
			}
		} catch (e) {
			console.error('Error al consultar token:', e);
		}
	}

	async function saveToken(newToken: string) {
		try {
			const res = await fetch(apiUrl('/api/lyrics/token'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ token: newToken }),
			});
			if (res.ok) {
				const data = await res.json();
				tokenStatus.value.is_configured = true;
				tokenStatus.value.status_text = data.status_text;
				tokenStatus.value.hours_remaining = data.hours_remaining;
				return true;
			}
		} catch (e) {
			console.error('Error al guardar token:', e);
		}
		return false;
	}

	// 7. Modal de Diff y Guardado
	const isDiffModalOpen = ref(false);
	const isSaving = ref(false);

	async function saveLyrics() {
		// Si ya existía un archivo en disco y tiene modificaciones respecto a la carga, mostramos el diff
		if (originalContent.value && originalContent.value.trim() !== '' && hasChanges.value) {
			isDiffModalOpen.value = true;
			return;
		}
		await confirmSave();
	}

	async function confirmSave() {
		isSaving.value = true;
		try {
			const res = await fetch(apiUrl('/api/lyrics/save'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					path: track.value.path,
					content: editorContent.value,
					format: 'ass',
				}),
			});

			if (res.ok) {
				originalContent.value = editorContent.value;
				isDiffModalOpen.value = false;
				return true;
			}
		} catch (e) {
			console.error('Error al guardar archivo ASS:', e);
		} finally {
			isSaving.value = false;
		}
		return false;
	}

	return {
		track,
		audioElement,
		audioStreamUrl,
		isPlaying,
		currentTime,
		duration,
		play,
		pause,
		togglePlay,
		seek,
		editorContent,
		originalContent,
		hasChanges,
		providers,
		selectedProvider,
		isSearching,
		searchTitle,
		searchArtist,
		searchLyrics,
		selectProvider,
		loadInitialLyrics,
		offsetMs,
		applyOffset,
		findText,
		replaceText,
		matchCount,
		replaceNext,
		replaceAll,
		isTokenModalOpen,
		tokenStatus,
		loadTokenStatus,
		saveToken,
		isDiffModalOpen,
		isSaving,
		saveLyrics,
		confirmSave,
	};
}
