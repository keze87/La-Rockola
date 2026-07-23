import { onKeyStroke } from '@vueuse/core';
import { useContextMenu } from './useContextMenu';
import { usePlaybackControls } from './usePlaybackControls';
import { usePlayer } from './usePlayer';

const { pause, setMute, skip, prev, seek } = usePlaybackControls();

export function useKeyboardShortcuts() {
	const player = usePlayer();
	const ctx = useContextMenu();

	const shouldIgnore = (e: KeyboardEvent) => {
		// Ignoramos si el usuario está escribiendo en un input de texto
		const el = e.target;

		return (
			el instanceof HTMLElement &&
			(el.closest('input, textarea, select, [contenteditable="true"], .ctx-menu') !== null ||
				el.isContentEditable) // , [role="menu"]
		);
	};

	onKeyStroke('Escape', (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		if (player.isFogonMode.value) {
			player.isFogonMode.value = false;
			player.haptic();
		}

		if (ctx.ctxMenu.visible) ctx.closeCtxMenu();

		if (player.showFogonVolume?.value) player.showFogonVolume.value = false;
	});

	onKeyStroke(' ', (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();
		pause();
		player.haptic(true);
	});

	onKeyStroke('ArrowRight', (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();

		if (e.shiftKey) {
			skip();
		} else {
			const amount = 10;
			player.localTimePos.value = Math.min(player.duration.value, player.localTimePos.value + amount);
			player.ignoreServerTimeUntil.value = Date.now() + 2000;
			seek(amount);
		}

		player.haptic();
	});

	onKeyStroke('ArrowLeft', (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();

		if (e.shiftKey) {
			prev();
		} else {
			const amount = -10;
			player.localTimePos.value = Math.max(0, player.localTimePos.value + amount);
			player.ignoreServerTimeUntil.value = Date.now() + 2000;
			seek(amount);
		}

		player.haptic();
	});

	onKeyStroke('ArrowUp', (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();
		player.volume.value = Math.min(110, Number(player.volume.value) + 5);
		player.setVolume();
		player.showToast({ prefix: 'Volumen: ', highlight: player.volume.value + '%' }, 'success');
	});

	onKeyStroke('ArrowDown', (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();
		player.volume.value = Math.max(0, Number(player.volume.value) - 5);
		player.setVolume();
		player.showToast({ prefix: 'Volumen: ', highlight: player.volume.value + '%' }, 'success');
	});

	onKeyStroke(['m', 'M'], (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		const isCurrentlyMuted = player.serverMuted.value;
		setMute(!isCurrentlyMuted);
		player.haptic();

		if (!isCurrentlyMuted) {
			player.showToast('Audio silenciado', 'error');
		} else {
			if (player.volume.value < 20) {
				player.volume.value = 20;
				player.setVolume();
			}

			player.showToast('Audio activado', 'success');
		}
	});

	onKeyStroke(['f', 'F'], (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		player.isFogonMode.value = !player.isFogonMode.value;
		player.haptic();
	});

	onKeyStroke(['l', 'L'], (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		const currentPath = player.currentTrackPath.value;

		if (currentPath) {
			const wasFavorite = player.favorites.value.includes(currentPath);

			player.toggleFavorite(currentPath);
			player.haptic();

			// Show the toast based on what the new state will be
			if (!wasFavorite) player.showToast('Agregado a favoritos', 'success');
			else player.showToast('Quitado de favoritos', 'error');
		}
	});

	onKeyStroke(['t', 'T'], (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		player.togglePauseAfterCurrent();
		player.haptic();

		player.showToast(
			{
				prefix: 'Frenamos la joda después de ',
				highlight: player.currentTrackPath.value
					? player.getTrackInfo(player.currentTrackPath.value).display_title
					: 'el tema actual',
			},
			'warning'
		);
	});

	onKeyStroke(['n', 'N'], (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		skip();
		player.haptic();
	});

	onKeyStroke(['p', 'P'], (e: KeyboardEvent) => {
		if (shouldIgnore(e)) return;

		prev();
		player.haptic();
	});
}
