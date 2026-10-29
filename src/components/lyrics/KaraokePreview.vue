<script setup lang="ts">
	import { computed } from 'vue';
	import { parseAss, type LyricLine, type LyricSyllable } from '../../composables/useLyrics';

	const props = defineProps<{
		assContent: string;
		currentTime: number;
	}>();

	const emit = defineEmits<{
		(e: 'seek', time: number): void;
	}>();

	const parsedLines = computed<LyricLine[]>(() => {
		if (!props.assContent) return [];
		return parseAss(props.assContent);
	});

	function isLineActive(line: LyricLine): boolean {
		const end = line.endTime ?? line.time + 3.0;
		return props.currentTime >= line.time && props.currentTime < end;
	}

	function getSyllableClass(syl: LyricSyllable): string {
		const t = props.currentTime;
		if (t >= syl.end) {
			return 'text-carpincho-warning font-bold';
		}
		if (t >= syl.start && t < syl.end) {
			return 'text-white font-black underline decoration-carpincho-warning drop-shadow-[0_0_8px_rgba(233,196,106,0.9)]';
		}
		return 'text-stone-400 opacity-60';
	}

	function formatDisplayTime(sec: number): string {
		const m = Math.floor(sec / 60);
		const s = Math.floor(sec % 60);
		const cs = Math.floor(Math.round((sec - Math.floor(sec)) * 100));
		return `${m}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
	}
</script>

<template>
	<div
		class="karaoke-preview-container flex h-full w-full flex-col overflow-y-auto rounded-xl border border-stone-800 bg-stone-900/60 p-4"
	>
		<div class="mb-3 flex items-center justify-between border-b border-stone-800 pb-2">
			<span class="text-xs font-semibold tracking-wider text-stone-400 uppercase">
				Vista Previa Sincronizada (Karaoke)
			</span>
			<span class="text-carpincho-warning font-mono text-xs">
				{{ formatDisplayTime(currentTime) }}
			</span>
		</div>

		<div
			v-if="parsedLines.length === 0"
			class="flex flex-1 items-center justify-center text-sm text-stone-500 italic"
		>
			Sin líneas de diálogo detectadas en el archivo ASS.
		</div>

		<div v-else class="flex flex-col gap-2">
			<div
				v-for="(line, idx) in parsedLines"
				:key="idx"
				:class="[
					'preview-line group flex cursor-pointer items-start gap-3 rounded-lg p-2.5 transition-all duration-150',
					isLineActive(line)
						? 'active-line bg-carpincho-warning/15 border-carpincho-warning border-l-4 shadow-md'
						: 'border-l-4 border-transparent opacity-75 hover:bg-stone-800/50 hover:opacity-100',
				]"
				@click="emit('seek', line.time)"
			>
				<span class="shrink-0 font-mono text-[0.7rem] text-stone-500 group-hover:text-stone-300">
					[{{ formatDisplayTime(line.time) }}]
				</span>

				<div class="flex-1 text-sm leading-relaxed">
					<template v-if="line.syllables && line.syllables.length > 0">
						<span v-for="(syl, sIdx) in line.syllables" :key="sIdx" :class="getSyllableClass(syl)">
							{{ syl.text }}
						</span>
					</template>
					<span v-else :class="isLineActive(line) ? 'text-carpincho-warning font-bold' : 'text-stone-300'">
						{{ line.text }}
					</span>
				</div>
			</div>
		</div>
	</div>
</template>
