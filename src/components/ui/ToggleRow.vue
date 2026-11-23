<script setup lang="ts">
	import { Switch } from '@headlessui/vue';

	withDefaults(
		defineProps<{
			modelValue: boolean;
			icon?: string | null;
			title?: string;
			description?: string;
			activeClass?: string;
		}>(),
		{
			icon: null,
			title: '',
			description: '',
			activeClass: 'bg-[var(--accent-mate)]',
		}
	);

	defineEmits<{
		(e: 'update:modelValue', value: boolean): void;
	}>();
</script>

<template>
	<div
		class="flex w-full items-center justify-between px-4 py-3.5 transition-colors hover:bg-[var(--bg-surface-hover)]"
	>
		<div class="min-w-0 flex-1 pr-3 text-left">
			<div class="flex items-center gap-2.5 text-[15px] font-semibold text-[var(--text-primary)]">
				<i v-if="icon" class="material-icons !text-[20px] text-[var(--accent-primary)]" aria-hidden="true">
					{{ icon }}
				</i>
				<span class="truncate">{{ title }}</span>
			</div>
			<div v-if="description" class="mt-0.5 text-[12px] leading-snug text-[var(--text-secondary)]">
				{{ description }}
			</div>
		</div>

		<Switch
			:model-value="modelValue"
			:class="[
				modelValue ? activeClass : 'bg-[rgba(255,236,210,0.16)]',
				'relative inline-flex h-[30px] w-[50px] shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 ease-in-out focus:outline-none',
			]"
			@update:model-value="$emit('update:modelValue', $event)"
		>
			<span
				aria-hidden="true"
				:class="[
					modelValue ? 'translate-x-[22px]' : 'translate-x-[2px]',
					'pointer-events-none inline-block h-[26px] w-[26px] transform rounded-full bg-[#faf6f0] shadow-[0_2px_6px_rgba(0,0,0,0.35)] ring-0 transition-transform duration-200 ease-in-out',
				]"
			/>
		</Switch>
	</div>
</template>
