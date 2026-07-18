import pluginVue from 'eslint-plugin-vue';
import js from '@eslint/js';

export default [
	// 1. GLOBAL IGNORES (Must be an object with ONLY an 'ignores' key)
	{
		ignores: ['dist/**', 'node_modules/**'],
	},

	// 2. Your existing configurations
	js.configs.recommended,
	...pluginVue.configs['flat/recommended'],

	{
		files: ['**/*.js', '**/*.vue'],
		languageOptions: {
			ecmaVersion: 'latest',
			sourceType: 'module',
			globals: {
				window: 'readonly',
				document: 'readonly',
				process: 'readonly',
			},
		},
		rules: {
			'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
			'no-unused-vars': 'warn',
			'vue/multi-word-component-names': 'off',
		},
	},
];