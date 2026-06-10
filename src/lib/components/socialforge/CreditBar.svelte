<script lang="ts">
	/**
	 * Pill de créditos no header (Navbar do chat).
	 *
	 * Refeito em 2026-05-16: antes estava 37×5px e ilegível. Agora é um pill
	 * ~32px alto com barra de 8px e texto text-xs, com transição suave e
	 * a11y via role="progressbar". Cores escalam por consumo: laranja-marca
	 * até 70%, amber 70–90%, red >90%.
	 *
	 * Polling 30s + escuta 'sf-credits-changed' (disparado por inject-metadata
	 * após completion). Falha em silêncio: 401 = sem assinatura (some), erro
	 * de rede = mostra "!".
	 */
	import { onMount, onDestroy } from 'svelte';
	import { getV3ApiBase, SF_API_PATHS } from '$lib/socialforge/config';

	type Balance = {
		total_credits: number;
		used_credits: number;
		available_credits: number;
		used_pct: number | string;
		days_until_reset: number | string;
	};

	let balance: Balance | null = null;
	let loading = true;
	let error: string | null = null;
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	async function fetchBalance() {
		try {
			const res = await fetch(`${getV3ApiBase()}${SF_API_PATHS.BALANCE}`, {
				credentials: 'include'
			});
			if (!res.ok) {
				if (res.status === 401) {
					balance = null;
					error = null;
					return;
				}
				throw new Error(`HTTP ${res.status}`);
			}
			const data = await res.json();
			balance = data.balance || null;
			error = null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	function handleCreditsChanged() {
		fetchBalance();
	}

	onMount(() => {
		fetchBalance();
		pollTimer = setInterval(fetchBalance, 30_000);
		if (typeof window !== 'undefined') {
			window.addEventListener('sf-credits-changed', handleCreditsChanged);
		}
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
		if (typeof window !== 'undefined') {
			window.removeEventListener('sf-credits-changed', handleCreditsChanged);
		}
	});

	$: usedPct = balance ? Math.min(Math.max(Number(balance.used_pct) || 0, 0), 100) : 0;
	// Bar preenche o DISPONÍVEL em laranja-marca. Conforme o user usa, encolhe.
	// Próximo do limite, muda pra amber/red pra alertar.
	$: availablePct = balance ? Math.max(0, 100 - usedPct) : 0;
	$: fillClass =
		usedPct > 90
			? 'bg-red-500 dark:bg-red-500'
			: usedPct > 70
				? 'bg-amber-500 dark:bg-amber-500'
				: 'bg-orange-500 dark:bg-orange-500';
	$: daysToReset = balance
		? Math.max(0, Math.floor(Number(balance.days_until_reset) || 0))
		: 0;
	$: title = balance
		? `${balance.available_credits.toLocaleString('pt-BR')} créditos disponíveis · renova em ${daysToReset} dia(s)`
		: error
			? `Erro ao carregar créditos: ${error}`
			: 'Sem assinatura ativa';
	$: ariaLabel = balance
		? `${balance.used_credits} de ${balance.total_credits} créditos usados`
		: 'Créditos indisponíveis';
</script>

{#if loading}
	<div
		class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400"
		title="Carregando créditos…"
	>
		<span class="inline-block w-1.5 h-1.5 rounded-full bg-current opacity-40"></span>
	</div>
{:else if error}
	<div
		class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-50 dark:bg-red-950/40 text-xs font-semibold text-red-600 dark:text-red-300"
		{title}
	>
		!
	</div>
{:else if balance}
	<div
		class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-gray-800"
		{title}
	>
		<div
			class="relative h-2 w-28 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden"
			role="progressbar"
			aria-valuenow={balance.used_credits}
			aria-valuemin="0"
			aria-valuemax={balance.total_credits}
			aria-label={ariaLabel}
		>
			<div
				class="absolute inset-y-0 left-0 {fillClass} transition-[width] duration-300 ease-out"
				style={`width: ${availablePct}%`}
			></div>
		</div>
		<span
			class="text-xs font-medium text-gray-700 dark:text-gray-200 tabular-nums whitespace-nowrap"
		>
			{balance.available_credits.toLocaleString('pt-BR')}<span class="opacity-40 mx-0.5"
				>/</span
			>{balance.total_credits.toLocaleString('pt-BR')}
		</span>
	</div>
{:else}
	<div
		class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-gray-800 text-xs text-gray-400 dark:text-gray-500"
		title="Sem assinatura ativa"
	>
		—
	</div>
{/if}
