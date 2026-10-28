import { ref, computed, type Ref } from 'vue';
import { apiUrl } from './useApi';

export interface LyricSyllable {
	text: string;
	start: number;
	end: number;
}

export interface LyricLine {
	time: number;
	endTime?: number;
	text: string;
	syllables?: LyricSyllable[];
}

const lyrics = ref<LyricLine[]>([]);
let currentLoadedPath: string | null = null;
let currentFetchPromise: Promise<void> | null = null;

/**
 * Parsea el tiempo del subtítulo ASS (h:mm:ss.cs o hh:mm:ss.cs) a segundos con coma.
 */
export function parseAssTime(timeStr: string): number {
	if (!timeStr) return 0;
	const parts = timeStr.trim().split(':');
	if (parts.length === 3) {
		const hours = parseFloat(parts[0]) || 0;
		const minutes = parseFloat(parts[1]) || 0;
		const seconds = parseFloat(parts[2]) || 0;
		return Math.round((hours * 3600 + minutes * 60 + seconds) * 100) / 100;
	} else if (parts.length === 2) {
		const minutes = parseFloat(parts[0]) || 0;
		const seconds = parseFloat(parts[1]) || 0;
		return Math.round((minutes * 60 + seconds) * 100) / 100;
	}
	return Math.round((parseFloat(timeStr) || 0) * 100) / 100;
}

/**
 * Divide la línea de ASS respetando que el último campo (Text) puede contener comas a rolete.
 */
export function splitAssFields(line: string, numFields: number): string[] {
	const result: string[] = [];
	let current = '';
	let count = 0;
	for (let i = 0; i < line.length; i++) {
		const char = line[i];
		if (char === ',' && count < numFields - 1) {
			result.push(current.trim());
			current = '';
			count++;
		} else {
			current += char;
		}
	}
	result.push(current);
	return result;
}

/**
 * Parsea el texto del evento de ASS para extraer texto limpio y los bloques \kf de sílabas.
 */
export function parseAssText(
	rawText: string,
	startTime: number,
	endTime: number
): { cleanText: string; syllables: LyricSyllable[] } {
	// Limpiamos los saltos de línea de ASS y cualquier estilo entre llaves para el texto plano
	const cleanText = rawText
		.replace(/\\N/gi, ' ')
		.replace(/\\h/gi, ' ')
		.replace(/\{[^}]*\}/g, '')
		.trim();

	const tokenRegex = /(\{[^}]*\})|([^{]+)/g;
	let match: RegExpExecArray | null;
	let currentTime = startTime;
	let pendingDuration: number | null = null;
	const syllables: LyricSyllable[] = [];

	while ((match = tokenRegex.exec(rawText)) !== null) {
		const tagBlock = match[1];
		const textChunk = match[2];

		if (tagBlock) {
			// Soporta \kf, \ko, \k y \K seguidos por la duración en centésimas de segundo
			const kMatch = /\\k[f|o]?(\d+)/i.exec(tagBlock) || /\\K(\d+)/.exec(tagBlock);
			if (kMatch) {
				pendingDuration = parseInt(kMatch[1], 10) / 100;
			}
		} else if (textChunk) {
			const cleanChunk = textChunk.replace(/\\N/gi, ' ').replace(/\\h/gi, ' ');
			if (cleanChunk.length > 0) {
				if (cleanChunk.trim() === '') {
					// Espacio en blanco entre palabras: si viene tras una sílaba, adjuntamos el espacio y su duración
					if (syllables.length > 0) {
						const prevSyl = syllables[syllables.length - 1];
						prevSyl.text += cleanChunk;
						if (pendingDuration !== null) {
							prevSyl.end = Math.round((prevSyl.end + pendingDuration) * 100) / 100;
							currentTime = prevSyl.end;
							pendingDuration = null;
						}
					} else if (pendingDuration !== null) {
						currentTime = Math.round((currentTime + pendingDuration) * 100) / 100;
						pendingDuration = null;
					}
				} else {
					const sylStart = Math.round(currentTime * 100) / 100;
					const sylDuration = pendingDuration !== null ? pendingDuration : Math.max(0, endTime - currentTime);
					const sylEnd = Math.round((sylStart + sylDuration) * 100) / 100;

					syllables.push({
						text: cleanChunk,
						start: sylStart,
						end: sylEnd,
					});

					currentTime = sylEnd;
					pendingDuration = null;
				}
			}
		}
	}

	if (pendingDuration !== null && syllables.length > 0) {
		const lastSyl = syllables[syllables.length - 1];
		lastSyl.end = Math.round((lastSyl.end + pendingDuration) * 100) / 100;
	}

	return { cleanText, syllables };
}

