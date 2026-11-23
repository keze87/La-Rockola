<script setup lang="ts">
	import type { Track } from '../../types';

	defineProps<{
		djBaraEnabled: boolean;
		queueLength: number;
		djNextTrack: Track | null;
		trackGridClass: string;
	}>();
</script>

<template>
	<div
		v-if="djBaraEnabled"
		:class="[
			'mx-3 my-3 flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--bg-grouped)] px-4 py-3 min-[720px]:mx-0 min-[720px]:my-0 min-[720px]:rounded-none min-[720px]:border-x-0 min-[720px]:border-t-0 min-[720px]:px-0 min-[720px]:py-0',
			trackGridClass,
		]"
	>
		<div class="flex shrink-0 justify-center min-[720px]:p-4">
			<i
				class="material-icons !text-[20px] text-[var(--accent-primary)]"
				:class="{ 'animate-pulse': queueLength === 0 }"
			>
				auto_awesome
			</i>
		</div>

		<div class="min-w-0 flex-1 text-[14px] text-[var(--text-secondary)] italic min-[720px]:p-4">
			{{
				queueLength === 0
					? djNextTrack
						? 'DJ Bara eligió: ' + (djNextTrack.display_title || djNextTrack.title)
						: 'Eligiendo...'
					: 'Al vaciarse la fila, entra el DJ Bara'
			}}
		</div>

		<div class="hidden truncate text-[14px] text-[var(--text-secondary)] italic min-[720px]:block min-[720px]:p-4">
			{{ queueLength === 0 && djNextTrack ? djNextTrack.display_artist || djNextTrack.artist : '' }}
		</div>

		<div class="shrink-0 text-right min-[720px]:p-4">🦦</div>
	</div>
</template>
