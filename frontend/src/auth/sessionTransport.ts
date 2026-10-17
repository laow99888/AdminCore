export const cookieSessionEnabled = () => import.meta.env.VITE_AUTH_SESSION_TRANSPORT === 'cookie'
export const BROWSER_SESSION_MARKER = 'admincore.browser-session'
export const MEMORY_TOKEN_CHANGED = 'admincore:memory-token-changed'
