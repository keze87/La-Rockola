<script setup>
	import { Switch } from '@headlessui/vue';

	defineProps({
		modelValue: Boolean,
		icon: { type: String, default: null },
		title: { type: String, default: '' },
		description: { type: String, default: '' },
		activeClass: { type: String, default: 'bg-carpincho-warning' },
	});
	defineEmits(['update:modelValue']);
</script>

<template>
	<div
		class="bg-carpincho-panel border-carpincho-warning mx-auto mb-8 flex w-full max-w-lg items-center justify-between rounded-xl border-l-4 p-4 shadow-md transition-all"
	>
		<div class="text-left">
			<div class="text-carpincho-text flex items-center gap-2 font-bold">
				<i class="material-icons text-carpincho-warning">{{ icon }}</i>
				{{ title }}
			</div>
			<div class="text-carpincho-muted text-xs">{{ description }}</div>
		</div>

		<Switch
			:model-value="modelValue"
			:class="[
				modelValue ? activeClass : 'bg-gray-700',
				'relative ml-4 inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none',
			]"
			@update:model-value="$emit('update:modelValue', $event)"
		>
			<span
				aria-hidden="true"
				:class="[
					modelValue ? 'translate-x-5' : 'translate-x-0',
					'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
				]"
			/>
		</Switch>
	</div>
</template>
