import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import LyricsTokenModal, { extractJwtToken } from '@/components/lyrics/LyricsTokenModal.vue';

describe('LyricsTokenModal.vue', () => {
	it('extracts JWT token from raw token or curl command', () => {
		const raw = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig';
		expect(extractJwtToken(raw)).toBe(raw);

		const curl = `curl 'https://lyrics.example.com/api?token=${raw}' -H 'User-Agent: test'`;
		expect(extractJwtToken(curl)).toBe(raw);
	});

	it('renders status and emits save with extracted token', async () => {
		const wrapper = mount(LyricsTokenModal, {
			props: {
				isOpen: true,
				statusText: 'Token activo',
				hoursRemaining: 48,
				isConfigured: true,
			},
		});

		expect(wrapper.text()).toContain('Token activo');
		expect(wrapper.text()).toContain('48');

		const input = wrapper.find('input');
		await input.setValue('eyJhbGciOiJIUzI1NiJ9.test.sig');

		const saveBtn = wrapper.findAll('button').find((b) => b.text().includes('Guardar token'));
		expect(saveBtn).toBeDefined();
		await saveBtn!.trigger('click');

		expect(wrapper.emitted('save')?.[0]).toEqual(['eyJhbGciOiJIUzI1NiJ9.test.sig']);
	});

	it('emits close event when clicking close button or backdrop', async () => {
		const wrapper = mount(LyricsTokenModal, {
			props: {
				isOpen: true,
				statusText: '',
				hoursRemaining: 0,
				isConfigured: false,
			},
		});

		const cancelBtn = wrapper.findAll('button').find((b) => b.text().includes('Cancelar'));
		await cancelBtn!.trigger('click');
		expect(wrapper.emitted('close')).toBeDefined();
	});
});
