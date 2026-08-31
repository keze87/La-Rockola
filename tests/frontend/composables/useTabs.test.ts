import { describe, it, expect } from 'vitest';
import { useTabs } from '@/composables/player/useTabs';
import { activeTab } from '@/composables/player/state';

describe('useTabs', () => {
	it('switches activeTab reactively', () => {
		const { switchTab } = useTabs();

		switchTab('queue');
		expect(activeTab.value).toBe('queue');

		switchTab('controls');
		expect(activeTab.value).toBe('controls');

		switchTab('library');
		expect(activeTab.value).toBe('library');
	});
});
