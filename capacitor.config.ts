import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
	appId: 'ar.carpincho.rockola',
	appName: 'La Rockola del Carpincho',
	webDir: 'dist',
	server: {
		androidScheme: 'http',
		cleartext: true,
	},
	android: {
		allowMixedContent: true,
	},
};

export default config;
