/**
 * Stores globais do SocialForge no chat (selectedClient + lista cacheada).
 *
 * Persistimos só o ID em sessionStorage (não o objeto inteiro, pra evitar dados
 * estagnados quando o nome do cliente muda no V3). A lista é re-buscada em cada
 * mount do ClientSelector.
 */
import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { SF_SELECTED_CLIENT_KEY } from './config';

export type SFClient = {
	id: string;
	name: string;
	segment?: string | null;
	instagram_handle?: string | null;
	has_pack?: boolean;
};

/**
 * Hidratação inicial do selectedClientId — duas fontes em ordem de prioridade:
 *   1. ?sf_client_id= na query string — vem do SSO bridge do V3
 *      ("Estúdio IA" no workspace, /sso?token=... redireciona pra
 *      /?sf_client_id=<uuid>&sf_client_name=...).
 *   2. sessionStorage — preserva escolha entre navegações na mesma aba.
 *
 * Quando a URL traz cliente, gravamos no sessionStorage pra que reloads
 * na mesma aba mantenham a seleção mesmo sem a query.
 */
function initialClientId(): string | null {
	if (typeof window === 'undefined') return null;
	try {
		const params = new URLSearchParams(window.location.search);
		const fromUrl = params.get('sf_client_id');
		if (fromUrl) {
			try {
				window.sessionStorage.setItem(SF_SELECTED_CLIENT_KEY, fromUrl);
			} catch {
				/* sessionStorage indisponível, segue só com a query */
			}
			return fromUrl;
		}
	} catch {
		/* URLSearchParams falhou, cai pro sessionStorage */
	}
	try {
		return window.sessionStorage.getItem(SF_SELECTED_CLIENT_KEY);
	} catch {
		return null;
	}
}

// Init com null sempre. O valor real (URL ou sessionStorage) é carregado
// no client após hydration via `browser` flag — caso contrário o módulo
// avalia em SSR (window undefined), retorna null, e o estado vai pra
// hidration cliente já como null, ignorando sf_client_id da URL.
export const selectedClientId = writable<string | null>(null);
export const clients = writable<SFClient[]>([]);

if (browser) {
	const initial = initialClientId();
	if (initial) selectedClientId.set(initial);
}

selectedClientId.subscribe((id) => {
	if (typeof window === 'undefined') return;
	try {
		if (id) window.sessionStorage.setItem(SF_SELECTED_CLIENT_KEY, id);
		else window.sessionStorage.removeItem(SF_SELECTED_CLIENT_KEY);
	} catch {
		/* sessionStorage indisponível, segue com store em memória */
	}
});
