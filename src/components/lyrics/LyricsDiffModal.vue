<script lang="ts">
	export interface DiffLine {
		type: 'same' | 'add' | 'delete';
		text: string;
	}

	/**
	 * Calcula el diff línea por línea entre el archivo original y el modificado usando LCS.
	 */
	export function computeLineDiff(original: string, modified: string): DiffLine[] {
		const a = original.split(/\r?\n/);
		const b = modified.split(/\r?\n/);

		const n = a.length;
		const m = b.length;

		// Matriz de programación dinámica para LCS
		const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));

		for (let i = 1; i <= n; i++) {
			for (let j = 1; j <= m; j++) {
				if (a[i - 1] === b[j - 1]) {
					dp[i][j] = dp[i - 1][j - 1] + 1;
				} else {
					dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
				}
			}
		}

		// Reconstrucción del diff desde el final
		const diff: DiffLine[] = [];
		let i = n;
		let j = m;

		while (i > 0 || j > 0) {
			if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
				diff.push({ type: 'same', text: a[i - 1] });
				i--;
				j--;
			} else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
				diff.push({ type: 'add', text: b[j - 1] });
				j--;
			} else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
				diff.push({ type: 'delete', text: a[i - 1] });
				i--;
			}
		}

		return diff.reverse();
	}
</script>

<script setup lang="ts">
	import { computed } from 'vue';

	const props = defineProps<{
		isOpen: boolean;
		originalContent: string;
		newContent: string;
	}>();

	const emit = defineEmits<{
		(e: 'confirm'): void;
		(e: 'close'): void;
	}>();

	const diffLines = computed(() => {
		if (!props.isOpen) return [];
		return computeLineDiff(props.originalContent, props.newContent);
	});

	const changesSummary = computed(() => {
		const added = diffLines.value.filter((d) => d.type === 'add').length;
		const deleted = diffLines.value.filter((d) => d.type === 'delete').length;
		return { added, deleted };
	});
</script>

<template>
	<div
		v-if="isOpen"
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
		@click.self="emit('close')"
	>
		<div
			class="bg-carpincho-panel border-carpincho-border flex h-[85vh] w-full max-w-4xl flex-col rounded-2xl border p-6 shadow-2xl"
		>
			<!-- Encabezado del modal -->
			<div class="mb-4 flex items-center justify-between border-b border-stone-800 pb-3">
				<div>
					<div class="flex items-center gap-2">
						<i class="material-icons text-carpincho-warning">difference</i>
						<h3 class="text-lg font-bold text-stone-100">Diferencias antes de sobrescribir</h3>
					</div>
					<p class="mt-1 text-xs text-stone-400">
						Ya existe un archivo en disco. Revisá los cambios antes de reemplazarlo con tu versión
						personalizada:
						<span class="ml-1 font-bold text-emerald-400">+{{ changesSummary.added }}</span>
						<span class="ml-1 font-bold text-red-400">-{{ changesSummary.deleted }}</span>
					</p>
				</div>
				<button type="button" class="text-stone-400 hover:text-stone-100" @click="emit('close')">
					<i class="material-icons">close</i>
				</button>
			</div>

			<!-- Visualizador de diff -->
			<div
				class="flex-1 overflow-auto rounded-xl border border-stone-800 bg-stone-950 font-mono text-xs leading-5"
			>
				<div
					v-for="(line, idx) in diffLines"
					:key="idx"
					:class="[
						'flex items-start gap-2 px-3 py-0.5 whitespace-pre',
						line.type === 'add' ? 'bg-emerald-950/40 text-emerald-300' : '',
						line.type === 'delete' ? 'bg-red-950/40 text-red-300 line-through opacity-75' : '',
						line.type === 'same' ? 'text-stone-400 opacity-60' : '',
					]"
				>
					<span class="w-4 shrink-0 text-center font-bold select-none">
						{{ line.type === 'add' ? '+' : line.type === 'delete' ? '-' : ' ' }}
					</span>
					<span class="flex-1 overflow-hidden">{{ line.text || ' ' }}</span>
				</div>
			</div>

			<!-- Acciones -->
			<div class="mt-4 flex items-center justify-end gap-3 border-t border-stone-800 pt-3">
				<button
					type="button"
					class="rounded-xl px-4 py-2 text-xs font-semibold text-stone-400 hover:bg-stone-800"
					@click="emit('close')"
				>
					Cancelar
				</button>
				<button
					type="button"
					class="bg-carpincho-primary text-carpincho-bg flex items-center gap-1.5 rounded-xl px-5 py-2 text-xs font-bold shadow-md transition-all hover:brightness-110"
					@click="emit('confirm')"
				>
					<i class="material-icons !text-base">save</i>
					Confirmar guardado
				</button>
			</div>
		</div>
	</div>
</template>
