/**
 * Pruebas end-to-end (E2E) aisladas para La Rockola del Carpincho.
 * Cubre carga de biblioteca musical aislada, búsqueda en tiempo real, favoritos con
 * persistencia real en SQLite, cola de reproducción (La Ronda) y navegación entre pestañas.
 * Uso: npm run test:e2e (desde La Rockola del Carpincho).
 */

import { expect, test } from '@playwright/test';

async function resetBackend(request: import('@playwright/test').APIRequestContext) {
	const res = await request.post('/api/test/reset');
	expect(res.ok()).toBeTruthy();
}

test.describe('La Rockola del Carpincho E2E', () => {
	test.beforeEach(async ({ request }) => {
		await resetBackend(request);
	});

	test('carga la biblioteca temporal y filtra temas desde el buscador', async ({ page }) => {
		await page.goto('/');

		await expect(page.getByText('01 - Mate en el Fogón')).toBeVisible();
		await expect(page.getByText('02 - Carpincho Blues')).toBeVisible();
		await expect(page.getByText('03 - Siesta en el Río')).toBeVisible();

		const searchInput = page.getByPlaceholder("Buscá un buen tema pa' acompañar los mates...");
		await searchInput.fill('Blues');

		await expect(page.getByText('02 - Carpincho Blues')).toBeVisible();
		await expect(page.getByText('01 - Mate en el Fogón')).toHaveCount(0);

		await searchInput.fill('');
		await expect(page.getByText('01 - Mate en el Fogón')).toBeVisible();
	});

	test('marca un tema como favorito, filtra favoritos y persiste tras recargar', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByText('02 - Carpincho Blues')).toBeVisible();

		// Filtramos para ubicar inequívocamente Carpincho Blues y tocamos su botón de favorito
		const searchInput = page.getByPlaceholder("Buscá un buen tema pa' acompañar los mates...");
		await searchInput.fill('Blues');
		await page.getByRole('button', { name: 'Agregar a favoritos' }).first().click();
		await searchInput.fill('');

		// Activamos el filtro "Mostrar sólo favoritos"
		await page.getByTitle('Mostrar sólo favoritos').click();
		await expect(page.getByText('02 - Carpincho Blues')).toBeVisible();
		await expect(page.getByText('01 - Mate en el Fogón')).toHaveCount(0);

		// Recargamos la página y comprobamos que el favorito sigue guardado en SQLite
		await page.reload();
		await page.getByTitle('Mostrar sólo favoritos').click();
		await expect(page.getByText('02 - Carpincho Blues')).toBeVisible();
		await expect(page.getByText('01 - Mate en el Fogón')).toHaveCount(0);
	});

	test('agrega un tema a La Ronda, navega entre pestañas y verifica estado', async ({ page, request }) => {
		const libRes = await request.get('/library');
		expect(libRes.ok()).toBeTruthy();
		const libJson = (await libRes.json()) as { data: Array<{ path: string; title: string }> };
		expect(libJson.data.length).toBeGreaterThanOrEqual(3);

		const targetTrack = libJson.data.find((t) => t.path.includes('Mate en el Fog')) ?? libJson.data[0];

		const addRes = await request.post('/command', {
			data: { cmd: 'toggle_queue', path: targetTrack.path },
		});
		expect(addRes.ok()).toBeTruthy();

		await page.goto('/');

		// Vamos a La Ronda (cola)
		await page.getByText('La Ronda').click();
		await expect(page.getByText(targetTrack.title).first()).toBeVisible();

		// Limpiamos la cola vía API y validamos que las demás pestañas respondan bien
		const clearRes = await request.post('/command', {
			data: { cmd: 'clear_queue' },
		});
		expect(clearRes.ok()).toBeTruthy();

		await page.getByText('Los Clásicos').click();
		await page.getByText('Las Perillas').click();
		await page.getByText('Los Temazos').click();
		await expect(page.getByText('03 - Siesta en el Río')).toBeVisible();
	});
});
