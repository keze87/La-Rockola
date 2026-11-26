import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { useQueueDragDrop } from '@/composables/player/useQueueDragDrop';
import { favorites, queueState } from '@/composables/player/state';
import { useLibrary } from '@/composables/player/useLibrary';
import { favoritesSet } from '@/stores/useLibraryStore';

describe('Rendimiento de cola con 100+ temas', () => {
	beforeEach(() => {
		queueState.value = [];
		favorites.value = [];
	});

	it('mantiene estables los id de unifiedQueue cuando se quita el primer tema de una cola de 100', () => {
		const h = ref<string[]>([]);
		const current = ref<string | null>('/music/0.mp3');
		const q = ref<string[]>(Array.from({ length: 100 }, (_, i) => `/music/song-${i + 1}.mp3`));

		const { unifiedQueue } = useQueueDragDrop({
			historyState: h,
			currentTrackPath: current,
			queueState: q,
			getTrackInfo: (path) => ({ path, display_title: path, display_artist: 'Artista' }),
			haptic: vi.fn(),
			openCtxMenu: vi.fn(),
			moveInPlaylist: vi.fn(),
			moveQueueItem: vi.fn(),
			removeQueueItemCmd: vi.fn(),
			addHistoryToQueueCmd: vi.fn(),
			removeHistoryItemCmd: vi.fn(),
		});

		const idsBefore = unifiedQueue.value.filter((x) => x.status === 'queue').map((x) => x.id);
		expect(idsBefore).toHaveLength(100);

		// Avanza al siguiente tema (sale song-1 de la cola)
		q.value = q.value.slice(1);
		const idsAfter = unifiedQueue.value.filter((x) => x.status === 'queue').map((x) => x.id);

		expect(idsAfter).toHaveLength(99);
		expect(idsAfter).toEqual(idsBefore.slice(1));
	});

	it('asigna ids unicos cuando un mismo tema aparece repetido en la cola', () => {
		const h = ref<string[]>([]);
		const current = ref<string | null>(null);
		const q = ref<string[]>(['/music/bis.mp3', '/music/otro.mp3', '/music/bis.mp3']);

		const { unifiedQueue } = useQueueDragDrop({
			historyState: h,
			currentTrackPath: current,
			queueState: q,
			getTrackInfo: (path) => ({ path, display_title: path, display_artist: 'Artista' }),
			haptic: vi.fn(),
			openCtxMenu: vi.fn(),
			moveInPlaylist: vi.fn(),
			moveQueueItem: vi.fn(),
			removeQueueItemCmd: vi.fn(),
			addHistoryToQueueCmd: vi.fn(),
			removeHistoryItemCmd: vi.fn(),
		});

		const ids = unifiedQueue.value.map((x) => x.id);
		expect(new Set(ids).size).toBe(3);
	});

	it('expone favoritesSet en O(1) y queueIndex consistente con primer ocurrencia', () => {
		favorites.value = ['/music/fav1.mp3', '/music/fav2.mp3'];
		expect(favoritesSet.value.has('/music/fav2.mp3')).toBe(true);
		expect(favoritesSet.value.has('/music/no.mp3')).toBe(false);

		queueState.value = ['/music/a.mp3', '/music/b.mp3', '/music/a.mp3'];
		const { queueIndex } = useLibrary();
		expect(queueIndex('/music/a.mp3')).toBe(0);
		expect(queueIndex('/music/b.mp3')).toBe(1);
		expect(queueIndex('/music/z.mp3')).toBe(-1);
	});
});
