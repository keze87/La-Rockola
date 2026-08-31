import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import CoverImage from '@/components/ui/CoverImage.vue';

describe('CoverImage.vue', () => {
	it('renders <img> with coverUrl when a valid local path is passed', () => {
		const wrapper = mount(CoverImage, {
			props: {
				path: '/music/album.flac',
				size: 'h-12 w-12',
			},
		});

		const img = wrapper.find('img');
		expect(img.exists()).toBe(true);
		expect(img.attributes('src')).toContain('/cover?path=');
		expect(img.classes()).toContain('h-12');
		expect(img.classes()).toContain('w-12');
	});

	it('renders fallback icon placeholder when path is null', () => {
		const wrapper = mount(CoverImage, {
			props: {
				path: null,
			},
		});

		expect(wrapper.find('img').exists()).toBe(false);
		expect(wrapper.find('.material-icons').text()).toBe('album');
	});
});
