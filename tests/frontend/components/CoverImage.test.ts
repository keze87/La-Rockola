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

	it('renders loading skeleton until image finishes loading and resets when path changes', async () => {
		const wrapper = mount(CoverImage, {
			props: {
				path: '/music/first.flac',
				sizePx: 128,
			},
		});

		expect(wrapper.find('.cover-skeleton').exists()).toBe(true);
		const img = wrapper.find('img.cover-main-img');
		expect(img.exists()).toBe(true);
		expect(img.classes()).toContain('opacity-0');

		await img.trigger('load');
		expect(wrapper.find('.cover-skeleton').exists()).toBe(false);
		expect(wrapper.find('img.cover-main-img').classes()).toContain('opacity-100');

		await wrapper.setProps({ path: '/music/second.flac' });
		expect(wrapper.find('.cover-skeleton').exists()).toBe(true);
		expect(wrapper.find('img.cover-main-img').classes()).toContain('opacity-0');
	});

	it('renders progressive 128px thumbnail layer when sizePx > 128', async () => {
		const wrapper = mount(CoverImage, {
			props: {
				path: '/music/big.flac',
				sizePx: 512,
			},
		});

		const thumb = wrapper.find('img.cover-thumb-img');
		const main = wrapper.find('img.cover-main-img');
		expect(thumb.exists()).toBe(true);
		expect(thumb.attributes('src')).toContain('&size=128');
		expect(main.exists()).toBe(true);
		expect(main.attributes('src')).toContain('&size=512');

		// Al cargar la miniatura 128px desaparece el skeleton inmediatamente
		await thumb.trigger('load');
		expect(wrapper.find('.cover-skeleton').exists()).toBe(false);
	});

	it('does not defer loading with loading=lazy and marks cached complete images loaded after mount', async () => {
		const wrapper = mount(CoverImage, {
			props: {
				path: '/music/cached.flac',
				sizePx: 128,
			},
		});

		const imgEl = wrapper.find('img.cover-main-img');
		expect(imgEl.exists()).toBe(true);
		expect(imgEl.attributes('loading')).toBeUndefined();

		Object.defineProperty(imgEl.element, 'complete', { value: true, configurable: true });
		Object.defineProperty(imgEl.element, 'naturalWidth', { value: 128, configurable: true });

		// Al re-evaluar tras cambiar path con imagen ya completa en caché, debe mostrarse
		await wrapper.setProps({ path: '/music/cached-2.flac' });
		await wrapper.vm.$nextTick();
		expect(wrapper.find('img.cover-main-img').classes()).toContain('opacity-100');
	});

	it('keeps image mounted by default (unloadWhenHidden=false) even if IntersectionObserver reports false', async () => {
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
				},
			});
			await wrapper.vm.$nextTick();
			if (observerCallback) {
				observerCallback([{ isIntersecting: false }]);
				await wrapper.vm.$nextTick();
			}
			expect(wrapper.find('img.cover-main-img').exists()).toBe(true);
		} finally {
			(window as any).IntersectionObserver = origWindowIO;
			(globalThis as any).IntersectionObserver = origGlobalIO;
		}
	});
});
