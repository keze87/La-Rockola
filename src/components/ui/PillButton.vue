<script setup>
	defineProps({
		icon: { type: String, default: null },
		colorClass: { type: String, default: 'bg-gray-800 hover:bg-gray-700' },
	});
	defineEmits(['click']);
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
