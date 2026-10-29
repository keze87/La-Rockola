<script setup lang="ts">
	import { onMounted, ref } from 'vue';
	import { useLyricsEditor } from '../../composables/useLyricsEditor';
	import { isLyricsEditorOpen, lyricsEditorTrack } from '../../stores/useUiStore';
	import AssEditor from './AssEditor.vue';
	import KaraokePreview from './KaraokePreview.vue';
	import LyricsDiffModal from './LyricsDiffModal.vue';
	import LyricsTokenModal from './LyricsTokenModal.vue';

	const defaultTrack = {
		path: '',
		display_title: 'Pista desconocida',
		display_artist: 'Artista desconocido',
		title: '',
		artist: '',
	};

	const editor = useLyricsEditor(lyricsEditorTrack.value || defaultTrack);
	const audioRef = ref<HTMLAudioElement | null>(null);

	onMounted(async () => {
		if (audioRef.value) {
			editor.audioElement.value = audioRef.value;
		}
		await editor.loadTokenStatus();
		await editor.loadInitialLyrics();
	});

	function onAudioTimeUpdate() {
		if (audioRef.value) {
			editor.currentTime.value = audioRef.value.currentTime;
		}
	}

	function onAudioLoadedMetadata() {
		if (audioRef.value) {
			editor.duration.value = audioRef.value.duration;
		}
	}

	function onAudioPlay() {
		editor.isPlaying.value = true;
	}

	function onAudioPause() {
		editor.isPlaying.value = false;
	}

	function handleClose() {
		editor.pause();
		isLyricsEditorOpen.value = false;
		if (typeof window !== 'undefined' && window.history.length > 1) {
			window.history.back();
		}
	}

	function handleSeekInput(e: Event) {
		const target = e.target as HTMLInputElement;
		const val = parseFloat(target.value) || 0;
		editor.seek(val);
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
			:src="editor.audioStreamUrl.value"
			preload="auto"
			@timeupdate="onAudioTimeUpdate"
			@loadedmetadata="onAudioLoadedMetadata"
			@play="onAudioPlay"
			@pause="onAudioPause"
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
							{{ editor.track.value.display_title || editor.track.value.title }}
						</h2>
					</div>
					<span class="text-carpincho-secondary truncate text-xs">
						{{ editor.track.value.display_artist || editor.track.value.artist }}
					</span>
				</div>
			</div>

			<div class="flex shrink-0 items-center gap-2">
				<button
					type="button"
					class="btn-token flex items-center gap-1.5 rounded-xl border border-stone-700/60 bg-stone-800 px-3 py-1.5 text-xs font-medium text-stone-300 transition-all hover:bg-stone-700 hover:text-white"
					@click="editor.isTokenModalOpen.value = true"
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
					v-model="editor.searchTitle.value"
					class="search-title-input focus:border-carpincho-warning flex-1 rounded-lg border border-stone-800 bg-stone-950 px-2.5 py-1.5 text-xs text-stone-200 focus:outline-none"
					type="text"
					placeholder="Título del tema"
				/>
				<input
					v-model="editor.searchArtist.value"
					class="search-artist-input focus:border-carpincho-warning flex-1 rounded-lg border border-stone-800 bg-stone-950 px-2.5 py-1.5 text-xs text-stone-200 focus:outline-none"
					type="text"
					placeholder="Artista"
				/>
				<button
					type="button"
					:disabled="editor.isSearching.value"
					class="btn-search bg-carpincho-primary text-carpincho-bg flex items-center gap-1 rounded-lg px-3 py-1.5 font-bold transition-all hover:brightness-110 disabled:opacity-50"
					@click="editor.searchLyrics"
				>
					<i class="material-icons !text-sm">search</i>
					<span class="hidden md:inline">{{ editor.isSearching.value ? 'Buscando...' : 'Buscar' }}</span>
				</button>
			</div>

			<!-- Selector de fuente devuelta en BetterLyrics -->
			<div class="flex shrink-0 items-center gap-2">
				<label class="font-medium text-stone-400">Fuente:</label>
				<select
					v-model="editor.selectedProvider.value"
					class="provider-select focus:border-carpincho-warning text-carpincho-warning max-w-[240px] rounded-lg border border-stone-800 bg-stone-950 px-2.5 py-1.5 text-xs font-semibold focus:outline-none"
					@change="editor.selectProvider(editor.selectedProvider.value)"
				>
					<option v-if="editor.providers.value.length === 0" value="">Sin fuentes cargadas</option>
					<option v-for="p in editor.providers.value" :key="p.provider" :value="p.provider">
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
					@click="editor.togglePlay"
				>
					<i class="material-icons !text-xl font-bold">
						{{ editor.isPlaying.value ? 'pause' : 'play_arrow' }}
					</i>
				</button>

				<span class="shrink-0 font-mono text-xs text-stone-300">
					{{ formatSec(editor.currentTime.value) }} / {{ formatSec(editor.duration.value) }}
				</span>

				<input
					type="range"
					min="0"
					:max="editor.duration.value || 100"
					step="0.05"
					:value="editor.currentTime.value"
					class="accent-carpincho-warning h-1.5 flex-1 cursor-pointer rounded-lg bg-stone-700"
					@input="handleSeekInput"
				/>
			</div>

			<!-- Herramienta de Offset rápido -->
			<div class="flex shrink-0 items-center gap-1.5 text-xs text-stone-300">
				<span class="font-medium text-stone-400">Offset:</span>
				<button
					type="button"
					class="rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="editor.applyOffset(-500)"
				>
					-500ms
				</button>
				<button
					type="button"
					class="rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="editor.applyOffset(-100)"
				>
					-100ms
				</button>
				<span class="text-carpincho-warning min-w-[45px] px-1 text-center font-mono font-bold">
					{{ editor.offsetMs.value >= 0 ? '+' : '' }}{{ editor.offsetMs.value }}ms
				</span>
				<button
					type="button"
					class="offset-plus-100-btn rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="editor.applyOffset(100)"
				>
					+100ms
				</button>
				<button
					type="button"
					class="rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-300 hover:bg-stone-700"
					@click="editor.applyOffset(500)"
				>
					+500ms
				</button>
			</div>
		</div>

		<!-- BARRA DE BUSCAR Y REEMPLAZAR -->
		<div class="flex shrink-0 items-center gap-2 border-b border-stone-800/80 bg-stone-950/70 px-4 py-1.5 text-xs">
			<i class="material-icons !text-sm text-stone-500">find_replace</i>
			<input
				v-model="editor.findText.value"
				type="text"
				placeholder="Buscar texto..."
				class="w-36 rounded border border-stone-800 bg-stone-900 px-2 py-1 text-xs text-stone-200 focus:outline-none"
			/>
			<input
				v-model="editor.replaceText.value"
				type="text"
				placeholder="Reemplazar con..."
				class="w-36 rounded border border-stone-800 bg-stone-900 px-2 py-1 text-xs text-stone-200 focus:outline-none"
			/>
			<span v-if="editor.findText.value" class="text-[0.7rem] text-stone-400">
				({{ editor.matchCount.value }} coincidencias)
			</span>
			<button
				type="button"
				class="rounded bg-stone-800 px-2.5 py-1 text-xs font-semibold text-stone-200 hover:bg-stone-700"
				@click="editor.replaceNext"
			>
				Reemplazar
			</button>
			<button
				type="button"
				class="rounded bg-stone-800 px-2.5 py-1 text-xs font-semibold text-stone-200 hover:bg-stone-700"
				@click="editor.replaceAll"
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
					<span v-if="editor.hasChanges.value" class="font-bold text-amber-400">
						● Modificado sin guardar
					</span>
					<span v-else class="text-stone-500">Al día</span>
				</div>
				<div class="min-h-0 flex-1">
					<AssEditor v-model="editor.editorContent.value" />
				</div>
			</div>

			<!-- Panel derecho: Vista previa sincronizada de Karaoke -->
			<div class="flex h-full min-h-0 min-w-0 flex-1 flex-col">
				<div class="mb-1.5 text-xs text-[0.7rem] font-semibold tracking-wider text-stone-400 uppercase">
					Previsualización en tiempo real
				</div>
				<div class="min-h-0 flex-1">
					<KaraokePreview
						:ass-content="editor.editorContent.value"
						:current-time="editor.currentTime.value"
						@seek="editor.seek"
					/>
				</div>
			</div>
		</main>

		<!-- BARRA INFERIOR / FOOTER -->
		<footer
			class="bg-carpincho-panel border-carpincho-border flex shrink-0 items-center justify-between border-t px-4 py-2.5 shadow-lg"
		>
			<div class="text-xs text-stone-400">
				<span>Archivo destino:</span>
				<span class="font-mono text-stone-200">{{ editor.track.value.path || 'Sin ruta' }}.ass</span>
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
					:disabled="editor.isSaving.value"
					class="btn-save bg-carpincho-primary text-carpincho-bg flex items-center gap-2 rounded-xl px-5 py-2 text-xs font-bold shadow-md transition-all hover:brightness-110 active:scale-95 disabled:opacity-50"
					@click="editor.saveLyrics"
				>
					<i class="material-icons !text-base">save</i>
					<span>{{ editor.isSaving.value ? 'Guardando...' : 'Guardar letra personalizada' }}</span>
				</button>
			</div>
		</footer>

		<!-- MODALES -->
		<LyricsTokenModal
			:is-open="editor.isTokenModalOpen.value"
			:status-text="editor.tokenStatus.value.status_text"
			:hours-remaining="editor.tokenStatus.value.hours_remaining"
			:is-configured="editor.tokenStatus.value.is_configured"
			@save="
				(tok) => {
					editor.saveToken(tok);
					editor.isTokenModalOpen.value = false;
				}
			"
			@close="editor.isTokenModalOpen.value = false"
		/>

		<LyricsDiffModal
			:is-open="editor.isDiffModalOpen.value"
			:original-content="editor.originalContent.value"
			:new-content="editor.editorContent.value"
			@confirm="editor.confirmSave"
			@close="editor.isDiffModalOpen.value = false"
		/>
	</div>
</template>
