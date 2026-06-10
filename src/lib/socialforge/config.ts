/**
 * Config SocialForge no chat IA.
 *
 * V3_API_BASE: URL absoluta pra API do V3 (novo.socialforge.pro).
 * - Hardcoded de propósito: env var no build de Docker pode ficar vazia,
 *   gerando fetch relativo que cai no catch-all do SvelteKit (200 + HTML).
 * - Se precisar mudar pra staging/local, troca aqui e rebuilda.
 *
 * SF_SELECTED_CLIENT_KEY: chave do sessionStorage onde guardamos o id
 * do cliente selecionado. Só o id — nome/segmento são re-buscados
 * pra evitar staleness quando o V3 muda o nome do cliente.
 *
 * SF_API_PATHS: centraliza paths pra evitar string drift entre componentes.
 */

export const V3_API_BASE = 'https://novo.socialforge.pro';

export function getV3ApiBase(): string {
	return V3_API_BASE;
}

export const SF_SELECTED_CLIENT_KEY = 'socialforge:selectedClientId';

export const SF_API_PATHS = {
	CLIENTS: '/api/chat-ia/clients',
	CONTEXT_PACK: (id: string) => `/api/chat-ia/clients/${id}/context-pack`,
	SEARCH_KNOWLEDGE: (id: string) => `/api/chat-ia/clients/${id}/search-knowledge`,
	TOKEN_MIRROR: '/api/chat-ia/token-mirror',
	BALANCE: '/api/chat-ia/credits/balance',
	HISTORY: '/api/chat-ia/credits/history',
	BY_MODEL: '/api/chat-ia/credits/by-model',
	PRICING: '/api/chat-ia/credits/pricing'
} as const;
