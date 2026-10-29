<script setup lang="ts">
	import { onMounted, ref } from 'vue';
	import { useLyricsEditor } from '../../composables/useLyricsEditor';
	import { usePlayer } from '../../composables/usePlayer';
	import { isLyricsEditorOpen, lyricsEditorTrack } from '../../stores/useUiStore';
	import AssEditor from './AssEditor.vue';
	import KaraokePreview from './KaraokePreview.vue';
	import LyricsDiffModal from './LyricsDiffModal.vue';
	import LyricsTokenModal from './LyricsTokenModal.vue';

	const player = usePlayer();
	const defaultTrack = {
		path: '',
		display_title: 'Pista desconocida',
		display_artist: 'Artista desconocido',
		title: '',
		artist: '',
	};

	const initialTrack =
		lyricsEditorTrack.value ||
		(player.currentTrackPath.value ? player.getTrackInfo(player.currentTrackPath.value) : null) ||
		defaultTrack;

	const editor = useLyricsEditor(initialTrack);
	const {
		track,
		audioElement,
		audioStreamUrl,
		isPlaying,
		currentTime,
		duration,
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
	} = editor;

	const audioRef = ref<HTMLAudioElement | null>(null);

	onMounted(async () => {
		if (audioRef.value) {
			audioElement.value = audioRef.value;
			if (audioRef.value.duration && !isNaN(audioRef.value.duration) && audioRef.value.duration > 0) {
				duration.value = audioRef.value.duration;
			}
		}
		await loadTokenStatus();
		await loadInitialLyrics();
	});

	function onAudioTimeUpdate() {
		if (audioRef.value) {
			currentTime.value = audioRef.value.currentTime;
		}
	}

	function onAudioLoadedMetadata() {
		if (audioRef.value && !isNaN(audioRef.value.duration)) {
			duration.value = audioRef.value.duration;
		}
	}

	function onAudioPlay() {
		isPlaying.value = true;
	}

	function onAudioPause() {
		isPlaying.value = false;
	}

	function handleClose() {
		pause();
		isLyricsEditorOpen.value = false;
		if (typeof window !== 'undefined' && window.history.length > 1) {
			window.history.back();
		}
	}

	function handleSeekInput(e: Event) {
		const target = e.target as HTMLInputElement;
		const val = parseFloat(target.value) || 0;
		seek(val);
	}

	function formatSec(seconds: number): string {
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		return `${m}:${String(s).padStart(2, '0')}`;
	}
</script>

