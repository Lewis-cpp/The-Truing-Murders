import js from '@eslint/js'
import { defineConfig } from 'eslint/config'
import vue from 'eslint-plugin-vue'
import ts from 'typescript-eslint'
import globals from 'globals'

export default defineConfig(
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  ts.configs.recommended,
  vue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: ts.parser } },
  },
  {
    files: ['src/frontend/**/*.{ts,vue}', 'tests/frontend/**/*.ts'],
    languageOptions: { globals: globals.browser },
  },
)
