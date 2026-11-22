import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = path.resolve(process.cwd(), 'src');

function collectSourceFiles(dir: string): string[] {
	const results: string[] = [];
	for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
		const full = path.join(dir, entry.name);
		if (entry.isDirectory()) {
			results.push(...collectSourceFiles(full));
		} else if (entry.name.endsWith('.ts') || entry.name.endsWith('.vue')) {
			results.push(full);
		}
	}
	return results;
}

function resolveImportTarget(fromFile: string, specifier: string): string | null {
	let base: string | null = null;
	if (specifier.startsWith('./') || specifier.startsWith('../')) {
		base = path.resolve(path.dirname(fromFile), specifier);
	} else if (specifier.startsWith('@/')) {
		base = path.resolve(SRC_ROOT, specifier.slice(2));
	}
	if (!base) return null;

	const candidates = [base, `${base}.ts`, `${base}.vue`, path.join(base, 'index.ts')];
	for (const c of candidates) {
		if (fs.existsSync(c) && fs.statSync(c).isFile()) {
			return c;
		}
	}
	return null;
}

function extractStaticImports(filePath: string): string[] {
	const content = fs.readFileSync(filePath, 'utf-8');
	const imports: string[] = [];
	const regex = /(?:^|\n)\s*import\s+(?!type\b)[\s\S]*?\bfrom\s+['"]([^'"]+)['"]/g;
	for (const match of content.matchAll(regex)) {
		const resolved = resolveImportTarget(filePath, match[1]);
		if (resolved) imports.push(resolved);
	}
	return imports;
}

describe('Grafo de imports en src/', () => {
	it('no contiene ciclos de imports estáticos', () => {
		const files = collectSourceFiles(SRC_ROOT);
		const graph = new Map<string, string[]>();
		for (const file of files) {
			graph.set(file, extractStaticImports(file));
		}

		const state = new Map<string, 'visiting' | 'visited'>();
		const cycles: string[] = [];

		function dfs(node: string, stack: string[]) {
			state.set(node, 'visiting');
			for (const next of graph.get(node) ?? []) {
				const nextState = state.get(next);
				if (nextState === 'visiting') {
					const idx = stack.indexOf(next);
					const cycle = [...stack.slice(idx), next].map((p) => path.relative(SRC_ROOT, p));
					cycles.push(cycle.join(' -> '));
				} else if (!nextState) {
					dfs(next, [...stack, next]);
				}
			}
			state.set(node, 'visited');
		}

		for (const file of files) {
			if (!state.get(file)) {
				dfs(file, [file]);
			}
		}

		expect(cycles).toEqual([]);
	});
});
