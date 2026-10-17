// Generador de audio WAV en código morse ("CARPINCHO") ultra-bajito.
// Se usa como keepalive para mantener vivo el elemento <audio> y la Media Session
// del sistema operativo en navegadores móviles cuando la reproducción ocurre en el servidor.

const MORSE_MAP: Record<string, string> = {
	A: '.-',
	B: '-...',
	C: '-.-.',
	D: '-..',
	E: '.',
	F: '..-.',
	G: '--.',
	H: '....',
	I: '..',
	J: '.---',
	K: '-.-',
	L: '.-..',
	M: '--',
	N: '-.',
	O: '---',
	P: '.--.',
	Q: '--.-',
	R: '.-.',
	S: '...',
	T: '-',
	U: '..-',
	V: '...-',
	W: '.--',
	X: '-..-',
	Y: '-.--',
	Z: '--..',
};

export function createFaintNoiseBlob(message = 'CARPINCHO'): Blob {
	const sampleRate = 44100;
	const unit = 0.2;
	const amplitude = 10;
	const frequency = 440;

	const sequence = message
		.toUpperCase()
		.split('')
		.map((ch) => MORSE_MAP[ch] || '')
		.join(' ');

	const samples: number[] = [];
	const addTone = (units: number) => {
		for (let i = 0; i < units * unit * sampleRate; i++) {
			const t = i / sampleRate;
			samples.push(Math.sin(2 * Math.PI * frequency * t) * amplitude);
		}
	};
	const addSilence = (units: number) => {
		for (let i = 0; i < units * unit * sampleRate; i++) {
			samples.push(0);
		}
	};

	for (const symbol of sequence) {
		if (symbol === '.') {
			addTone(1);
			addSilence(1);
		} else if (symbol === '-') {
			addTone(3);
			addSilence(1);
		} else if (symbol === ' ') {
			addSilence(3);
		}
	}

	const buffer = new ArrayBuffer(44 + samples.length * 2);
	const view = new DataView(buffer);
	const writeString = (offset: number, str: string) => {
		for (let i = 0; i < str.length; i++) {
			view.setUint8(offset + i, str.charCodeAt(i));
		}
	};

	// Cabecera WAV PCM 16-bit mono
	writeString(0, 'RIFF');
	view.setUint32(4, 36 + samples.length * 2, true);
	writeString(8, 'WAVE');
	writeString(12, 'fmt ');
	view.setUint32(16, 16, true);
	view.setUint16(20, 1, true);
	view.setUint16(22, 1, true);
	view.setUint32(24, sampleRate, true);
	view.setUint32(28, sampleRate * 2, true);
	view.setUint16(32, 2, true);
	view.setUint16(34, 16, true);
	writeString(36, 'data');
	view.setUint32(40, samples.length * 2, true);

	samples.forEach((s, i) => view.setInt16(44 + i * 2, s, true));

	return new Blob([view], { type: 'audio/wav' });
}

let cachedSilentBlobUrl = '';

export function getSilentBlobUrl(): string {
	if (!cachedSilentBlobUrl) {
		cachedSilentBlobUrl = URL.createObjectURL(createFaintNoiseBlob());
	}
	return cachedSilentBlobUrl;
}
