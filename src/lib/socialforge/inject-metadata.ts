/**
 * Fetch interceptor que injeta metadata SocialForge no body de qualquer
 * completion (chat/completions, ollama/api/chat, etc).
 *
 * Por que injetar no body em vez de header HTTP:
 *   o context_injector.py do Open WebUI é uma Filter Function — recebe
 *   {body, __user__} pelo runtime de Functions, NÃO o Request. Headers
 *   HTTP custom ficam invisíveis dentro do inlet. Injetando em
 *   body.metadata.sf, o inlet vê de graça.
 *
 * O que injeta:
 *   body.metadata.sf = {
 *     client_id: <uuid|null>,           // do ClientSelector
 *     mirror_token: <jwt curto>,        // pro Python falar com /chat-ia/* no V3
 *     mirror_expires_at: <iso>,         // pra renovar antes de expirar
 *   }
 *
 * Mirror token:
 *   - cacheado em memória + sessionStorage
 *   - renovado quando faltam <5min pra expirar
 *   - se renovação falha (V3 fora, sem cookie), seguimos sem mirror — o
 *     inlet vai simplesmente não injetar contexto. Chat normal continua.
 */

import { get } from 'svelte/store';
import { selectedClientId } from './stores';
import { getV3ApiBase } from './config';

const MIRROR_CACHE_KEY = 'socialforge:mirrorToken';
const MIRROR_EXPIRES_KEY = 'socialforge:mirrorTokenExpiresAt';
const RENEW_THRESHOLD_MS = 5 * 60 * 1000;

// URLs que DEVEM receber injeção (completions reais).
// Cobrimos /api/chat/completions (Open WebUI native), /ollama, /openai e
// /api/v1/tasks/* (utility completions tipo title gen — também rodam por
// model + se beneficiam do contexto). Functions/admin/auth ficam de fora.
const INJECT_PATH_PATTERNS = [
	/\/api\/chat\/completions(\?|$)/,
	/\/ollama\/api\/chat(\?|$)/,
	/\/ollama\/v1\/chat\/completions(\?|$)/,
	/\/openai\/chat\/completions(\?|$)/,
	/\/openai\/v1\/chat\/completions(\?|$)/,
	/\/api\/v1\/tasks\/[a-z_]+\/completions(\?|$)/
];

let inflightRenew: Promise<string | null> | null = null;
let installed = false;

function shouldInject(url: string): boolean {
	return INJECT_PATH_PATTERNS.some((re) => re.test(url));
}

function readCachedMirror(): { token: string | null; expiresAt: number | null } {
	if (typeof window === 'undefined') return { token: null, expiresAt: null };
	// Prioridade 1: sf_mirror_token do localStorage (gravado pelo SSO bridge).
	// Não expira aqui — o api.ts já valida e remove se vencido.
	try {
		const ssoToken = window.localStorage.getItem('sf_mirror_token');
		const ssoExpRaw = window.localStorage.getItem('sf_mirror_expires_at');
		if (ssoToken) {
			const expMs = ssoExpRaw ? Date.parse(ssoExpRaw) : null;
			if (!expMs || expMs > Date.now()) {
				return { token: ssoToken, expiresAt: expMs };
			}
			// expirado — limpa
			window.localStorage.removeItem('sf_mirror_token');
			window.localStorage.removeItem('sf_mirror_expires_at');
		}
	} catch {
		/* segue pro fallback sessionStorage */
	}
	// Prioridade 2: sessionStorage (renovado via cookie sf_token quando funciona).
	try {
		const token = window.sessionStorage.getItem(MIRROR_CACHE_KEY);
		const expiresRaw = window.sessionStorage.getItem(MIRROR_EXPIRES_KEY);
		return {
			token: token || null,
			expiresAt: expiresRaw ? Number(expiresRaw) : null
		};
	} catch {
		return { token: null, expiresAt: null };
	}
}

function writeMirror(token: string, expiresAtIso: string): void {
	if (typeof window === 'undefined') return;
	try {
		window.sessionStorage.setItem(MIRROR_CACHE_KEY, token);
		window.sessionStorage.setItem(
			MIRROR_EXPIRES_KEY,
			String(Date.parse(expiresAtIso) || Date.now() + 30 * 60_000)
		);
	} catch {
		/* sessionStorage indisponível, vai re-fetch a cada turno */
	}
}

