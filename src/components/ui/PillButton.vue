<script setup lang="ts">
	withDefaults(
		defineProps<{
			icon?: string | null;
			colorClass?: string;
			disabled?: boolean;
			title?: string;
		}>(),
		{
			icon: null,
			colorClass:
				'bg-[var(--bg-input)] hover:bg-[var(--bg-surface-hover)] border border-[var(--hairline)] text-[var(--text-primary)]',
			disabled: false,
			title: undefined,
		}
	);
	defineEmits<{
		(e: 'click'): void;
	}>();
</script>

<template>
	<button
		:disabled="disabled"
		:title="title"
		class="tap-feedback flex items-center gap-2 rounded-[var(--radius-md)] px-4 py-2.5 text-sm font-semibold disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
		:class="colorClass"
		@click="!disabled && $emit('click')"
	>
		<i v-if="icon" class="material-icons" :class="{ 'animate-spin': disabled && icon === 'refresh' }">{{ icon }}</i>
		<slot />
	</button>
</template>
