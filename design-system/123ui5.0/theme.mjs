export const UI5_VERSION = '5.0.0'

import { TOKENS } from './tokens.mjs'

export function themeTokens(mode = 'light') {
  return { ...(TOKENS[String(mode).toLowerCase() === 'dark' ? 'dark' : 'light'] || {}) }
}

export function actionGradient(mode = 'light') {
  const palette = themeTokens(mode)
  return `linear-gradient(135deg, ${palette.action_gradient_start}, ${palette.action_gradient_end})`
}
