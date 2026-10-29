import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import KaraokePreview from '@/components/lyrics/KaraokePreview.vue';

describe('KaraokePreview.vue', () => {
	const sampleAss = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\kf100}Hola {\\kf100}mundo
Dialogue: 0,0:00:04.00,0:00:07.00,Default,,0,0,0,,{\\kf150}Segunda {\\kf150}línea
`;

	it('renders parsed dialogue lines with timestamps', () => {
		const wrapper = mount(KaraokePreview, {
			props: {
				assContent: sampleAss,
				currentTime: 0,
			},
		});

		const lines = wrapper.findAll('.preview-line');
		expect(lines.length).toBe(2);
		expect(lines[0].text()).toContain('Hola mundo');
		expect(lines[1].text()).toContain('Segunda línea');
	});

	it('highlights active line based on current time', () => {
		const wrapper = mount(KaraokePreview, {
			props: {
				assContent: sampleAss,
				currentTime: 2.0, // Should activate first line (1.00 to 3.00)
			},
		});

		const lines = wrapper.findAll('.preview-line');
		expect(lines[0].classes()).toContain('active-line');
		expect(lines[1].classes()).not.toContain('active-line');
	});

	it('emits seek event when a line is clicked', async () => {
		const wrapper = mount(KaraokePreview, {
			props: {
				assContent: sampleAss,
				currentTime: 0,
			},
		});

		const lines = wrapper.findAll('.preview-line');
		await lines[1].trigger('click');

		expect(wrapper.emitted('seek')?.[0]).toEqual([4.0]);
	});
});
