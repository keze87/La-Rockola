import { onKeyStroke } from '@vueuse/core';
import { usePlayer } from './usePlayer';
import { useContextMenu } from './useContextMenu';

export function useKeyboardShortcuts() {
	const player = usePlayer();
	const ctx = useContextMenu();

	const shouldIgnore = (e) => {
		// Ignoramos si el usuario está escribiendo en un input de texto
		const el = e.target;

		return (
			el instanceof HTMLElement &&
			(el.closest('input, textarea, select, [contenteditable="true"], .ctx-menu') !== null ||
				el.isContentEditable) // , [role="menu"]
		);
	};

	onKeyStroke('Escape', (e) => {
		if (shouldIgnore(e)) return;

		if (player.isFogonMode.value) {
			player.isFogonMode.value = false;
			player.haptic();
		}

		if (ctx.ctxMenu.visible) ctx.closeCtxMenu();

		if (player.showFogonVolume?.value) player.showFogonVolume.value = false;
	});

	onKeyStroke(' ', (e) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();
		player.sendCmd('pause');
		player.haptic(true);
	});

	onKeyStroke('ArrowRight', (e) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();

		if (e.shiftKey) {
			player.sendCmd('skip');
		} else {
			const amount = 10;
			player.localTimePos.value = Math.min(player.duration.value, player.localTimePos.value + amount);
			player.ignoreServerTimeUntil.value = Date.now() + 2000;
			player.sendCmd('seek', { amount });
		}

		player.haptic();
	});

	onKeyStroke('ArrowLeft', (e) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();

		if (e.shiftKey) {
			player.sendCmd('prev');
		} else {
			const amount = -10;
			player.localTimePos.value = Math.max(0, player.localTimePos.value + amount);
			player.ignoreServerTimeUntil.value = Date.now() + 2000;
			player.sendCmd('seek', { amount });
		}

		player.haptic();
	});

	onKeyStroke('ArrowUp', (e) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();
		player.volume.value = Math.min(110, Number(player.volume.value) + 5);
		player.setVolume();

		player.showToast(
			{
				prefix: 'Volumen: ',
				highlight: player.volume.value + '%',
			},
			'success'
		);
	});

	onKeyStroke('ArrowDown', (e) => {
		if (shouldIgnore(e)) return;

		e.preventDefault();
		player.volume.value = Math.max(0, Number(player.volume.value) - 5);
		player.setVolume();

		player.showToast(
			{
				prefix: 'Volumen: ',
				highlight: player.volume.value + '%',
			},
			'success'
		);
	});

	onKeyStroke(['m', 'M'], (e) => {
		if (shouldIgnore(e)) return;

		const isCurrentlyMuted = player.serverMuted.value;

		player.sendCmd('set_mute', {
			state: !isCurrentlyMuted,
		});

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

	onKeyStroke(['f', 'F'], (e) => {
		if (shouldIgnore(e)) return;

		player.isFogonMode.value = !player.isFogonMode.value;
		player.haptic();
	});

	onKeyStroke(['l', 'L'], (e) => {
		if (shouldIgnore(e)) return;

		const currentPath = player.currentTrackPath.value;

		if (currentPath) {
			const wasFavorite = player.favorites.value.includes(currentPath);

			player.toggleFavorite(currentPath);
			player.haptic();

			// Show the toast based on what the new state will be
			if (!wasFavorite) {
				player.showToast('Agregado a favoritos', 'success');
			} else {
				player.showToast('Quitado de favoritos', 'error');
			}
		}
	});

	onKeyStroke(['t', 'T'], (e) => {
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

	onKeyStroke(['n', 'N'], (e) => {
		if (shouldIgnore(e)) return;

		player.sendCmd('skip');
		player.haptic();
	});

	onKeyStroke(['p', 'P'], (e) => {
		if (shouldIgnore(e)) return;

		player.sendCmd('prev');
		player.haptic();
	});
}
