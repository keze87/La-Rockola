<script setup>
	import { usePlayer } from '../composables/usePlayer';
	import { useContextMenuBindings } from '../composables/useContextMenu';
	import CoverImage from './ui/CoverImage.vue';

	const { topPlayedState, getTrackInfo, toggleQueue } = usePlayer();
</script>

<template>
	<section class="tab-content bg-carpincho-bg h-full overflow-y-auto px-4 pt-4">
		<ul v-if="topPlayedState.length > 0" class="flex flex-col">
			<li
				v-for="(t, i) in topPlayedState"
				:key="t.path"
				class="border-carpincho-border hover:bg-carpincho-panel flex cursor-pointer items-center rounded-lg border-b p-4 transition active:scale-[0.98]"
				@click="toggleQueue(t.path)"
				v-on="useContextMenuBindings(() => getTrackInfo(t.path), 'library')"
			>
				<div class="text-carpincho-warning mr-4 w-8 text-center text-xl font-bold">#{{ i + 1 }}</div>

				<CoverImage :path="t.path" size="h-12 w-12" rounded="rounded-md" class="mr-4" icon-size="!text-4xl" />

				<div class="flex-grow overflow-hidden">
					<div class="text-carpincho-text truncate font-bold">
						{{ getTrackInfo(t.path).display_title }}
					</div>
					<div class="text-carpincho-muted truncate text-sm">
						{{ getTrackInfo(t.path).display_artist }} • Sonó {{ t.count }} veces
					</div>
				</div>
				<i class="material-icons text-carpincho-primary ml-2 shrink-0">playlist_add</i>
			</li>
		</ul>
		<div v-else class="text-carpincho-primary p-8 text-center font-medium">Todavía no sonó nada, maestro.</div>
	</section>
</template>
