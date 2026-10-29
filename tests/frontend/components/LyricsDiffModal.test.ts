import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import LyricsDiffModal, { computeLineDiff } from '@/components/lyrics/LyricsDiffModal.vue';

describe('LyricsDiffModal.vue', () => {
	it('computes line-by-line diff between original and new content', () => {
		const original = 'Line 1\nLine 2\nLine 3';
		const modified = 'Line 1\nLine 2 modified\nLine 3\nLine 4 added';

		const diff = computeLineDiff(original, modified);
		expect(diff.some((d) => d.type === 'delete' && d.text === 'Line 2')).toBe(true);
		expect(diff.some((d) => d.type === 'add' && d.text === 'Line 2 modified')).toBe(true);
		expect(diff.some((d) => d.type === 'add' && d.text === 'Line 4 added')).toBe(true);
	});

	it('emits confirm when clicking Confirmar guardado', async () => {
		const wrapper = mount(LyricsDiffModal, {
			props: {
				isOpen: true,
				originalContent: 'Original',
				newContent: 'Modificado',
			},
		});

		const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('Confirmar guardado'));
		expect(confirmBtn).toBeDefined();
		await confirmBtn!.trigger('click');

		expect(wrapper.emitted('confirm')).toBeDefined();
	});

	it('emits close when clicking Cancelar', async () => {
		const wrapper = mount(LyricsDiffModal, {
			props: {
				isOpen: true,
				originalContent: 'Original',
				newContent: 'Modificado',
			},
		});

		const cancelBtn = wrapper.findAll('button').find((b) => b.text().includes('Cancelar'));
		await cancelBtn!.trigger('click');

		expect(wrapper.emitted('close')).toBeDefined();
	});
});
