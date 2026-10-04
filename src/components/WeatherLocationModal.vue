<script setup lang="ts">
	import { ref, watch, nextTick, onUnmounted } from 'vue';
	import type { Map as LeafletMap, Marker as LeafletMarker, LeafletMouseEvent } from 'leaflet';
	import { weatherLocation } from '../composables/player/state';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { useToasts } from '../composables/player/useToasts';
	import { apiUrl } from '../composables/useApi';
	import PillButton from './ui/PillButton.vue';

	const props = defineProps<{
		isOpen: boolean;
	}>();

	const emit = defineEmits<{
		(e: 'close'): void;
	}>();

	const { setWeatherLocation } = usePlaybackControls();
	const { showToast } = useToasts();

	const mapContainer = ref<HTMLDivElement | null>(null);
	const lat = ref<number>(-34.6037);
	const lng = ref<number>(-58.3816);
	const isLocating = ref<boolean>(false);
	const isPreviewing = ref<boolean>(false);
	const previewData = ref<{
		area_name?: string;
		temp_c?: number | null;
		phrase?: string;
	} | null>(null);

	let leafletMap: LeafletMap | null = null;
	let marker: LeafletMarker | null = null;

	const presets = [
		{ name: 'Bariloche', lat: -41.1335, lng: -71.3103 },
		{ name: 'Buenos Aires', lat: -34.6037, lng: -58.3816 },
		{ name: 'Córdoba', lat: -31.4201, lng: -64.1888 },
		{ name: 'Mendoza', lat: -32.8895, lng: -68.8458 },
		{ name: 'Rosario', lat: -32.9468, lng: -60.6393 },
		{ name: 'Salta', lat: -24.7821, lng: -65.4232 },
		{ name: 'Tucumán', lat: -26.8241, lng: -65.2226 },
		{ name: 'Ushuaia', lat: -54.8019, lng: -68.303 },
	];

	function parseLocationString(loc: string) {
		const trimmed = loc.trim();
		const coordMatch = trimmed.match(/^([-+]?\d+(\.\d+)?)\s*,\s*([-+]?\d+(\.\d+)?)$/);
		if (coordMatch) {
			lat.value = parseFloat(coordMatch[1]);
			lng.value = parseFloat(coordMatch[3]);
			return;
		}
		const preset = presets.find((p) => p.name.toLowerCase() === trimmed.toLowerCase());
		if (preset) {
			lat.value = preset.lat;
			lng.value = preset.lng;
		}
	}

	async function initMap() {
		if (!mapContainer.value) return;

		try {
			const [L] = await Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]);

			if (leafletMap) {
				leafletMap.remove();
				leafletMap = null;
			}

			leafletMap = L.map(mapContainer.value, {
				center: [lat.value, lng.value],
				zoom: 11,
				attributionControl: false,
			});

			L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
				maxZoom: 19,
			}).addTo(leafletMap);

			const carpinchoIcon = L.divIcon({
				className: 'carpincho-marker',
				html: '<div style="font-size: 28px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5)); cursor: pointer;">🧉</div>',
				iconSize: [32, 32],
				iconAnchor: [16, 16],
			});

			marker = L.marker([lat.value, lng.value], {
				draggable: true,
				icon: carpinchoIcon,
			}).addTo(leafletMap);

			const activeMarker = marker;
			activeMarker.on('dragend', () => {
				const pos = activeMarker.getLatLng();
				lat.value = parseFloat(pos.lat.toFixed(4));
				lng.value = parseFloat(pos.lng.toFixed(4));
			});

			leafletMap.on('click', (e: LeafletMouseEvent) => {
				lat.value = parseFloat(e.latlng.lat.toFixed(4));
				lng.value = parseFloat(e.latlng.lng.toFixed(4));
				if (marker) {
					marker.setLatLng([lat.value, lng.value]);
				}
			});

			setTimeout(() => {
				if (leafletMap) leafletMap.invalidateSize();
			}, 200);
		} catch (err) {
			console.warn('Leaflet initialization skipped or failed:', err);
		}
	}

	function updateMarkerPosition() {
		if (marker && leafletMap) {
			marker.setLatLng([lat.value, lng.value]);
			leafletMap.setView([lat.value, lng.value], leafletMap.getZoom() || 11);
		}
	}

	function selectPreset(preset: (typeof presets)[0]) {
		lat.value = preset.lat;
		lng.value = preset.lng;
		updateMarkerPosition();
	}

	function detectLocation() {
		if (!navigator.geolocation) {
			showToast('Tu navegador no soporta geolocalización, fiera.', 'error');
			return;
		}
		isLocating.value = true;
		navigator.geolocation.getCurrentPosition(
			(pos) => {
				isLocating.value = false;
				lat.value = parseFloat(pos.coords.latitude.toFixed(4));
				lng.value = parseFloat(pos.coords.longitude.toFixed(4));
				updateMarkerPosition();
			},
			(err) => {
				isLocating.value = false;
				console.error(err);
				showToast('No pudimos acceder a tu ubicación, revisá los permisos.', 'error');
			},
			{ enableHighAccuracy: true, timeout: 10000 }
		);
	}

	async function testWeatherPreview() {
		const coords = `${lat.value},${lng.value}`;
		isPreviewing.value = true;
		previewData.value = null;
		try {
			const res = await fetch(apiUrl(`/api/weather/preview?location=${encodeURIComponent(coords)}`));
			const data = await res.json();
			if (data.ok) {
				previewData.value = {
					area_name: data.area_name,
					temp_c: data.temp_c,
					phrase: data.phrase,
				};
			} else {
				showToast(data.error || 'No se pudo consultar el pronóstico.', 'error');
			}
		} catch (err) {
			console.error(err);
			showToast('Fallo al conectar con el servidor de clima.', 'error');
		} finally {
			isPreviewing.value = false;
		}
	}

	async function saveLocation() {
		const coords = `${lat.value},${lng.value}`;
		await setWeatherLocation(coords);
		emit('close');
	}

	watch(
		() => props.isOpen,
		(open) => {
			if (open) {
				parseLocationString(weatherLocation.value);
				previewData.value = null;
				nextTick(() => {
					initMap();
				});
			} else if (leafletMap) {
				leafletMap.remove();
				leafletMap = null;
				marker = null;
			}
		}
	);

	onUnmounted(() => {
		if (leafletMap) {
			leafletMap.remove();
			leafletMap = null;
		}
	});
