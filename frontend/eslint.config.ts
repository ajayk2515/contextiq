import eslint from '@eslint/js'
import eslintConfigPrettier from '@vue/eslint-config-prettier'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/**', 'coverage/**'] },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  eslintConfigPrettier,
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      globals: {
        AbortController: 'readonly',
        HTMLElement: 'readonly',
        sessionStorage: 'readonly',
        window: 'readonly',
      },
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
)
