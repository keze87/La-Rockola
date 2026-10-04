import { toValue, type MaybeRefOrGetter } from 'vue';
import { useDragSlider } from './useDragSlider';

export function useSliderFactory() {
	/**
	 * @param {Ref|Number|Function} source - Valor reactivo para la posición actual del control deslizante
	 * @param {Ref|Number|Function} max - Valor reactivo para el límite máximo del control
	 * @param {Function} onUpdate - Se dispara de forma continua mientras se arrastra
	 * @param {Function} onCommit - Se dispara una sola vez cuando el usuario suelta el control
	 */
	function createSlider(
		source: MaybeRefOrGetter<number>,
		max: MaybeRefOrGetter<number>,
		onUpdate: (val: number) => void,
		onCommit?: (val: number) => void
	) {
		return useDragSlider({
			// toValue desenvuelve refs automáticamente o ejecuta funciones getter
			max: () => toValue(max),
			getValue: () => toValue(source),
			onUpdate,
			onCommit: onCommit || onUpdate, // Fallback a onUpdate si no se requiere un commit diferenciado
		});
	}

	return { createSlider };
}
