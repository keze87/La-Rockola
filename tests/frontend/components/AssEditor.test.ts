import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import AssEditor, { highlightAssLine } from '@/components/lyrics/AssEditor.vue';

describe('AssEditor.vue', () => {
	it('highlights ASS section headers, dialogue keys, timestamps and karaoke tags', () => {
		const headerHtml = highlightAssLine('[Events]');
		expect(headerHtml).toContain('text-carpincho-warning');
		expect(headerHtml).toContain('[Events]');

		const dialogueHtml = highlightAssLine('Dialogue: 0,0:00:01.50,0:00:03.20,Default,,0,0,0,,{\\kf50}Hola');
		expect(dialogueHtml).toContain('text-sky-400'); // Dialogue:
		expect(dialogueHtml).toContain('text-amber-300'); // Timestamps
		expect(dialogueHtml).toContain('text-emerald-400'); // {\kf50}
	});

	it('emits update:modelValue when text changes in textarea', async () => {
		const wrapper = mount(AssEditor, {
			props: {
				modelValue: '[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hola',
			},
		});

		const textarea = wrapper.find('textarea');
		expect(textarea.exists()).toBe(true);

		await textarea.setValue('[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Chau');
		expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([
			'[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Chau',
		]);
	});

	it('renders line numbers matching line count', () => {
		const sample = 'Line 1\nLine 2\nLine 3\nLine 4';
		const wrapper = mount(AssEditor, {
			props: {
				modelValue: sample,
			},
		});

		const lineNums = wrapper.findAll('.line-number');
		expect(lineNums.length).toBe(4);
		expect(lineNums[0].text()).toBe('1');
		expect(lineNums[3].text()).toBe('4');
	});
});
