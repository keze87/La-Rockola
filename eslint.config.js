import pluginVue from 'eslint-plugin-vue';
import js from '@eslint/js';
import globals from 'globals';
import eslintPluginPrettierRecommended from 'eslint-plugin-prettier/recommended';

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
                ...globals.browser, // <-- Esto inyecta automáticamente window, document, etc.
                process: 'readonly', // Puedes mantener process de Node si lo necesitas para entornos mixtos
            },
        },
        rules: {
            'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
            'no-unused-vars': 'warn',
            'vue/multi-word-component-names': 'off',
        },
    },

    // MUST BE LAST: This turns off conflicting ESLint layout rules
    // and flags formatting errors as ESLint issues automatically.
    eslintPluginPrettierRecommended,
];
