import { ref, computed, type Ref } from 'vue';

interface LyricLine {
	time: number;
	text: string;
}

const lyrics = ref<LyricLine[]>([]);

export function useLyrics(player: { localTimePos: Ref<number> }) {
	const currentLyricLine = computed(() => {
		if (!lyrics.value || !lyrics.value.length) return null;

		const activeLine = ' ';
		for (let i = lyrics.value.length - 1; i >= 0; i--) {
			// Syncs against the player's localTimePos
			if (player.localTimePos.value >= lyrics.value[i].time) {
				return lyrics.value[i].text;
			}
		}
		return activeLine;
	});

	async function loadLyrics(path: string | null) {
		lyrics.value = []; // Clear immediately on track change
		if (!path || path.startsWith('http')) return;

		try {
			const res = await fetch('/lrc?path=' + encodeURIComponent(path));

			if (res.ok) {
				const text = await res.text();
				parseLrc(text);
			}
		} catch (err) {
			console.error('Pifió buscando las lyrics, maestro:', err);
		}
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

		// Chronological sorting
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
					// If the instrumental gap is 2 seconds or more, keep blank space
					if (nextValidTime - current.time >= 2) {
						finalParsed.push(current);
					} else if (nextValidTime - current.time >= 1) {
						// If the gap is between 1s and 2s, insert the carpincho emoji
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

	return { currentLyricLine, loadLyrics, lyrics };
}