/**
 * Parsea un archivo de letras en formato ASS.
 */
export function parseAss(content: string): LyricLine[] {
	// Limpiamos BOM si viene al principio del archivo
	const cleanContent = content.replace(/^\uFEFF/, '');
	const lines = cleanContent.split(/\r?\n/);
	const parsed: LyricLine[] = [];
	let inEvents = false;
	let formatFields: string[] = [];

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i].trim();
		if (!line) continue;

		if (line.startsWith('[') && line.endsWith(']')) {
			inEvents = line.toLowerCase() === '[events]';
			continue;
		}

		if (!inEvents) continue;

		if (line.toLowerCase().startsWith('format:')) {
			formatFields = line
				.substring(7)
				.split(',')
				.map((f) => f.trim().toLowerCase());
			continue;
		}

		if (line.toLowerCase().startsWith('dialogue:')) {
			const rawContent = line.substring(9).trim();
			const startIndex = formatFields.indexOf('start') !== -1 ? formatFields.indexOf('start') : 1;
			const endIndex = formatFields.indexOf('end') !== -1 ? formatFields.indexOf('end') : 2;
			const textIndex =
				formatFields.indexOf('text') !== -1
					? formatFields.indexOf('text')
					: formatFields.length > 0
						? formatFields.length - 1
						: 9;

			const numFields = Math.max(textIndex + 1, 10);
			const fields = splitAssFields(rawContent, numFields);

			const startStr = fields[startIndex] ?? '';
			const endStr = fields[endIndex] ?? '';
			const rawText = fields[textIndex] ?? '';

			const startTime = parseAssTime(startStr);
			const endTime = parseAssTime(endStr);

			const { cleanText, syllables } = parseAssText(rawText, startTime, endTime);

			if (cleanText) {
				parsed.push({
					time: startTime,
					endTime: endTime,
					text: cleanText,
					syllables: syllables.length > 0 ? syllables : undefined,
				});
			}
		}
	}

	// Ordenamos siempre cronológicamente de menor a mayor
	parsed.sort((a, b) => a.time - b.time);
	return parsed;
}

/**
 * Detecta si el texto corresponde a un archivo ASS o a un LRC común y corriente.
 */
export function isAssFormat(content: string): boolean {
	return content.includes('[Events]') || content.includes('[Script Info]') || content.includes('[V4+ Styles]');
}

