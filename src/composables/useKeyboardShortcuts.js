import { onMounted, onBeforeUnmount } from 'vue'
import { usePlayer } from './usePlayer'
import { useContextMenu } from './useContextMenu'

export function useKeyboardShortcuts() {
	const player = usePlayer()
	const ctx = useContextMenu()

	function handleKeydown(e) {
		// Ignoramos si el usuario está escribiendo en un input de texto
		if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

		switch (e.key) {
			case 'Escape':
				if (player.isFogonMode.value) {
					player.isFogonMode.value = false;
					player.haptic();
				}
				if (ctx.ctxMenu.visible) ctx.closeCtxMenu();
				if (player.showFogonVolume?.value) player.showFogonVolume.value = false;
				break;
			case ' ': // Barra espaciadora
				e.preventDefault();
				player.sendCmd('pause');
				player.haptic(true);
				break;
			case 'ArrowRight':
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
				break;
			case 'ArrowLeft':
				e.preventDefault();
				if (e.shiftKey) {
					player.sendCmd('prev');
				} else {
					const amount = -10;
					player.localTimePos.value = Math.max(0, player.localTimePos.value - amount);
					player.ignoreServerTimeUntil.value = Date.now() + 2000;
					player.sendCmd('seek', { amount });
				}
				player.haptic();
				break;
			case 'ArrowUp':
				e.preventDefault();
				player.volume.value = Math.min(110, parseInt(player.volume.value) + 5);
				player.setVolume();
				break;
			case 'ArrowDown':
				e.preventDefault();
				player.volume.value = Math.max(0, parseInt(player.volume.value) - 5);
				player.setVolume();
				break;
			case 'm':
			case 'M':
				player.sendCmd('set_mute', { state: !player.serverMuted.value });
				break;
			case 'f':
			case 'F':
				player.isFogonMode.value = !player.isFogonMode.value;
				player.haptic();
				break;
			case 'l':
			case 'L':
				if (player.currentTrackPath.value) {
					player.toggleFavorite(player.currentTrackPath.value);
					player.haptic();
				}
				break;
			case 't':
			case 'T':
				player.togglePauseAfterCurrent();
				player.haptic();
				break;
			case 'n':
			case 'N':
				player.sendCmd('skip');
				player.haptic();
				break;
			case 'p':
			case 'P':
				player.sendCmd('prev');
				player.haptic();
				break;
		}
	}

	onMounted(() => {
		window.addEventListener('keydown', handleKeydown);
	});

	onBeforeUnmount(() => {
		window.removeEventListener('keydown', handleKeydown);
	});
}