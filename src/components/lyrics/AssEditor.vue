<script lang="ts">
	/**
	 * Función pura para colorear la sintaxis de una línea de archivo ASS.
	 * Resalta encabezados de sección, comandos Dialogue, marcas de tiempo y etiquetas de karaoke.
	 */
	export function highlightAssLine(rawLine: string): string {
		// 1. Escapamos entidades HTML básicas para evitar inyecciones
		let escaped = rawLine
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');

		// Comentarios de ASS que inician con punto y coma
		if (escaped.trim().startsWith(';')) {
			return `<span class="text-gray-400 italic">${escaped}</span>`;
		}

		// Encabezados de sección entre corchetes ([Script Info], [V4+ Styles], [Events])
		if (/^\[[^\]]+\]/.test(escaped.trim())) {
			return escaped.replace(/^(\[[^\]]+\])/, '<span class="text-carpincho-warning font-bold">$1</span>');
		}

		// Comandos de línea ASS (Dialogue, Comment, Format, Style)
		escaped = escaped.replace(
			/\b(Dialogue|Comment|Format|Style):/g,
			'<span class="text-sky-400 font-semibold">$1:</span>'
		);

		// Marcas de tiempo (h:mm:ss.cs)
		escaped = escaped.replace(/\b(\d+:\d{2}:\d{2}\.\d{2})\b/g, '<span class="text-amber-300 font-mono">$1</span>');

		// Etiquetas de karaoke de sílaba (\kf, \ko, \k)
		escaped = escaped.replace(
			/(\{\\k[f|o]?\d+\})/gi,
			'<span class="text-emerald-400 font-mono font-bold">$1</span>'
		);

		// Otras etiquetas y modificadores de estilo entre llaves
		escaped = escaped.replace(/(\{[^}]+\})/g, (match) => {
			if (match.includes('text-emerald-400')) return match;
			return `<span class="text-pink-400 font-mono">${match}</span>`;
		});

		return escaped || '&nbsp;';
	}
</script>

<script setup lang="ts">
	import { computed, ref } from 'vue';

	const props = defineProps<{
		modelValue: string;
	}>();

	const emit = defineEmits<{
		(e: 'update:modelValue', value: string): void;
	}>();

	const textareaRef = ref<HTMLTextAreaElement | null>(null);
	const preRef = ref<HTMLPreElement | null>(null);
	const gutterRef = ref<HTMLDivElement | null>(null);

	const lines = computed(() => {
		return props.modelValue.split(/\r?\n/);
	});

	const highlightedHtml = computed(() => {
		return lines.value.map((l) => highlightAssLine(l)).join('\n');
	});

	function onInput(e: Event) {
		const target = e.target as HTMLTextAreaElement;
		emit('update:modelValue', target.value);
	}

	function onScroll() {
		if (!textareaRef.value) return;
		const top = textareaRef.value.scrollTop;
		const left = textareaRef.value.scrollLeft;

		if (preRef.value) {
			preRef.value.scrollTop = top;
			preRef.value.scrollLeft = left;
		}
		if (gutterRef.value) {
			gutterRef.value.scrollTop = top;
		}
	}
</script>

<template>
	<!-- eslint-disable vue/no-v-html -->
	<div
		class="ass-editor-container bg-carpincho-bg relative flex h-full w-full overflow-hidden rounded-xl border border-stone-800 font-mono text-xs sm:text-sm"
	>
		<!-- Canaleta con numeración de líneas -->
		<div
			ref="gutterRef"
			class="line-gutter text-carpincho-muted z-10 w-12 shrink-0 overflow-hidden border-r border-stone-800 bg-stone-900/80 px-2 py-3 text-right select-none"
		>
			<div v-for="(_, index) in lines" :key="index" class="line-number h-6 text-[0.75rem] leading-6 opacity-60">
				{{ index + 1 }}
			</div>
		</div>

		<!-- Área de código editable con resaltado de sintaxis subyacente -->
		<div class="relative h-full min-w-0 flex-1 overflow-hidden">
			<!-- Capa coloreada (Background) -->
			<!-- eslint-disable-next-line vue/no-v-html -->
			<pre
				ref="preRef"
				aria-hidden="true"
				class="highlight-layer pointer-events-none absolute inset-0 z-0 m-0 overflow-hidden px-4 py-3 font-mono leading-6 whitespace-pre text-stone-200"
				v-html="highlightedHtml + '\n'"
			/>

			<!-- Capa editable de texto transparente (Foreground) -->
			<textarea
				ref="textareaRef"
				:value="modelValue"
				spellcheck="false"
				class="editor-textarea caret-carpincho-warning selection:bg-carpincho-warning/30 absolute inset-0 z-1 m-0 h-full w-full resize-none overflow-auto bg-transparent px-4 py-3 font-mono leading-6 whitespace-pre text-transparent selection:text-white focus:outline-none"
				@input="onInput"
				@scroll="onScroll"
			/>
		</div>
	</div>
</template>

<style scoped>
	.editor-textarea {
		-webkit-text-fill-color: transparent;
	}
</style>