export function useLyrics(player: { localTimePos: Ref<number> }) {
	const activeLyricLines = computed(() => {
		if (!lyrics.value || !lyrics.value.length) return [];
		const time = player.localTimePos.value;

		// Devolvemos todas las líneas reales que estén reproduciéndose en este momento (duetos, coros, etc.)
		return lyrics.value.filter((line, idx) => {
			if (!line.text || line.text.trim() === '' || line.text === ' ' || line.text === '🦦') {
				return false;
			}
			const start = line.time;
			const nextLine = lyrics.value[idx + 1];
			const rawEnd = line.endTime ?? (nextLine ? Math.min(nextLine.time, start + 8) : start + 8);
			const end = nextLine && nextLine.time - rawEnd < 1.0 && nextLine.time >= rawEnd ? nextLine.time : rawEnd;
			return time >= start && time <= end;
		});
	});

	const currentLyricLine = computed(() => {
		if (!lyrics.value || !lyrics.value.length) return null;

		const active = activeLyricLines.value;
		if (active.length > 0) {
			const texts = active.map((l) => l.text).filter((t) => t && t.trim() !== '' && t !== ' ' && t !== '🦦');
			if (texts.length > 0) {
				return texts.join(' / ');
			}
			return ' ';
		}

		const time = player.localTimePos.value;

		// Si todavía no arrancó la primera estrofa
		if (time < lyrics.value[0].time) {
			const gap = lyrics.value[0].time;
			if (gap >= 1.0 && gap < 2.0) {
				return '🦦';
			}
			return ' ';
		}

		// Encontramos el último verso que empezó en o antes de `time`
		let lastIdx = -1;
		for (let i = lyrics.value.length - 1; i >= 0; i--) {
			if (time >= lyrics.value[i].time) {
				lastIdx = i;
				break;
			}
		}

		if (lastIdx === -1) {
			return ' ';
		}

		const prevLine = lyrics.value[lastIdx];

		// Si la línea explícita en lyrics es un marcador de silencio de LRC
		if (prevLine.text === '🦦') {
			return '🦦';
		}
		if (prevLine.text === ' ' || !prevLine.text.trim()) {
			return ' ';
		}

		// Buscamos la siguiente línea de letra real
		let nextLine: LyricLine | null = null;
		for (let j = lastIdx + 1; j < lyrics.value.length; j++) {
			if (
				lyrics.value[j].text &&
				lyrics.value[j].text.trim() !== '' &&
				lyrics.value[j].text !== ' ' &&
				lyrics.value[j].text !== '🦦'
			) {
				nextLine = lyrics.value[j];
				break;
			}
		}

		const prevEnd = prevLine.endTime ?? (nextLine ? Math.min(nextLine.time, prevLine.time + 8) : prevLine.time + 8);

		// Si todavía estamos dentro de la ventana de reproducción del verso (ej. LRC sin endTime)
		if (time <= prevEnd) {
			return prevLine.text;
		}

		// La línea ya terminó de cantarse. Evaluamos la brecha de silencio hasta la próxima línea
		if (nextLine) {
			const gap = nextLine.time - prevEnd;
			if (gap >= 2.0) {
				// Silencio largo: volvemos al título de la canción
				return ' ';
			} else if (gap >= 1.0) {
				// Silencio corto: mostramos el emoji carpincho
				return '🦦';
			}
			return ' ';
		}

		// Si no hay siguiente línea (outro del tema tras la última estrofa)
		return ' ';
	});

	async function loadLyrics(path: string | null) {
		if (path === currentLoadedPath) {
			if (currentFetchPromise) await currentFetchPromise;
			return;
		}

		currentLoadedPath = path;
		lyrics.value = []; // Limpiamos al toque al cambiar de tema
		if (!path || path.startsWith('http')) return;

		const fetchTask = (async () => {
			try {
				const res = await fetch(apiUrl('/lrc?path=' + encodeURIComponent(path)));

				if (res.ok && typeof res.text === 'function') {
					const text = await res.text();
					if (currentLoadedPath === path) {
						if (isAssFormat(text)) {
							lyrics.value = parseAss(text);
						} else {
							parseLrc(text);
						}
					}
				}
			} catch (err) {
				console.error('Pifió buscando las lyrics, maestro:', err);
			} finally {
				if (currentLoadedPath === path) {
					currentFetchPromise = null;
				}
			}
		})();

		currentFetchPromise = fetchTask;
		await fetchTask;
	}

	function parseLrc(text: string) {
		const lines = text.split('\n');
		const parsed: LyricLine[] = [];
		const tagRegex = /\[\d{2}:\d{2}\.\d{2,3}\]/g;

		lines.forEach((line) => {
			const tags = line.match(tagRegex);

			if (tags) {
				const lyricText = line.replace(tagRegex, '').trim();
				tags.forEach((tag) => {
					const match = /\[(\d{2}):(\d{2})\.(\d{2,3})\]/.exec(tag);

					if (match) {
						const mins = parseInt(match[1], 10);
						const secs = parseInt(match[2], 10);
						const msStr = match[3];
						const ms = parseInt(msStr, 10) * (msStr.length === 2 ? 10 : 1);
						const timeInSeconds = mins * 60 + secs + ms / 1000;

						parsed.push({ time: timeInSeconds, text: lyricText || ' ' });
					}
				});
			}
		});

		// Orden cronológico
		parsed.sort((a, b) => a.time - b.time);

		const finalParsed: LyricLine[] = [];
		for (let i = 0; i < parsed.length; i++) {
			const current = parsed[i];

			if (current.text === ' ') {
				let nextValidTime: number | null = null;
				for (let j = i + 1; j < parsed.length; j++) {
					if (parsed[j].text !== ' ') {
						nextValidTime = parsed[j].time;
						break;
					}
				}

				if (nextValidTime !== null) {
					// Si el bache instrumental dura 2 segundos o más, dejamos espacio en blanco
					if (nextValidTime - current.time >= 2) {
						finalParsed.push(current);
					} else if (nextValidTime - current.time >= 1) {
						// Si el bache dura entre 1s y 2s, metemos el emoji de carpincho
						current.text = '🦦';
						finalParsed.push(current);
					}
				} else {
					finalParsed.push(current);
				}
			} else {
				finalParsed.push(current);
			}
		}

		lyrics.value = finalParsed;
	}

	return { currentLyricLine, activeLyricLines, loadLyrics, lyrics };
}
