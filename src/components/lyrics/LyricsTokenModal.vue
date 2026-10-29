<script lang="ts">
	/**
	 * Extrae token JWT desde texto crudo, comandos cURL o cadenas con token=...
	 */
	export function extractJwtToken(raw: string): string {
		const text = raw.trim();
		if (!text) return '';

		// 1. Busca token= en query strings o form data
		const queryMatch = text.match(/token=([a-zA-Z0-9_.-]+)/);
		if (queryMatch) return queryMatch[1];

		// 2. Coincidencia directa con estructura JWT (eyJ...)
		const jwtMatch = text.match(/(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)/);
		if (jwtMatch) return jwtMatch[1];

		// 3. Fallback si el usuario pegó el token empezando por eyJ
		if (text.startsWith('eyJ')) return text;

		return text;
	}
</script>

<script setup lang="ts">
	import { ref, watch } from 'vue';

	const props = defineProps<{
		isOpen: boolean;
		statusText: string;
		hoursRemaining: number;
		isConfigured: boolean;
	}>();

	const emit = defineEmits<{
		(e: 'save', token: string): void;
		(e: 'close'): void;
	}>();

	const tokenInput = ref('');

	watch(
		() => props.isOpen,
		(open) => {
			if (open) tokenInput.value = '';
		}
	);

	function handleSave() {
		const extracted = extractJwtToken(tokenInput.value);
		if (extracted) {
			emit('save', extracted);
		}
	}
</script>

<template>
	<div
		v-if="isOpen"
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
		@click.self="emit('close')"
	>
		<div
			class="bg-carpincho-panel border-carpincho-border flex w-full max-w-lg flex-col rounded-2xl border p-6 shadow-2xl"
		>
			<div class="mb-4 flex items-center justify-between border-b border-stone-800 pb-3">
				<div class="flex items-center gap-2">
					<i class="material-icons text-carpincho-warning">vpn_key</i>
					<h3 class="text-lg font-bold text-stone-100">Token de BetterLyrics</h3>
				</div>
				<button type="button" class="text-stone-400 hover:text-stone-100" @click="emit('close')">
					<i class="material-icons">close</i>
				</button>
			</div>

			<div class="mb-5 flex flex-col gap-2 rounded-xl bg-stone-900/70 p-3.5 text-xs text-stone-300">
				<div class="flex items-center justify-between">
					<span class="font-semibold text-stone-400">Estado actual:</span>
					<span
						:class="[
							'rounded px-2 py-0.5 font-bold',
							isConfigured ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300',
						]"
					>
						{{ isConfigured ? 'Configurado' : 'Sin configurar' }}
					</span>
				</div>
				<p class="text-stone-400">
					{{ statusText || 'Pegá tu token de BetterLyrics para búsquedas sincronizadas.' }}
				</p>
				<p v-if="hoursRemaining > 0" class="text-carpincho-warning font-medium">
					⏳ Horas restantes estimadas: {{ hoursRemaining }}h
				</p>
			</div>

			<div class="mb-6 flex flex-col gap-2">
				<label class="text-xs font-semibold text-stone-300">Pegar Token JWT o comando cURL:</label>
				<input
					v-model="tokenInput"
					type="text"
					placeholder="eyJhbGciOiJIUzI1Ni... o pegá el curl completo"
					class="border-carpincho-border focus:border-carpincho-warning focus:ring-carpincho-warning/20 w-full rounded-xl border bg-stone-900 px-3.5 py-2.5 font-mono text-xs text-stone-100 focus:ring-2 focus:outline-none"
					@keydown.enter="handleSave"
				/>
				<span class="text-[0.7rem] text-stone-500">
					La Rockola extrae automáticamente el JWT del comando curl si lo pegás entero.
				</span>
			</div>

			<div class="flex items-center justify-end gap-3">
				<button
					type="button"
					class="rounded-xl px-4 py-2 text-xs font-semibold text-stone-400 hover:bg-stone-800"
					@click="emit('close')"
				>
					Cancelar
				</button>
				<button
					type="button"
					class="bg-carpincho-primary text-carpincho-bg flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold transition-all hover:brightness-110"
					@click="handleSave"
				>
					<i class="material-icons !text-base">check</i>
					Guardar token
				</button>
			</div>
		</div>
	</div>
</template>
