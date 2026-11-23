import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ControlsTab from '@/components/ControlsTab.vue';
import QRCode from 'qrcode.vue';
import {
	activeSort,
	activeTab,
	currentTracks,
	defaultSort,
	djBaraEnabled,
	djMode,
	djSafeModeEnabled,
	hasEdgeTts,
	hasFfmpeg,
	hasLocalPlayer,
	hasMpv,
	isScanning,
	listenLocally,
	mpvVisible,
	radioModeEnabled,
	scanStatus,
	serverMuted,
	serverUrl,
	setWsSend,
	volume,
	weatherLocation,
} from '@/composables/player/state';

describe('ControlsTab.vue', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);
		global.fetch = fetchMock;

		currentTracks.value = [];
		activeTab.value = 'controls';
		djBaraEnabled.value = false;
		djSafeModeEnabled.value = false;
		hasEdgeTts.value = true;
		hasFfmpeg.value = true;
		hasLocalPlayer.value = false;
		hasMpv.value = true;
		listenLocally.value = false;
		mpvVisible.value = true;
		radioModeEnabled.value = false;
		serverMuted.value = false;
		serverUrl.value = null;
		volume.value = 80;
		isScanning.value = false;
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: false,
			phase: 'idle',
			current: 0,
			total: 0,
			message: '',
		};
	});

	it('renders volume controls, sort buttons, and toggles', () => {
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).toContain('Acomodando la gilada');
		expect(wrapper.text()).toContain('Como llegaron');
		expect(wrapper.text()).toContain('Por el que canta');
		expect(wrapper.text()).toContain('Más Manija');
		expect(wrapper.text()).toContain('Mezcladito (A lo loco)');
		expect(wrapper.text()).toContain('La Joda');
		expect(wrapper.text()).toContain('DJ Bara');
		expect(wrapper.text()).toContain('Carpincho locutor');
		expect(wrapper.text()).toContain('Escuchar acá');
	});

	it('hides "Más Manija" button when hasFfmpeg is false', () => {
		hasFfmpeg.value = false;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).not.toContain('Más Manija');
		expect(wrapper.text()).toContain('Como llegaron');
		expect(wrapper.text()).toContain('Por el que canta');
		expect(wrapper.text()).toContain('Mezcladito (A lo loco)');
	});

	it('toggles mute when mute icon or button is clicked', async () => {
		const wrapper = mount(ControlsTab);

		const muteIcon = wrapper.find('button[aria-label*="audio"] .material-icons');
		await muteIcon.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_mute', state: true }),
			})
		);
	});

	it('dispatches stop command when "Cortala de una" is clicked', async () => {
		const wrapper = mount(ControlsTab);

		const stopBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Cortala de una'));
		expect(stopBtn).toBeDefined();
		await stopBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'stop' }),
			})
		);
	});

	it('toggles DJ Bara mode when toggle is clicked', async () => {
		const wrapper = mount(ControlsTab);

		const toggles = wrapper.findAllComponents({ name: 'ToggleRow' });
		const djToggle = toggles.find((t) => t.props('title') === 'DJ Bara');
		expect(djToggle).toBeDefined();

		const switchBtn = djToggle!.find('button');
		await switchBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'toggle_dj_carpincho', state: true }),
			})
		);
	});

	it('renders and dispatches set_dj_mode when selecting DJ Bara modes', async () => {
		djBaraEnabled.value = true;
		djMode.value = 'shuffle';
		currentTracks.value = [
			{ path: '/music/a.mp3', display_title: 'Tema A', display_artist: 'Art A' } as any,
			{ path: '/music/b.mp3', display_title: 'Tema B', display_artist: 'Art B' } as any,
		];
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).toContain('Modo del DJ Bara');
		expect(wrapper.text()).toContain('Aleatorio');
		expect(wrapper.text()).toContain('Favoritos');
		expect(wrapper.text()).toContain('Lista de librería');

		// Click en 'Favoritos'
		const favButton = wrapper.findAll('button').find((b) => b.text().includes('Favoritos'));
		expect(favButton).toBeDefined();
		await favButton!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_dj_mode', mode: 'favorites' }),
			})
		);

		// Click en 'Lista de librería'
		const libButton = wrapper.findAll('button').find((b) => b.text().includes('Lista de librería'));
		expect(libButton).toBeDefined();
		await libButton!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_dj_mode', mode: 'library', paths: ['/music/a.mp3', '/music/b.mp3'] }),
			})
		);
	});

	it('dispatches toggle_radio_mode when clicking Carpincho locutor toggle', async () => {
		radioModeEnabled.value = false;
		hasEdgeTts.value = true;
		const wrapper = mount(ControlsTab);

		const toggles = wrapper.findAllComponents({ name: 'ToggleRow' });
		const radioToggle = toggles.find((t) => t.props('title') === 'Carpincho locutor');
		expect(radioToggle).toBeDefined();

		const switchBtn = radioToggle!.find('button');
		await switchBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'toggle_radio_mode', state: true }),
			})
		);
	});

	it('hides Carpincho locutor toggle when hasEdgeTts is false', () => {
		hasEdgeTts.value = false;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).not.toContain('Carpincho locutor');
	});

	it('uses serverUrl for QR code when opened on localhost', () => {
		serverUrl.value = 'http://192.168.1.100:1729';
		const wrapper = mount(ControlsTab);
		const qrCode = wrapper.findComponent(QRCode);
		expect(qrCode.exists()).toBe(true);
		expect(qrCode.props('value')).toBe('http://192.168.1.100:1729');
	});

	it('triggers mute toggle from PillButton', async () => {
		serverMuted.value = false;
		const wrapper = mount(ControlsTab);

		const muteBtn = wrapper.findAllComponents({ name: 'PillButton' }).find((w) => w.text().includes('Mutear'));
		expect(muteBtn).toBeDefined();
		await muteBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_mute', state: true }),
			})
		);
	});

	it('triggers library rescan when clicking "Pegale otra escaneada"', async () => {
		const wrapper = mount(ControlsTab);

		const rescanBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Pegale otra escaneada'));
		expect(rescanBtn).toBeDefined();
		await rescanBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith('/scan');
	});

	it('toggles MPV visibility when clicking MPV toggle button', async () => {
		mpvVisible.value = true;
		const wrapper = mount(ControlsTab);

		const hideBtn = wrapper.findAllComponents({ name: 'PillButton' }).find((w) => w.text().includes('Ocultar MPV'));
		expect(hideBtn).toBeDefined();
		await hideBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith('/mpv/hide', expect.anything());
	});

	it('dispatches fullscreen command when clicking "Todo pantalla, ñeri"', async () => {
		const wrapper = mount(ControlsTab);

		const fsBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Todo pantalla, ñeri'));
		expect(fsBtn).toBeDefined();
		await fsBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'fullscreen' }),
			})
		);
	});

	it('triggers library sorting when clicking sort buttons', async () => {
		currentTracks.value = [
			{ path: '/a.mp3', title: 'B', artist: 'Z', bpm: 100 },
			{ path: '/b.mp3', title: 'A', artist: 'A', bpm: 140 },
		];
		const wrapper = mount(ControlsTab);

		const pills = wrapper.findAllComponents({ name: 'PillButton' });
		const byArtist = pills.find((w) => w.text().includes('Por el que canta'));
		const byTime = pills.find((w) => w.text().includes('Como llegaron'));
		const byMood = pills.find((w) => w.text().includes('Más Manija'));
		const byShuffle = pills.find((w) => w.text().includes('Mezcladito'));

		await byArtist?.trigger('click');
		expect(currentTracks.value[0].artist).toBe('A');
		expect(activeTab.value).toBe('library');

		await byMood?.trigger('click');
		expect(currentTracks.value[0].bpm).toBe(140);

		await byTime?.trigger('click');
		await byShuffle?.trigger('click');
	});

	it('disables "Más Manija" and displays "Sintonizando vibra..." when is_analyzing_mood is true', () => {
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: true,
			phase: 'mood',
			current: 10,
			total: 50,
			message: '',
		};
		const wrapper = mount(ControlsTab);

		const moodBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Sintonizando vibra'));
		expect(moodBtn).toBeDefined();
		expect(moodBtn?.attributes('disabled')).toBeDefined();
	});

	it('disables "Pegale otra escaneada" and displays progress when isScanning is true', () => {
		isScanning.value = true;
		scanStatus.value = {
			is_scanning: true,
			phase: 'metadata',
			current: 120,
			total: 500,
			message: '',
		};
		const wrapper = mount(ControlsTab);

		const scanBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Escaneando...'));
		expect(scanBtn).toBeDefined();
		expect(scanBtn?.text()).toContain('120/500');
		expect(scanBtn?.attributes('disabled')).toBeDefined();
	});

	it('displays current weather location and opens weather modal when clicked', async () => {
		hasEdgeTts.value = true;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).toContain('Ubicación del Clima: San Miguel de Tucumán');

		const mapBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Ubicación del Clima: San Miguel de Tucumán'));
		expect(mapBtn).toBeDefined();

		await mapBtn!.trigger('click');

		const modal = wrapper.findComponent({ name: 'WeatherLocationModal' });
		expect(modal.exists()).toBe(true);
		expect(modal.props('isOpen')).toBe(true);
	});

	it('displays resolved wttr location instead of raw coordinates when weatherLocation contains coordinates', async () => {
		fetchMock.mockImplementation((url: string) => {
			if (url.includes('/api/weather/preview')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							ok: true,
							location: '-34.6037,-58.3816',
							area_name: 'Buenos Aires',
							temp_c: 22,
							phrase: 'Clima lindo',
						}),
				} as unknown as Response);
			}
			return Promise.resolve({
				ok: true,
				json: () => Promise.resolve({ status: 'ok', data: [] }),
			} as unknown as Response);
		});

		hasEdgeTts.value = true;
		weatherLocation.value = '-34.6037,-58.3816';
		const wrapper = mount(ControlsTab);

		await flushPromises();

		expect(wrapper.text()).toContain('Ubicación del Clima: Buenos Aires');
		expect(wrapper.text()).not.toContain('-34.6037,-58.3816');
	});

	it('shows return to server speakers button when another client is playing locally', async () => {
		hasLocalPlayer.value = true;
		listenLocally.value = false;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).not.toContain('Alguien está escuchando en su dispositivo');
		expect(wrapper.text()).toContain('Volver a parlantes del servidor');
	});

	it('hides return to server speakers button when local player is not active or this client is playing', () => {
		// 1. No local player
		hasLocalPlayer.value = false;
		listenLocally.value = false;
		let wrapper = mount(ControlsTab);
		expect(wrapper.text()).not.toContain('Volver a parlantes del servidor');

		// 2. This client is the local player
		hasLocalPlayer.value = true;
		listenLocally.value = true;
		wrapper = mount(ControlsTab);
		expect(wrapper.text()).not.toContain('Volver a parlantes del servidor');
	});

	it('calls returnToServerSpeakers when return button is clicked', async () => {
		const wsSendMock = vi.fn();
		setWsSend(wsSendMock);

		hasLocalPlayer.value = true;
		listenLocally.value = false;
		const wrapper = mount(ControlsTab);

		const btn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Volver a parlantes del servidor'));
		expect(btn).toBeDefined();
		await btn!.trigger('click');

		expect(wsSendMock).toHaveBeenCalled();
		const sent = JSON.parse(wsSendMock.mock.calls[0][0]);
		expect(sent.type).toBe('local_player_reset');
	});

	it('displays "Mostrar MPV" with visibility icon when mpvVisible is false', () => {
		mpvVisible.value = false;
		const wrapper = mount(ControlsTab);

		const btn = wrapper.findAllComponents({ name: 'PillButton' }).find((b) => b.text().includes('Mostrar MPV'));
		expect(btn).toBeDefined();
		expect(btn?.props('icon')).toBe('visibility');
	});

	it('displays "Ocultar MPV" with visibility_off icon when mpvVisible is true', () => {
		mpvVisible.value = true;
		const wrapper = mount(ControlsTab);

		const btn = wrapper.findAllComponents({ name: 'PillButton' }).find((b) => b.text().includes('Ocultar MPV'));
		expect(btn).toBeDefined();
		expect(btn?.props('icon')).toBe('visibility_off');
	});

	it('clicking an inactive sort button changes activeSort for session only without saving config', async () => {
		activeSort.value = 'time';
		defaultSort.value = 'time';
		const wrapper = mount(ControlsTab);

		const artistBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Por el que canta'));
		expect(artistBtn).toBeDefined();

		await artistBtn!.trigger('click');

		expect(activeSort.value).toBe('artist');
		expect(defaultSort.value).toBe('time');
		expect(activeTab.value).toBe('library');
		expect(fetchMock).not.toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: expect.stringContaining('set_default_sort'),
			})
		);
	});

	it('clicking an active sort button again saves defaultSort to config via API', async () => {
		activeSort.value = 'artist';
		defaultSort.value = 'time';
		const wrapper = mount(ControlsTab);

		const artistBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Por el que canta'));
		expect(artistBtn).toBeDefined();

		await artistBtn!.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_default_sort', sort: 'artist' }),
			})
		);
		expect(defaultSort.value).toBe('artist');
		expect(activeTab.value).toBe('library');
	});

	it('shows a visible indicator on the saved defaultSort button', () => {
		activeSort.value = 'time';
		defaultSort.value = 'shuffle';
		const wrapper = mount(ControlsTab);

		const shuffleBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Mezcladito'));
		expect(shuffleBtn).toBeDefined();
		expect(shuffleBtn!.find('[aria-label="Orden por defecto"]').exists()).toBe(true);

		const timeBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Como llegaron'));
		expect(timeBtn!.find('[aria-label="Orden por defecto"]').exists()).toBe(false);
	});

	it('hides MPV controls and shows local listen button when hasMpv is false', async () => {
		hasMpv.value = false;
		hasLocalPlayer.value = false;
		listenLocally.value = false;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).not.toContain('Mostrar MPV');
		expect(wrapper.text()).not.toContain('Ocultar MPV');
		expect(wrapper.text()).not.toContain('Todo pantalla, ñeri');
		expect(wrapper.text()).not.toContain('Volver a parlantes del servidor');

		const listenBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Escuchar en este dispositivo'));
		expect(listenBtn).toBeDefined();

		await listenBtn!.trigger('click');
		expect(listenLocally.value).toBe(true);
	});

	it('toggles native Android fullscreen via SystemBars when Full Rockola is clicked on Android', async () => {
		const androidHost = await import('@/composables/useAndroidHost');
		const isNativeSpy = vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const toggleSpy = vi.spyOn(androidHost as any, 'toggleAndroidFullscreen').mockImplementation(async () => {
			(androidHost as any).isAndroidFullscreen.value = !(androidHost as any).isAndroidFullscreen.value;
			return (androidHost as any).isAndroidFullscreen.value;
		});

		const wrapper = mount(ControlsTab);
		const fullBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Full Rockola'));
		expect(fullBtn).toBeDefined();
		expect(fullBtn!.props('icon')).toBe('open_in_full');

		await fullBtn!.trigger('click');
		await flushPromises();

		expect(toggleSpy).toHaveBeenCalledTimes(1);
		expect(fullBtn!.props('icon')).toBe('fullscreen_exit');

		isNativeSpy.mockRestore();
		toggleSpy.mockRestore();
		if ((androidHost as any).isAndroidFullscreen) {
			(androidHost as any).isAndroidFullscreen.value = false;
		}
	});

	it('shares QR URL natively on Android and via Web Share / clipboard fallback on web', async () => {
		const androidHost = await import('@/composables/useAndroidHost');
		const isNativeSpy = vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const shareNativeSpy = vi.spyOn(androidHost as any, 'shareAndroidUrl').mockResolvedValue(true);

		serverUrl.value = 'http://192.168.0.55:1729';
		const wrapper = mount(ControlsTab);

		const shareBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((b) => b.text().includes('Compartir link'));
		expect(shareBtn).toBeDefined();

		// En Android usa Intent.ACTION_SEND nativo
		await shareBtn!.trigger('click');
		await flushPromises();
		expect(shareNativeSpy).toHaveBeenCalledWith(
			expect.objectContaining({
				url: 'http://192.168.0.55:1729',
			})
		);

		// En web usa navigator.share si está disponible o clipboard fallback
		isNativeSpy.mockReturnValue(false);
		const writeTextMock = vi.fn().mockResolvedValue(undefined);
		const originalClipboard = navigator.clipboard;
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: { writeText: writeTextMock },
		});
		const originalShare = (navigator as any).share;
		delete (navigator as any).share;

		try {
			await shareBtn!.trigger('click');
			await flushPromises();
			expect(writeTextMock).toHaveBeenCalledWith('http://192.168.0.55:1729');
		} finally {
			isNativeSpy.mockRestore();
			shareNativeSpy.mockRestore();
			if (originalShare !== undefined) {
				Object.defineProperty(navigator, 'share', { configurable: true, value: originalShare });
			}
			Object.defineProperty(navigator, 'clipboard', { configurable: true, value: originalClipboard });
		}
	});

	it('hides "Escuchar acá" toggle on local Android host unless connected to remote server', async () => {
		const androidHost = await import('@/composables/useAndroidHost');
		const isNativeSpy = vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const prevRemoteUrl = androidHost.activeRemoteServerUrl.value;

		try {
			androidHost.activeRemoteServerUrl.value = null;
			const wrapper = mount(ControlsTab);

			expect(wrapper.text()).not.toContain('Escuchar acá');

			androidHost.activeRemoteServerUrl.value = 'http://192.168.1.50:1729';
			await wrapper.vm.$nextTick();

			expect(wrapper.text()).toContain('Escuchar acá');
			expect(wrapper.text()).not.toContain('Elegir carpeta de música');
		} finally {
			androidHost.activeRemoteServerUrl.value = prevRemoteUrl;
			isNativeSpy.mockRestore();
		}
	});

	it('renders native accessible <dialog> for remote server and Android host status panel with start/stop/error banner', async () => {
		const androidHost = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');
		const isNativeSpy = vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const stopSpy = vi.spyOn(androidHost, 'stopAndroidServer').mockResolvedValue(undefined);
		const startSpy = vi.spyOn(androidHost, 'initAndroidServer').mockResolvedValue(true);

		store.resetServerConnectionStore();
		store.setHostMode();
		store.localServerState.value = 'ready';
		store.localServerLanUrl.value = 'http://192.168.0.77:1729';
		store.localMusicDir.value = 'content://com.android.externalstorage.documents/tree/primary%3AMusic';
		store.localMusicDisplayName.value = 'Music';
		store.libraryFolderStatus.value = 'ok';
		store.setServerError('HOST_FAILED', 'No se pudo abrir el puerto 1729');

		try {
			const wrapper = mount(ControlsTab);

			// Banner de error accionable y tarjeta de estado Host/Remoto
			expect(wrapper.text()).toContain('Modo Host local');
			expect(wrapper.text()).toContain('Encendido');
			expect(wrapper.text()).toContain('http://192.168.0.77:1729');
			expect(wrapper.text()).toContain('No se pudo abrir el puerto 1729');

			const stopHostBtn = wrapper.findAll('button').find((b) => b.text().includes('Apagar servidor'));
			expect(stopHostBtn).toBeDefined();
			await stopHostBtn!.trigger('click');
			expect(stopSpy).toHaveBeenCalledTimes(1);

			store.localServerState.value = 'stopped';
			await wrapper.vm.$nextTick();
			const startHostBtn = wrapper.findAll('button').find((b) => b.text().includes('Prender servidor'));
			expect(startHostBtn).toBeDefined();
			await startHostBtn!.trigger('click');
			expect(startSpy).toHaveBeenCalledTimes(1);

			// Volumen usa botón semántico con aria-label
			const volBtn = wrapper.find(
				'button[aria-label*="Silenciar"], button[aria-label*="Mutear"], button[aria-label*="Desmutear"]'
			);
			expect(volBtn.exists()).toBe(true);

			// Diálogo remoto usa <dialog> nativo sin role="dialog" redundante y con <label for>
			const dialogEl = wrapper.find('dialog');
			expect(dialogEl.exists()).toBe(true);
			expect(dialogEl.attributes('role')).toBeUndefined();
			expect(dialogEl.attributes('aria-modal')).toBeUndefined();
			expect(dialogEl.attributes('aria-labelledby')).toBe('remote-dialog-title');
			expect(dialogEl.find('label[for="remote-server-input"]').exists()).toBe(true);
			expect(dialogEl.find('input#remote-server-input').exists()).toBe(true);

			// La cara del carpincho en el QR debe usar el asset local del bundle y no apiUrl()
			const qrLogo = wrapper.find('img[alt="Logo Carpincho"]');
			expect(qrLogo.exists()).toBe(true);
			expect(qrLogo.attributes('src')).toBe('/favicon.png');
		} finally {
			store.resetServerConnectionStore();
			isNativeSpy.mockRestore();
			stopSpy.mockRestore();
			startSpy.mockRestore();
		}
	});
});
