import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';

const { setBackHandlerSpy } = vi.hoisted(() => ({
	setBackHandlerSpy: vi.fn(async (opts: { enabled: boolean }) => ({ enabled: opts.enabled })),
}));

vi.mock('@capacitor/core', () => ({
	Capacitor: {
		isNativePlatform: () => true,
		getPlatform: () => 'android',
	},
	SystemBars: { hide: vi.fn(), show: vi.fn() },
	registerPlugin: () => ({
		startServer: vi.fn(async () => ({
			running: true,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/music',
		})),
		getStatus: vi.fn(async () => ({
			running: true,
			hostState: 'ready',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/music',
		})),
		consumePendingShortcut: vi.fn(async () => ({ action: null })),
		setBackHandlerEnabled: setBackHandlerSpy,
	}),
}));

import App from '../../../src/App.vue';
import { useContextMenu } from '../../../src/composables/useContextMenu';
import {
	activeTab,
	isFogonMode,
	isLyricsEditorOpen,
	registerOpenModal,
	unregisterOpenModal,
} from '../../../src/stores/useUiStore';

describe('Android predictive back handler', () => {
	beforeEach(() => {
		setBackHandlerSpy.mockClear();
		activeTab.value = 'library';
		isFogonMode.value = false;
		isLyricsEditorOpen.value = false;
		useContextMenu().closeCtxMenu();
		unregisterOpenModal('test-modal');
	});

	it('empuja isEnabled al nativo y cierra cada capa en orden de prioridad', async () => {
		const HostStub = defineComponent({ template: '<div />' });
		const wrapper = mount(App, {
			global: {
				stubs: {
					Toaster: HostStub,
					FogonMode: HostStub,
					LyricsEditorView: HostStub,
					ContextMenu: HostStub,
					LibraryTab: HostStub,
					QueueTab: HostStub,
					TopTab: HostStub,
					ControlsTab: HostStub,
					FloatingPlayer: HostStub,
				},
			},
		});

		await wrapper.vm.$nextTick();
		expect(setBackHandlerSpy).toHaveBeenLastCalledWith({ enabled: false });
		expect(window.__rockolaHandleBack?.()).toBe(false);

		// 1. Pestaña distinta a library
		activeTab.value = 'queue';
		await wrapper.vm.$nextTick();
		expect(setBackHandlerSpy).toHaveBeenLastCalledWith({ enabled: true });

		// 2. Fogón encima
		isFogonMode.value = true;
		await wrapper.vm.$nextTick();
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(isFogonMode.value).toBe(false);
		expect(activeTab.value).toBe('queue');

		// 3. Editor de letras encima
		isLyricsEditorOpen.value = true;
		await wrapper.vm.$nextTick();
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(isLyricsEditorOpen.value).toBe(false);

		// 4. Menú contextual encima
		useContextMenu().openCtxMenu(
			{ clientX: 10, clientY: 10 } as MouseEvent,
			{ path: '/a.mp3', display_title: 'A', display_artist: 'B' },
			'library'
		);
		await wrapper.vm.$nextTick();
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(useContextMenu().ctxMenu.visible).toBe(false);

		// 5. Modal registrado
		const closeModal = vi.fn(() => unregisterOpenModal('test-modal'));
		registerOpenModal('test-modal', closeModal);
		await wrapper.vm.$nextTick();
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(closeModal).toHaveBeenCalledTimes(1);

		// 6. Cierra foco de input antes de navegar
		const input = document.createElement('input');
		document.body.appendChild(input);
		input.focus();
		input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
		await wrapper.vm.$nextTick();
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(document.activeElement).not.toBe(input);
		input.remove();

		// 7. Cierra pestaña queue -> vuelve a library -> deshabilita callback nativo
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(activeTab.value).toBe('library');
		await wrapper.vm.$nextTick();
		expect(setBackHandlerSpy).toHaveBeenLastCalledWith({ enabled: false });
		expect(window.__rockolaHandleBack?.()).toBe(false);

		wrapper.unmount();
	});
});