<template>
	<div
		class="lyrics-editor-view fixed inset-0 z-[10000] flex h-full w-full flex-col overflow-hidden bg-[#1c1917] text-stone-100 select-none"
	>
		<!-- Elemento de audio en streaming directo para cero desync con el reproductor -->
		<audio
			ref="audioRef"
			:src="audioStreamUrl"
			preload="auto"
			@timeupdate="onAudioTimeUpdate"
			@loadedmetadata="onAudioLoadedMetadata"
			@play="onAudioPlay"
			@pause="onAudioPause"
			@ended="onAudioPause"
		/>

		<!-- BARRA SUPERIOR -->
		<header
			class="bg-carpincho-panel border-carpincho-border flex shrink-0 items-center justify-between border-b px-4 py-2.5 shadow-md"
		>
			<div class="flex min-w-0 items-center gap-3">
				<button
					type="button"
					class="btn-back flex items-center gap-1.5 rounded-xl bg-stone-800 px-3 py-1.5 text-xs font-semibold text-stone-300 transition-all hover:bg-stone-700 hover:text-white active:scale-95"
					@click="handleClose"
				>
					<i class="material-icons !text-sm">arrow_back</i>
					<span>Volver</span>
				</button>

				<div class="flex min-w-0 flex-col">
					<div class="flex items-center gap-2">
						<span
							class="bg-carpincho-warning/20 text-carpincho-warning rounded px-2 py-0.5 text-[0.65rem] font-bold tracking-wider uppercase"
						>
							Taller de Letras
						</span>
						<h2 class="truncate text-sm font-bold text-stone-100">
							{{ track.display_title || track.title }}
						</h2>
					</div>
					<span class="text-carpincho-secondary truncate text-xs">
						{{ track.display_artist || track.artist }}
					</span>
				</div>
			</div>

			<div class="flex shrink-0 items-center gap-2">
				<button
					type="button"
					class="btn-token flex items-center gap-1.5 rounded-xl border border-stone-700/60 bg-stone-800 px-3 py-1.5 text-xs font-medium text-stone-300 transition-all hover:bg-stone-700 hover:text-white"
					@click="isTokenModalOpen = true"
				>
					<i class="material-icons text-carpincho-warning !text-base">vpn_key</i>
					<span class="hidden sm:inline">Token BetterLyrics</span>
				</button>
			</div>
		</header>

		<!-- BARRA DE BÚSQUEDA Y SELECCIÓN DE PROVEEDOR -->
		<div
			class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-stone-800 bg-stone-900/90 px-4 py-2 text-xs"
		>
			<div class="flex min-w-[280px] flex-1 items-center gap-2">
				<input
					v-model="searchTitle"
					class="search-title-input focus:border-carpincho-warning flex-1 rounded-lg border border-stone-800 bg-stone-950 px-2.5 py-1.5 text-xs text-stone-200 focus:outline-none"
					type="text"
					placeholder="Título del tema"
				/>
				<input
					v-model="searchArtist"
					class="search-artist-input focus:border-carpincho-warning flex-1 rounded-lg border border-stone-800 bg-stone-950 px-2.5 py-1.5 text-xs text-stone-200 focus:outline-none"
					type="text"
					placeholder="Artista"
				/>
				<button
					type="button"
					:disabled="isSearching"
					class="btn-search bg-carpincho-primary text-carpincho-bg flex items-center gap-1 rounded-lg px-3 py-1.5 font-bold transition-all hover:brightness-110 disabled:opacity-50"
					@click="searchLyrics"
				>
					<i class="material-icons !text-sm">search</i>
					<span class="hidden md:inline">{{ isSearching ? 'Buscando...' : 'Buscar' }}</span>
				</button>
			</div>

			<!-- Selector de fuente devuelta en BetterLyrics -->
			<div class="flex shrink-0 items-center gap-2">
				<label class="font-medium text-stone-400">Fuente:</label>
				<select
					v-model="selectedProvider"
					class="provider-select focus:border-carpincho-warning text-carpincho-warning max-w-[240px] rounded-lg border border-stone-800 bg-stone-950 px-2.5 py-1.5 text-xs font-semibold focus:outline-none"
					@change="selectProvider(selectedProvider)"
				>
					<option v-if="providers.length === 0" value="">Sin fuentes cargadas</option>
					<option v-for="p in providers" :key="p.provider" :value="p.provider">
						{{ p.name }}
					</option>
				</select>
			</div>
		</div>

		<!-- BARRA DE REPRODUCTOR DE STREAMING Y COMPENSACIÓN DE OFFSET -->
		<div
			class="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-stone-800 bg-stone-900 px-4 py-2"
		>
			<!-- Controles de Audio Stream -->
			<div class="flex min-w-[280px] flex-1 items-center gap-3">
				<button
					type="button"
					class="btn-play bg-carpincho-warning text-carpincho-bg flex h-9 w-9 shrink-0 items-center justify-center rounded-full shadow-md transition-all hover:scale-105 active:scale-95"
					@click="togglePlay"
				>
					<i class="material-icons !text-xl font-bold">
						{{ isPlaying ? 'pause' : 'play_arrow' }}
					</i>
				</button>

				<span class="shrink-0 font-mono text-xs text-stone-300">
					{{ formatSec(currentTime) }} / {{ formatSec(duration) }}
				</span>

				<input
					type="range"
					min="0"
					:max="duration || 100"
					step="0.05"
					:value="currentTime"
					class="accent-carpincho-warning h-1.5 flex-1 cursor-pointer rounded-lg bg-stone-700"
					@input="handleSeekInput"
					@change="handleSeekInput"
				/>
			</div>

			<!-- Herramienta de Offset rápido -->
			<div class="flex shrink-0 items-center gap-1.5 text-xs text-stone-300">
				<span class="font-medium text-stone-400">Offset:</span>
				<button
					type="button"
					class="rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="applyOffset(-500)"
				>
					-500ms
				</button>
				<button
					type="button"
					class="rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="applyOffset(-100)"
				>
					-100ms
				</button>
				<span class="text-carpincho-warning min-w-[45px] px-1 text-center font-mono font-bold">
					{{ offsetMs >= 0 ? '+' : '' }}{{ offsetMs }}ms
				</span>
				<button
					type="button"
					class="offset-plus-100-btn rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="applyOffset(100)"
				>
					+100ms
				</button>
				<button
					type="button"
					class="rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="applyOffset(500)"
				>
					+500ms
				</button>
			</div>
		</div>

		<!-- BARRA DE BUSCAR Y REEMPLAZAR -->
		<div class="flex shrink-0 items-center gap-2 border-b border-stone-800/80 bg-stone-950/70 px-4 py-1.5 text-xs">
			<i class="material-icons !text-sm text-stone-500">find_replace</i>
			<input
				v-model="findText"
				type="text"
				placeholder="Buscar texto..."
				class="w-36 rounded border border-stone-800 bg-stone-900 px-2 py-1 text-xs text-stone-200 focus:outline-none"
			/>
			<input
				v-model="replaceText"
				type="text"
				placeholder="Reemplazar con..."
				class="w-36 rounded border border-stone-800 bg-stone-900 px-2 py-1 text-xs text-stone-200 focus:outline-none"
			/>
			<span v-if="findText" class="text-[0.7rem] text-stone-400">({{ matchCount }} coincidencias)</span>
			<button
				type="button"
				class="rounded bg-stone-800 px-2.5 py-1 text-xs font-semibold text-stone-200 hover:bg-stone-700"
				@click="replaceNext"
			>
				Reemplazar
			</button>
			<button
				type="button"
				class="rounded bg-stone-800 px-2.5 py-1 text-xs font-semibold text-stone-200 hover:bg-stone-700"
				@click="replaceAll"
			>
				Reemplazar todo
			</button>
		</div>

		<!-- ÁREA PRINCIPAL: EDITOR DE CÓDIGO ASS + VISTA PREVIA KARAOKE -->
		<main class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 md:flex-row">
			<!-- Panel izquierdo: Editor ASS con resaltado de sintaxis -->
			<div class="flex h-full min-h-0 min-w-0 flex-1 flex-col">
				<div class="mb-1.5 flex items-center justify-between text-xs text-stone-400">
					<span class="text-[0.7rem] font-semibold tracking-wider uppercase">
						Editor de archivo .ASS (Personalizado)
					</span>
					<span v-if="hasChanges" class="font-bold text-amber-400">● Modificado sin guardar</span>
					<span v-else class="text-stone-500">Al día</span>
				</div>
				<div class="min-h-0 flex-1">
					<AssEditor v-model="editorContent" />
				</div>
			</div>

			<!-- Panel derecho: Vista previa sincronizada de Karaoke -->
			<div class="flex h-full min-h-0 min-w-0 flex-1 flex-col">
				<div class="mb-1.5 text-xs text-[0.7rem] font-semibold tracking-wider text-stone-400 uppercase">
					Previsualización en tiempo real
				</div>
				<div class="min-h-0 flex-1">
					<KaraokePreview :ass-content="editorContent" :current-time="currentTime" @seek="seek" />
				</div>
			</div>
		</main>

		<!-- BARRA INFERIOR / FOOTER -->
		<footer
			class="bg-carpincho-panel border-carpincho-border flex shrink-0 items-center justify-between border-t px-4 py-2.5 shadow-lg"
		>
			<div class="text-xs text-stone-400">
				<span>Archivo destino:</span>
				<span class="font-mono text-stone-200">{{ track.path || 'Sin ruta' }}.ass</span>
			</div>

			<div class="flex items-center gap-3">
				<button
					type="button"
					class="rounded-xl px-4 py-2 text-xs font-semibold text-stone-400 hover:bg-stone-800"
					@click="handleClose"
				>
					Cerrar
				</button>
				<button
					type="button"
					:disabled="isSaving"
					class="btn-save bg-carpincho-primary text-carpincho-bg flex items-center gap-2 rounded-xl px-5 py-2 text-xs font-bold shadow-md transition-all hover:brightness-110 active:scale-95 disabled:opacity-50"
					@click="saveLyrics"
				>
					<i class="material-icons !text-base">save</i>
					<span>{{ isSaving ? 'Guardando...' : 'Guardar letra personalizada' }}</span>
				</button>
			</div>
		</footer>

		<!-- MODALES -->
		<LyricsTokenModal
			:is-open="isTokenModalOpen"
			:status-text="tokenStatus.status_text"
			:hours-remaining="tokenStatus.hours_remaining"
			:is-configured="tokenStatus.is_configured"
			@save="
				(tok) => {
					saveToken(tok);
					isTokenModalOpen = false;
				}
			"
			@close="isTokenModalOpen = false"
		/>

		<LyricsDiffModal
			:is-open="isDiffModalOpen"
			:original-content="originalContent"
			:new-content="editorContent"
			@confirm="confirmSave"
			@close="isDiffModalOpen = false"
		/>
	</div>
</template>
