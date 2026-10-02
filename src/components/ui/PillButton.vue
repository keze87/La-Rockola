<script setup lang="ts">
	withDefaults(
		defineProps<{
			icon?: string | null;
			colorClass?: string;
			disabled?: boolean;
		}>(),
		{
			icon: null,
			colorClass: 'bg-gray-800 hover:bg-gray-700',
			disabled: false,
		}
	);
	defineEmits<{
		(e: 'click'): void;
	}>();
</script>

<template>
	<button
		:disabled="disabled"
		class="flex items-center gap-2 rounded-full px-5 py-2 font-medium text-white transition active:scale-95 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
		:class="colorClass"
		@click="!disabled && $emit('click')"
	>
		<i v-if="icon" class="material-icons" :class="{ 'animate-spin': disabled && icon === 'refresh' }">{{ icon }}</i>
		<slot />
	</button>
</template>