</script>

<template>
	<div
		v-if="isOpen"
		class="fixed inset-0 z-90 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
		role="dialog"
		aria-modal="true"
		aria-labelledby="weather-modal-title"
		@click.self="emit('close')"
	>
		<div
			class="border-carpincho-border bg-carpincho-panel text-carpincho-text relative flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border shadow-2xl"
		>
			<!-- Encabezado -->
			<div class="border-carpincho-border flex items-center justify-between border-b px-6 py-4">
				<div class="flex items-center gap-2">
					<i class="material-icons text-carpincho-warning text-2xl">wb_sunny</i>
					<h3 id="weather-modal-title" class="text-carpincho-secondary text-lg font-bold">
						Ubicación del clima radial
					</h3>
				</div>
				<button
					class="text-carpincho-muted hover:bg-carpincho-bg hover:text-carpincho-warning cursor-pointer rounded-lg p-1.5 transition"
					aria-label="Cerrar modal"
					@click="emit('close')"
				>
					<i class="material-icons text-xl">close</i>
				</button>
			</div>

			<!-- Cuerpo -->
			<div class="flex-1 space-y-4 overflow-y-auto p-6">
				<p class="text-carpincho-muted text-xs">
					Hacé click en el mapa, arrastrá el carpincho 🧉 o usá la detección automática.
				</p>

				<!-- Contenedor del mapa -->
				<div
					ref="mapContainer"
					class="border-carpincho-border bg-carpincho-bg relative h-64 w-full overflow-hidden rounded-xl border shadow-inner"
				></div>

				<!-- Coordenadas y geolocalización -->
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div class="flex items-center gap-2 text-sm">
						<label class="text-carpincho-muted text-xs font-semibold">Coords:</label>
						<input
							v-model.number="lat"
							type="number"
							step="0.0001"
							placeholder="Latitud"
							class="focus:border-carpincho-warning border-carpincho-border bg-carpincho-bg text-carpincho-text w-28 rounded-lg border px-2 py-1 text-xs focus:outline-none"
							@change="updateMarkerPosition"
						/>
						<input
							v-model.number="lng"
							type="number"
							step="0.0001"
							placeholder="Longitud"
							class="focus:border-carpincho-warning border-carpincho-border bg-carpincho-bg text-carpincho-text w-28 rounded-lg border px-2 py-1 text-xs focus:outline-none"
							@change="updateMarkerPosition"
						/>
					</div>

					<button
						type="button"
						:disabled="isLocating"
						class="text-carpincho-warning border-carpincho-border bg-carpincho-bg hover:border-carpincho-warning hover:bg-carpincho-panel flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition hover:text-white disabled:opacity-50"
						@click="detectLocation"
					>
						<i class="material-icons text-sm" :class="{ 'animate-spin': isLocating }">my_location</i>
						{{ isLocating ? 'Buscando...' : 'Detectar mi ubicación' }}
					</button>
				</div>

				<!-- Ciudades sugeridas -->
				<div>
					<span class="text-carpincho-muted mb-1.5 block text-xs font-semibold">Ciudades sugeridas:</span>
					<div class="flex flex-wrap gap-1.5">
						<button
							v-for="preset in presets"
							:key="preset.name"
							type="button"
							class="hover:border-carpincho-warning border-carpincho-border bg-carpincho-bg text-carpincho-muted hover:text-carpincho-text cursor-pointer rounded-full border px-2.5 py-1 text-xs transition"
							@click="selectPreset(preset)"
						>
							{{ preset.name }}
						</button>
					</div>
				</div>

				<!-- Cuadro de vista previa -->
				<div
					v-if="previewData"
					class="border-carpincho-border bg-carpincho-bg/80 rounded-xl border p-3.5 text-sm"
				>
					<div class="border-carpincho-border/60 flex items-center justify-between border-b pb-2">
						<span class="text-carpincho-warning font-bold">📍 {{ previewData.area_name }}</span>
						<span v-if="previewData.temp_c !== null" class="text-carpincho-text font-bold">
							{{ previewData.temp_c }}°C
						</span>
					</div>
					<p class="text-carpincho-muted mt-2 text-xs italic">"{{ previewData.phrase }}"</p>
				</div>
			</div>

			<!-- Pie de modal -->
			<div class="border-carpincho-border flex items-center justify-between border-t px-6 py-4">
				<PillButton
					icon="sync"
					color-class="bg-gray-700 hover:bg-gray-600 text-carpincho-text"
					:disabled="isPreviewing"
					@click="testWeatherPreview"
				>
					{{ isPreviewing ? 'Consultando...' : 'Probar reporte' }}
				</PillButton>

				<div class="flex items-center gap-2">
					<button
						type="button"
						class="text-carpincho-muted hover:bg-carpincho-bg hover:text-carpincho-text cursor-pointer rounded-full px-4 py-2 text-xs font-medium transition"
						@click="emit('close')"
					>
						Cancelar
					</button>
					<PillButton
						icon="check"
						color-class="bg-carpincho-success hover:bg-green-700"
						@click="saveLocation"
					>
						Guardar ubicación
					</PillButton>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
	:deep(.leaflet-bar) {
		border: 1px solid var(--color-carpincho-border) !important;
		border-radius: 8px !important;
		overflow: hidden;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important;
	}

	:deep(.leaflet-bar a) {
		background-color: var(--color-carpincho-panel) !important;
		color: var(--color-carpincho-text) !important;
		border-bottom: 1px solid var(--color-carpincho-border) !important;
		transition:
			background-color 0.15s,
			color 0.15s;
	}

	:deep(.leaflet-bar a:hover) {
		background-color: var(--color-carpincho-bg) !important;
		color: var(--color-carpincho-warning) !important;
	}

	:deep(.leaflet-container) {
		background-color: var(--color-carpincho-bg) !important;
		font-family: inherit !important;
	}

	:deep(.leaflet-tile-pane) {
		filter: brightness(0.8) invert(1) contrast(1.2) hue-rotate(200deg) saturate(0.4);
	}
</style>
