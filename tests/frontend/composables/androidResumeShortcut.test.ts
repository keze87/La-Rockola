import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';

const { sendCmdSpy } = vi.hoisted(() => ({
	sendCmdSpy: vi.fn(async () => {}),
}));

vi.mock('@capacitor/core', () => ({
	Capacitor: {
		isNativePlatform: () => true,
		getPlatform: () => 'android',
	},
	SystemBars: { hide: vi.fn(), show: vi.fn() },
	registerPlugin: () => ({
		startServer: vi.fn(async () => ({
			running: false,
			hostState: 'starting',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/music',
		})),
		getStatus: vi.fn(async () => ({
			running: false,
			hostState: 'starting',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/music',
		})),
		consumePendingShortcut: vi.fn(async () => ({
			action: 'ar.carpincho.rockola.ACTION_RESUME_LAST',
		})),
		setBackHandlerEnabled: vi.fn(async () => ({ enabled: false })),
		setMediaTarget: vi.fn(async () => ({ updated: true })),
		getMediaVolume: vi.fn(async () => ({ level: 60, muted: false })),
		getUiRuntimeState: vi.fn(async () => ({
			pipActive: false,
			imeBottomCssPx: 0,
			volumeLevel: 60,
			volumeMuted: false,
		})),
		addListener: vi.fn(async () => ({ remove: vi.fn(async () => {}) })),
	}),
}));

vi.mock('../../../src/composables/usePlaybackControls', () => ({
	usePlaybackControls: () => ({
		pause: () => sendCmdSpy('pause'),
		seekAbsolute: vi.fn(),
		skip: vi.fn(),
		prev: vi.fn(),
		seek: vi.fn(),
		setVolume: vi.fn(),
		setMute: vi.fn(),
	}),
}));

import App from '../../../src/App.vue';
import { currentTrackPath, isPaused } from '../../../src/stores/usePlaybackStore';
import { localServerState, resetServerConnectionStore } from '../../../src/stores/useServerConnectionStore';
import { activeTab } from '../../../src/stores/useUiStore';

describe('Android ACTION_RESUME_LAST cold start', () => {
	beforeEach(() => {
		sendCmdSpy.mockClear();
		resetServerConnectionStore();
		activeTab.value = 'library';
		currentTrackPath.value = '/music/zamba.mp3';
		isPaused.value = true;
		localServerState.value = 'starting';
		global.fetch = vi.fn(async () => ({
			ok: false,
			status: 404,
			json: async () => ({}),
		})) as unknown as typeof fetch;
	});

	it('difiere la reanudación hasta que el servidor local pasa a ready', async () => {
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

		await new Promise((r) => setTimeout(r, 15));
		expect(activeTab.value).toBe('queue');
		// Mientras el servidor sigue en starting, no debe disparar pause todavía
		expect(sendCmdSpy).not.toHaveBeenCalledWith('pause');

		localServerState.value = 'ready';
		await wrapper.vm.$nextTick();
		await new Promise((r) => setTimeout(r, 10));
		expect(sendCmdSpy).toHaveBeenCalledWith('pause');

		wrapper.unmount();
	});
});
