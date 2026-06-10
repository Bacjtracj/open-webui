<script lang="ts">
	import { onMount } from 'svelte';
	import { selectedClientId, clients, type SFClient } from '$lib/socialforge/stores';
	import { listV3Clients } from '$lib/socialforge/api';

	let loading = false;
	let error: string | null = null;
	let open = false;
	let filter = '';

	// Popover usa position:fixed pra escapar de containers ancestrais com
	// overflow:hidden (ex: o wrapper flex-1.overflow-hidden.max-w-full do
	// Navbar.svelte do Open WebUI clipava verticalmente em ~45px). Coordenadas
	// calculadas no toggle a partir do bounding rect do botão.
	let btnEl: HTMLButtonElement | null = null;
	let popoverTop = 0;
	let popoverRight = 0;

	function recalcPopoverPosition() {
		if (!btnEl) return;
		const r = btnEl.getBoundingClientRect();
		popoverTop = r.bottom + 4; // 4px gap
		popoverRight = window.innerWidth - r.right;
	}

	$: filtered = (filter
		? $clients.filter((c) => c.name.toLowerCase().includes(filter.toLowerCase()))
		: $clients
	).slice(0, 30);
	$: current = $clients.find((c) => c.id === $selectedClientId) || null;

	async function load() {
		loading = true;
		error = null;
		try {
			const list = await listV3Clients();
			clients.set(list);
			if ($selectedClientId && !list.some((c: SFClient) => c.id === $selectedClientId)) {
				selectedClientId.set(null);
			}
		} catch (e) {
			const err = e as Error & { status?: number };
			error =
				err.status === 401
					? 'Faça login no V3 (novo.socialforge.pro)'
					: `Erro ao carregar clientes: ${err.message}`;
		} finally {
			loading = false;
		}
	}

	function pick(id: string | null) {
		selectedClientId.set(id);
		open = false;
		filter = '';
	}

	function toggle() {
		open = !open;
		if (open) {
			recalcPopoverPosition();
			if ($clients.length === 0 && !loading) load();
		}
	}

	function handleWindowChange() {
		if (open) recalcPopoverPosition();
	}

	onMount(() => {
		if ($clients.length === 0) load();
		window.addEventListener('resize', handleWindowChange);
		window.addEventListener('scroll', handleWindowChange, true);
		return () => {
			window.removeEventListener('resize', handleWindowChange);
			window.removeEventListener('scroll', handleWindowChange, true);
		};
	});
</script>

<div class="relative">
	<button
		type="button"
		bind:this={btnEl}
		on:click={toggle}
		class="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium
		       text-gray-600 dark:text-gray-300
		       hover:bg-gray-100 dark:hover:bg-gray-850 transition max-w-[200px]"
		title={current ? `Cliente ativo: ${current.name}` : 'Selecionar cliente do SocialForge'}
	>
		<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4" />
		</svg>
		<span class="truncate">
			{current ? current.name : 'Sem cliente'}
		</span>
		<svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0 opacity-60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<polyline points="6 9 12 15 18 9" />
		</svg>
	</button>

	{#if open}
		<button
			type="button"
			class="fixed inset-0 z-40 cursor-default"
			aria-label="Fechar"
			on:click={() => (open = false)}
		/>
		<div
			class="fixed z-50 min-w-[260px] max-w-[320px]
			       bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800
			       rounded-xl shadow-lg overflow-hidden"
			style="top: {popoverTop}px; right: {popoverRight}px;"
		>
			<div class="p-2 border-b border-gray-100 dark:border-gray-800">
				<input
					type="text"
					placeholder="Buscar cliente…"
					bind:value={filter}
					class="w-full px-2 py-1 text-sm rounded-md bg-gray-50 dark:bg-gray-850
					       border border-transparent focus:border-gray-300 dark:focus:border-gray-700
					       focus:outline-none"
				/>
			</div>

			<div class="max-h-[300px] overflow-y-auto">
				{#if loading}
					<div class="px-3 py-4 text-xs text-gray-500 text-center">Carregando…</div>
				{:else if error}
					<div class="px-3 py-3 text-xs text-red-600 dark:text-red-400">{error}</div>
					<button
						type="button"
						class="w-full px-3 py-2 text-xs text-left hover:bg-gray-50 dark:hover:bg-gray-850"
						on:click={load}
					>
						Tentar de novo
					</button>
				{:else}
					<button
						type="button"
						class="w-full px-3 py-2 text-xs text-left hover:bg-gray-50 dark:hover:bg-gray-850
						       text-gray-500 italic border-b border-gray-100 dark:border-gray-800"
						on:click={() => pick(null)}
					>
						(nenhum — chat sem contexto)
					</button>
					{#each filtered as c (c.id)}
						<button
							type="button"
							class="w-full px-3 py-2 text-sm text-left flex items-center justify-between gap-2
							       hover:bg-gray-50 dark:hover:bg-gray-850
							       {c.id === $selectedClientId ? 'bg-orange-50 dark:bg-orange-950/30' : ''}"
							on:click={() => pick(c.id)}
						>
							<span class="flex flex-col min-w-0">
								<span class="truncate font-medium">{c.name}</span>
								{#if c.segment}
									<span class="truncate text-[10px] text-gray-500">{c.segment}</span>
								{/if}
							</span>
							{#if c.has_pack}
								<span
									class="shrink-0 text-[9px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
									title="Contexto destilado pronto"
								>
									pack
								</span>
							{/if}
						</button>
					{:else}
						<div class="px-3 py-4 text-xs text-gray-500 text-center">Nenhum cliente.</div>
					{/each}
				{/if}
			</div>
		</div>
	{/if}
</div>
