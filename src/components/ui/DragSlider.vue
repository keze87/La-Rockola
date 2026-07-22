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
			activeColor: 'bg-carpincho-warning',
			trackColor: 'bg-gray-600/50',
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
		<div class="pointer-events-none relative h-1.5 w-full rounded-full" :class="trackColor">
			<div
				class="absolute top-0 left-0 h-full rounded-full"
				:class="activeColor"
				:style="{ width: progressPercent + '%' }"
			/>

			<div
				class="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full shadow transition-transform group-active:scale-125"
				:class="activeColor"
				:style="{ left: progressPercent + '%', marginLeft: '-8px' }"
			/>
		</div>
	</div>
</template>
