/**
 * Cliente HTTP do bridge V3 → chat externo.
 *
 * Pontos críticos:
 * - SEMPRE URL absoluta (V3_API_BASE). Path relativo cairia no catch-all
 *   do SvelteKit do lab e retornaria HTML com 200 OK (silent failure).
 * - credentials: 'include' pra mandar o cookie sf_token (httpOnly) do V3.
 * - Guard de content-type: se servidor devolver HTML/texto, joga erro claro
 *   em vez de tentar JSON.parse(html) silenciosamente.
 */

import { getV3ApiBase, SF_API_PATHS } from './config';
import type { SFClient } from './stores';

/**
 * Lê mirror_token do localStorage (gravado pelo SSO bridge). Retorna null
 * se vazio ou expirado. Token tem TTL 30min — depois disso o user
 * precisa abrir o Chat IA novamente pelo V3.
 */
function readMirrorToken(): string | null {
	if (typeof window === 'undefined') return null;
	try {
		const token = window.localStorage.getItem('sf_mirror_token');
		const expRaw = window.localStorage.getItem('sf_mirror_expires_at');
		if (!token) return null;
		if (expRaw) {
			const expMs = Date.parse(expRaw);
			if (Number.isFinite(expMs) && expMs <= Date.now()) {
				window.localStorage.removeItem('sf_mirror_token');
				window.localStorage.removeItem('sf_mirror_expires_at');
				return null;
			}
		}
		return token;
	} catch {
		return null;
	}
}

async function v3Fetch(path: string, init: RequestInit = {}): Promise<Response> {
	const base = getV3ApiBase();
	// Prioriza Bearer Authorization (mirror_token do SSO) porque cookie
	// sf_token do V3 não atravessa pra lab.socialforge.pro (origens
	// diferentes). Cai pra `credentials:include` como fallback caso o
	// user esteja com sessão ativa no V3 na mesma janela.
	const mirror = readMirrorToken();
	const extraHeaders: Record<string, string> = mirror ? { Authorization: `Bearer ${mirror}` } : {};
	return fetch(`${base}${path}`, {
		credentials: 'include',
		...init,
		headers: {
			Accept: 'application/json',
			...extraHeaders,
			...(init.headers || {})
		}
	});
}

async function v3FetchJson<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
	const res = await v3Fetch(path, init);
	const contentType = res.headers.get('content-type') || '';

	if (!res.ok) {
		let detail = '';
		try {
			detail = await res.text();
		} catch {
			/* ignore body read failure */
		}
		const err = new Error(`V3 API ${path} → HTTP ${res.status}: ${detail.slice(0, 200)}`) as Error & {
			status?: number;
		};
		err.status = res.status;
		throw err;
	}

	// Se vier HTML em vez de JSON, NÃO faz JSON.parse silencioso — joga erro
	// claro pro console pra capturar regressões de routing/CORS rapidamente.
	if (!contentType.includes('application/json')) {
		const peek = await res.text();
		throw new Error(
			`V3 API ${path} retornou content-type ${contentType || 'desconhecido'} ` +
				`(esperado application/json). Provável fetch caindo em catch-all. ` +
				`Início: ${peek.slice(0, 120)}`
		);
	}

	return (await res.json()) as T;
}

export async function listV3Clients(): Promise<SFClient[]> {
	const data = await v3FetchJson<{ ok: boolean; clients: SFClient[] }>(SF_API_PATHS.CLIENTS);
	if (!data.ok || !Array.isArray(data.clients)) {
		throw new Error('V3 /clients devolveu shape inesperado');
	}
	return data.clients;
}

export async function getTokenMirror(): Promise<{ mirror_token: string; expires_at: string }> {
	const data = await v3FetchJson<{
		ok: boolean;
		mirror_token: string;
		expires_at: string;
	}>(SF_API_PATHS.TOKEN_MIRROR);
	if (!data.ok) throw new Error('V3 token-mirror falhou');
	return { mirror_token: data.mirror_token, expires_at: data.expires_at };
}
