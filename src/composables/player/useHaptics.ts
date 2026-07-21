import { useVibrate } from '@vueuse/core';

const { vibrate } = useVibrate();

export function useHaptics() {
	function haptic(heavy: boolean = false) {
		if ('vibrate' in navigator && typeof navigator.vibrate === 'function') {
			vibrate(heavy ? [10, 30, 20] : 10);
			return;
		}
		try {
			const AudioContextClass = window.AudioContext || window.webkitAudioContext;
			const ctx = new AudioContextClass();
			const osc = ctx.createOscillator();
			const gain = ctx.createGain();
			osc.connect(gain);
			gain.connect(ctx.destination);
			gain.gain.setValueAtTime(heavy ? 0.03 : 0.01, ctx.currentTime);
			gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + (heavy ? 0.05 : 0.02));
			osc.frequency.setValueAtTime(heavy ? 200 : 400, ctx.currentTime);
			osc.start(ctx.currentTime);
			osc.stop(ctx.currentTime + (heavy ? 0.05 : 0.02));
			osc.onended = () => ctx.close();
		} catch {
			// Si el navegador no lo soporta, fallamos silenciosamente sin romper nada
		}
	}

	return { haptic };
}
