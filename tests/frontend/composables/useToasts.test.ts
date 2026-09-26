import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'vue-sonner';
import { useToasts } from '@/composables/player/useToasts';

vi.mock('vue-sonner', () => {
	const fn = vi.fn();
	(fn as any).success = vi.fn();
	(fn as any).warning = vi.fn();
	(fn as any).error = vi.fn();
	return { toast: fn };
});

describe('useToasts.ts', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('shows plain string toast with default info type', () => {
		const { showToast } = useToasts();
		showToast('¡Hola Carpincho!');
		expect(toast).toHaveBeenCalledWith('¡Hola Carpincho!');
	});

	it('shows success, warning, and error toasts', () => {
		const { showToast } = useToasts();

		showToast('Éxito total', 'success');
		expect(toast.success).toHaveBeenCalledWith('Éxito total');

		showToast('Ojo al piojo', 'warning');
		expect(toast.warning).toHaveBeenCalledWith('Ojo al piojo');

		showToast('Se pudrió todo', 'error');
		expect(toast.error).toHaveBeenCalledWith('Se pudrió todo');
	});

	it('formats message object without highlight into a plain string', () => {
		const { showToast } = useToasts();
		showToast({ prefix: 'Agregado: ', highlight: '', suffix: ' a la fila' });
		expect(toast).toHaveBeenCalledWith('Agregado:  a la fila');
	});

	it('formats message object with highlight into a component with setup()', () => {
		const { showToast } = useToasts();
		showToast({ prefix: 'Tema: ', highlight: 'Jijiji', suffix: ' agregado' });

		expect(toast).toHaveBeenCalled();
		const passedComponent = (toast as any).mock.calls[0][0];
		expect(typeof passedComponent.setup).toBe('function');

		// Call setup to test the VNode rendering
		const renderFn = passedComponent.setup();
		expect(typeof renderFn).toBe('function');
		const vnode = renderFn();
		expect(vnode.type).toBe('span');
	});
});