async function fetchMirrorToken(): Promise<string | null> {
	if (inflightRenew) return inflightRenew;
	inflightRenew = (async () => {
		try {
			const res = await fetch(`${getV3ApiBase()}/api/chat-ia/token-mirror`, {
				credentials: 'include'
			});
			if (!res.ok) return null;
			const data = await res.json();
			if (!data?.mirror_token || !data?.expires_at) return null;
			writeMirror(data.mirror_token, data.expires_at);
			return data.mirror_token as string;
		} catch {
			return null;
		} finally {
			inflightRenew = null;
		}
	})();
	return inflightRenew;
}

async function getMirrorToken(): Promise<string | null> {
	const { token, expiresAt } = readCachedMirror();
	const valid = token && expiresAt && expiresAt - Date.now() > RENEW_THRESHOLD_MS;
	if (valid) return token;
	return fetchMirrorToken();
}

/**
 * Patcha o objeto body (parsed) com metadata.sf.
 * Não muta se já existe metadata.sf.client_id (idempotente em re-runs).
 */
function patchBody(parsed: any, clientId: string | null, mirrorToken: string | null): any {
	if (!parsed || typeof parsed !== 'object') return parsed;
	// Open WebUI sobrescreve body.metadata com construct próprio (whitelist) —
	// metadata.sf é descartado mas variables vai pra metadata.variables.
	const variables = (parsed.variables && typeof parsed.variables === 'object') ? parsed.variables : {};
	const sf = (variables.sf && typeof variables.sf === 'object') ? variables.sf : {};
	const { expiresAt } = readCachedMirror();
	const sfPayload = {
		...sf,
		client_id: clientId,
		mirror_token: mirrorToken,
		mirror_expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
		source: 'sf-v3-bridge'
	};
	parsed.variables = { ...variables, sf: sfPayload };
	// Belt-and-suspenders: também grava em metadata pra rotas que não passam
	// pelo construtor whitelist (ex.: /openai proxy direto).
	const metadata = (parsed.metadata && typeof parsed.metadata === 'object') ? parsed.metadata : {};
	parsed.metadata = { ...metadata, sf: sfPayload };
	return parsed;
}

/**
 * Reescreve init.body pra incluir metadata.sf.
 * Suporta body=string, body=ArrayBuffer (codificado), body=FormData (pula).
 */
async function rewriteInit(init: RequestInit | undefined): Promise<RequestInit | undefined> {
	if (!init || init.body == null) return init;
	const ct = new Headers(init.headers || {}).get('content-type') || '';
	if (!ct.toLowerCase().includes('application/json')) return init;

	let raw: string | null = null;
	if (typeof init.body === 'string') raw = init.body;
	else if (init.body instanceof ArrayBuffer) raw = new TextDecoder().decode(init.body);
	else if (ArrayBuffer.isView(init.body)) raw = new TextDecoder().decode(init.body.buffer);
	else return init;

	let parsed: any;
	try {
		parsed = JSON.parse(raw);
	} catch {
		return init;
	}

	const clientId = get(selectedClientId);
	const mirror = await getMirrorToken();
	const patched = patchBody(parsed, clientId, mirror);
	return { ...init, body: JSON.stringify(patched) };
}

/**
 * Instala o interceptor uma vez. Idempotente.
 * Chamar em +layout.svelte com onMount.
 */
export function installSocialForgeFetchInterceptor(): void {
	if (installed || typeof window === 'undefined' || !window.fetch) return;
	installed = true;

	const original = window.fetch.bind(window);
	window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
		try {
			const url = typeof input === 'string'
				? input
				: input instanceof URL
				? input.toString()
				: input.url;
			if (!shouldInject(url)) return original(input as any, init);
			const newInit = await rewriteInit(init);
			const res = await original(input as any, newInit);
			// Dispara refresh da barrinha de créditos. Pra streams, ~2s cobre o
			// settle típico do filter outlet (que roda async em background).
			// CreditBar dedupea via comparação de valores; chamar 2x não custa.
			if (typeof window !== 'undefined') {
				setTimeout(() => {
					window.dispatchEvent(new CustomEvent('sf-credits-changed'));
				}, 2000);
			}
			return res;
		} catch {
			return original(input as any, init);
		}
	}) as typeof window.fetch;
}
