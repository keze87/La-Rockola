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

	it('switches to fallback when image load fails', async () => {
		const wrapper = mount(CoverImage, {
			props: {
				path: '/music/corrupted_cover.mp3',
			},
		});

		const img = wrapper.find('img');
		expect(img.exists()).toBe(true);
		await img.trigger('error');

		expect(wrapper.find('img').exists()).toBe(false);
		expect(wrapper.find('.material-icons').exists()).toBe(true);
	});

	it('uses 512px size by default and allows custom sizePx or null', () => {
		const wrapperDefault = mount(CoverImage, {
			props: { path: '/music/song.mp3' },
		});
		expect(wrapperDefault.find('img').attributes('src')).toContain('&size=512');

		const wrapper512 = mount(CoverImage, {
			props: { path: '/music/song.mp3', sizePx: 512 },
		});
		expect(wrapper512.find('img').attributes('src')).toContain('&size=512');

		const wrapperOrig = mount(CoverImage, {
			props: { path: '/music/song.mp3', sizePx: null },
		});
		expect(wrapperOrig.find('img').attributes('src')).not.toContain('&size=');
	});

	it('unloads <img> when offscreen and loads it when visible', async () => {
		let observerCallback: any = null;
		class MockIntersectionObserver {
			constructor(callback: any) {
				observerCallback = callback;
			}
			observe() {}
			unobserve() {}
			disconnect() {}
		}
		const origWindowIO = (window as any).IntersectionObserver;
		const origGlobalIO = (globalThis as any).IntersectionObserver;
		(window as any).IntersectionObserver = MockIntersectionObserver;
		(globalThis as any).IntersectionObserver = MockIntersectionObserver;

		try {
			const wrapper = mount(CoverImage, {
				props: {
					path: '/music/album.flac',
					unloadWhenHidden: true,
				},
			});

			await wrapper.vm.$nextTick();

			// Initially mounted in test mode
			expect(wrapper.find('img').exists()).toBe(true);

			// Simulate scrolling out of view (offscreen / not being seen)
			if (observerCallback) {
				observerCallback([{ isIntersecting: false }]);
				await wrapper.vm.$nextTick();

				// Image is now unloaded!
				expect(wrapper.find('img').exists()).toBe(false);

				// Simulate scrolling back into view
				observerCallback([{ isIntersecting: true }]);
				await wrapper.vm.$nextTick();

				// Image is loaded back!
				expect(wrapper.find('img').exists()).toBe(true);
			}
		} finally {
			(window as any).IntersectionObserver = origWindowIO;
			(globalThis as any).IntersectionObserver = origGlobalIO;
		}
	});
});
