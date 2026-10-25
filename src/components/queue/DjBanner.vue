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
		:class="['border-carpincho-border bg-carpincho-panel/50 items-center border-b', trackGridClass]"
	>
		<div class="flex justify-center p-4">
			<i class="material-icons text-carpincho-warning" :class="{ 'animate-pulse': queueLength === 0 }">
				auto_awesome
			</i>
		</div>

		<div class="text-carpincho-muted p-4 italic">
			{{
				queueLength === 0
					? djNextTrack
						? 'DJ Bara eligió: ' + (djNextTrack.display_title || djNextTrack.title)
						: 'Eligiendo...'
					: 'Al vaciarse la fila, entra el DJ Bara'
			}}
		</div>

		<div class="text-carpincho-muted p-4 italic">
			{{ queueLength === 0 && djNextTrack ? djNextTrack.display_artist || djNextTrack.artist : '' }}
		</div>

		<div class="hidden p-4 text-right sm:block">🦦</div>
	</div>
</template>
