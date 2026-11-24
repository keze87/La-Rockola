<script setup lang="ts">
	import { useDragSlider } from '../../composables/useDragSlider';

	const props = withDefaults(
		defineProps<{
			modelValue: number;
			max?: number;
			activeColor?: string;
			trackColor?: string;
		}>(),
		{
			max: 100,
			activeColor: 'bg-[var(--accent-primary)]',
			trackColor: 'bg-[rgba(255,236,210,0.14)]',
		}
	);

	const emit = defineEmits<{
		(e: 'update:modelValue', value: number): void;
		(e: 'commit', value: number): void;
		(e: 'dragging', value: boolean): void;
	}>();

	const { progressPercent, startDrag, moveDrag, endDrag } = useDragSlider({
		max: () => props.max,
		getValue: () => props.modelValue,
		onUpdate: (val) => {
			emit('dragging', true);
			emit('update:modelValue', val);
		},
		onCommit: (val) => {
			emit('dragging', false);
			emit('commit', val);
		},
	});
</script>

<template>
	<div
		class="group flex h-10 w-full cursor-pointer touch-none items-center"
		@pointerdown="startDrag"
		@pointermove="moveDrag"
		@pointerup="endDrag"
		@pointercancel="endDrag"
	>
		<div
			class="pointer-events-none relative h-[6px] w-full overflow-visible rounded-full transition-[height] duration-150 group-active:h-[10px]"
			:class="trackColor"
		>
			<div
				class="absolute top-0 left-0 h-full rounded-full"
				:class="activeColor"
				:style="{ width: progressPercent + '%' }"
			/>

			<div
				class="absolute top-1/2 aspect-square h-4 w-4 shrink-0 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#EFE7DC] shadow-[0_2px_6px_rgba(0,0,0,0.45)] transition-transform group-active:scale-110"
				:style="{ left: progressPercent + '%' }"
			/>
		</div>
	</div>
</template>
