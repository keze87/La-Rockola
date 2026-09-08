import eslintPluginPrettierRecommended from 'eslint-plugin-prettier/recommended';
import globals from 'globals';
import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import typescriptEslint from 'typescript-eslint';
import vueParser from 'vue-eslint-parser';

export default [
	// 1. GLOBAL IGNORES
	{ ignores: ['dist/**', 'node_modules/**'] },

	// 2. Existing configurations
	js.configs.recommended,
	...typescriptEslint.configs.recommended,
	...pluginVue.configs['flat/recommended'],

	{
		files: ['**/*.ts', '**/*.vue', '**/*.js'],
		languageOptions: {
			ecmaVersion: 'latest',
			sourceType: 'module',
			parser: vueParser,
			parserOptions: {
				parser: typescriptEslint.parser,
				extraFileExtensions: ['.vue'],
				sourceType: 'module',
			},
			globals: {
				...globals.browser, // <-- Esto inyecta automáticamente window, document, etc.
				...globals.node, // <-- Fixes 'process is not defined'
			},
		},
		rules: {
			'@typescript-eslint/no-explicit-any': 'error',
			'@typescript-eslint/no-unused-vars': 'warn',
			'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
			'no-unused-vars': 'off', // Let TS handle this
			'vue/multi-word-component-names': 'off',
		},
	},

	{
		files: ['tests/**/*.ts', 'tests/**/*.js'],
		rules: {
			// Allows mocking and testing invalid inputs without boilerplate
			'@typescript-eslint/no-explicit-any': 'off',

			// Catches forgotten assertions, but allows intentional unused params/vars prefixed with _
			'@typescript-eslint/no-unused-vars': [
				'warn',
				{
					argsIgnorePattern: '^_',
					varsIgnorePattern: '^_',
					caughtErrorsIgnorePattern: '^_',
				},
			],
		},
	},

	// MUST BE LAST: This turns off conflicting ESLint layout rules
	// and flags formatting errors as ESLint issues automatically.
	eslintPluginPrettierRecommended,
];
