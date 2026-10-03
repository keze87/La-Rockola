<script setup lang="ts">
	import { ref, watch, nextTick, onUnmounted } from 'vue';
	import type { Map as LeafletMap, Marker as LeafletMarker, LeafletMouseEvent } from 'leaflet';
	import { weatherLocation } from '../composables/player/state';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { useToasts } from '../composables/player/useToasts';
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
		{ name: 'Buenos Aires', lat: -34.6037, lng: -58.3816 },
		{ name: 'Córdoba', lat: -31.4201, lng: -64.1888 },
		{ name: 'Rosario', lat: -32.9468, lng: -60.6393 },
		{ name: 'Tucumán', lat: -26.8241, lng: -65.2226 },
		{ name: 'Mendoza', lat: -32.8895, lng: -68.8458 },
		{ name: 'Mar del Plata', lat: -38.0055, lng: -57.5562 },
		{ name: 'Bariloche', lat: -41.1335, lng: -71.3103 },
		{ name: 'Ushuaia', lat: -54.8019, lng: -68.303 },
		{ name: 'Montevideo', lat: -34.9011, lng: -56.1645 },
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
				showToast('¡Ubicación detectada al toque!', 'success');
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
			const res = await fetch(`/api/weather/preview?location=${encodeURIComponent(coords)}`);
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
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
		role="dialog"
		aria-modal="true"
		aria-labelledby="weather-modal-title"
		@click.self="emit('close')"
	>
		<div
			class="relative flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-neutral-700 bg-neutral-900 shadow-2xl"
		>
			<!-- Header -->
			<div class="flex items-center justify-between border-b border-neutral-800 px-6 py-4">
				<div class="flex items-center gap-2">
					<span class="text-2xl">🌤️</span>
					<h3 id="weather-modal-title" class="text-lg font-bold text-white">Ubicación del clima radial</h3>
				</div>
				<button
					class="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-white"
					aria-label="Cerrar modal"
					@click="emit('close')"
				>
					<span class="material-symbols-outlined text-xl">close</span>
				</button>
			</div>

			<!-- Body -->
			<div class="flex-1 space-y-4 overflow-y-auto p-6">
				<p class="text-xs text-neutral-400">
					Hacé click en el mapa, arrastrá el carpincho 🧉 o usá la detección automática. El locutor mencionará
					el barrio o localidad más cercana con acento radial criollo.
				</p>

				<!-- Map container -->
				<div
					ref="mapContainer"
					class="relative h-64 w-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-950"
				></div>

				<!-- Coords & Geolocation -->
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div class="flex items-center gap-2 text-sm">
						<label class="text-xs font-semibold text-neutral-400">Coords:</label>
						<input
							v-model.number="lat"
							type="number"
							step="0.0001"
							placeholder="Latitud"
							class="focus:border-carpincho-success w-28 rounded-lg border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs text-white focus:outline-none"
							@change="updateMarkerPosition"
						/>
						<input
							v-model.number="lng"
							type="number"
							step="0.0001"
							placeholder="Longitud"
							class="focus:border-carpincho-success w-28 rounded-lg border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs text-white focus:outline-none"
							@change="updateMarkerPosition"
						/>
					</div>

					<button
						type="button"
						:disabled="isLocating"
						class="text-carpincho-accent flex items-center gap-1.5 rounded-lg bg-neutral-800 px-3 py-1.5 text-xs font-medium transition hover:bg-neutral-700 disabled:opacity-50"
						@click="detectLocation"
					>
						<span class="material-symbols-outlined text-sm">my_location</span>
						{{ isLocating ? 'Buscando...' : 'Detectar mi ubicación' }}
					</button>
				</div>

				<!-- City Presets -->
				<div>
					<span class="mb-1.5 block text-xs font-semibold text-neutral-400">Ciudades sugeridas:</span>
					<div class="flex flex-wrap gap-1.5">
						<button
							v-for="preset in presets"
							:key="preset.name"
							type="button"
							class="hover:border-carpincho-accent rounded-full border border-neutral-700 bg-neutral-800/80 px-2.5 py-1 text-xs text-neutral-300 transition hover:text-white"
							@click="selectPreset(preset)"
						>
							{{ preset.name }}
						</button>
					</div>
				</div>

				<!-- Preview Box -->
				<div v-if="previewData" class="rounded-xl border border-neutral-700 bg-neutral-800/60 p-3.5 text-sm">
					<div class="flex items-center justify-between border-b border-neutral-700/60 pb-2">
						<span class="text-carpincho-accent font-bold">📍 {{ previewData.area_name }}</span>
						<span v-if="previewData.temp_c !== null" class="font-bold text-white">
							{{ previewData.temp_c }}°C
						</span>
					</div>
					<p class="mt-2 text-xs text-neutral-300 italic">"{{ previewData.phrase }}"</p>
				</div>
			</div>

			<!-- Footer -->
			<div class="flex items-center justify-between border-t border-neutral-800 px-6 py-4">
				<PillButton
					icon="sync"
					color-class="bg-neutral-800 hover:bg-neutral-700 text-neutral-200"
					:disabled="isPreviewing"
					@click="testWeatherPreview"
				>
					{{ isPreviewing ? 'Consultando...' : 'Probar reporte' }}
				</PillButton>

				<div class="flex items-center gap-2">
					<button
						type="button"
						class="rounded-xl px-4 py-2 text-xs font-medium text-neutral-400 transition hover:bg-neutral-800 hover:text-white"
						@click="emit('close')"
					>
						Cancelar
					</button>
					<PillButton
						icon="check"
						color-class="bg-carpincho-success hover:bg-green-600"
						@click="saveLocation"
					>
						Guardar ubicación
					</PillButton>
				</div>
			</div>
		</div>
	</div>
</template>
