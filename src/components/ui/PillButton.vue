<script setup lang="ts">
	withDefaults(
		defineProps<{
			icon?: string | null;
			colorClass?: string;
		}>(),
		{
			icon: null,
			colorClass: 'bg-gray-800 hover:bg-gray-700',
		}
	);
	defineEmits<{
		(e: 'click'): void;
	}>();
</script>

<template>
	<button
		class="flex items-center gap-2 rounded-full px-5 py-2 font-medium text-white transition active:scale-95"
		:class="colorClass"
		@click="$emit('click')"
	>
		<i v-if="icon" class="material-icons">{{ icon }}</i>
		<slot />
	</button>
</template>
