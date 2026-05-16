<script lang="ts">
	import { config, user, models as _models, temporaryChatEnabled } from '$lib/stores';
	import { onMount, getContext } from 'svelte';
	import { fade } from 'svelte/transition';

	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let modelIds = [];
	export let models = [];
	export let atSelectedModel;
	export let onSelect = (e) => {};

	let mounted = false;
	$: models = modelIds.map((id) => $_models.find((m) => m.id === id));

	onMount(() => {
		mounted = true;
	});

	// SocialForge: saudação dinâmica por hora do dia
	function sfEmoji() {
		const h = new Date().getHours();
		if (h >= 5 && h < 12) return '☀️';
		if (h >= 12 && h < 18) return '🌤️';
		return '🌙';
	}
	function sfGreeting() {
		const h = new Date().getHours();
		if (h >= 5 && h < 12) return 'Bom dia';
		if (h >= 12 && h < 18) return 'Boa tarde';
		return 'Boa noite';
	}
</script>

{#key mounted}
	<div class="m-auto w-full max-w-6xl px-8 lg:px-20">
		{#if $temporaryChatEnabled}
			<Tooltip
				content={$i18n.t("This chat won't appear in history and your messages will not be saved.")}
				className="w-full flex justify-center mb-2"
				placement="top"
			>
				<div class="flex items-center gap-2 text-gray-500 text-base my-2 w-fit mx-auto">
					<EyeSlash strokeWidth="2.5" className="size-4" />{$i18n.t('Temporary Chat')}
				</div>
			</Tooltip>
		{/if}

		<div class="sf-hero" in:fade={{ duration: 200 }}>
			<h1 class="sf-greeting">
				{sfEmoji()} {sfGreeting()}, {($user?.name ?? '').split(' ')[0] || 'amigo'}
			</h1>
			<p class="sf-subtitle">
				Escolha o cliente, me diga o objetivo e eu transformo a ideia em estratégia, conteúdo, relatório ou campanha pronta para executar.
			</p>
			<div class="sf-cards">
				<div class="sf-card"><div class="sf-card-icon">🔍</div><div class="sf-card-title">Análise de perfil</div><div class="sf-card-desc">Bio, posicionamento, autoridade e conversão.</div></div>
				<div class="sf-card"><div class="sf-card-icon">📊</div><div class="sf-card-title">Criar relatório</div><div class="sf-card-desc">Insights, SWOT, diagnóstico e próximos passos.</div></div>
				<div class="sf-card"><div class="sf-card-icon">🌐</div><div class="sf-card-title">Pesquisar nicho</div><div class="sf-card-desc">Tendências, concorrentes, ideias e oportunidades.</div></div>
				<div class="sf-card"><div class="sf-card-icon">📅</div><div class="sf-card-title">Calendário</div><div class="sf-card-desc">Reels, Stories, Feed, CTAs e objetivos.</div></div>
				<div class="sf-card"><div class="sf-card-icon">⚡</div><div class="sf-card-title">Campanha</div><div class="sf-card-desc">Anúncios, públicos, criativos e copy.</div></div>
			</div>
		</div>
	</div>
{/key}

<style>
	.sf-hero {
		text-align: center;
		padding: 24px 16px 8px;
		max-width: 1100px;
		margin: 0 auto;
	}
	.sf-greeting {
		font-size: 36px;
		font-weight: 700;
		margin: 0 0 12px;
		letter-spacing: -0.5px;
		line-height: 1.2;
	}
	.sf-subtitle {
		font-size: 15px;
		line-height: 1.5;
		color: #666;
		max-width: 640px;
		margin: 0 auto 28px;
	}
	:global(.dark) .sf-subtitle {
		color: #aaa;
	}
	.sf-cards {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: 14px;
	}
	.sf-card {
		background: rgba(0, 0, 0, 0.02);
		border: 1px solid rgba(0, 0, 0, 0.08);
		border-radius: 12px;
		padding: 18px 14px;
		text-align: left;
		transition: all 0.18s ease;
		cursor: pointer;
	}
	.sf-card:hover {
		background: rgba(0, 0, 0, 0.04);
		transform: translateY(-2px);
	}
	:global(.dark) .sf-card {
		background: rgba(255, 255, 255, 0.03);
		border-color: rgba(255, 255, 255, 0.08);
	}
	:global(.dark) .sf-card:hover {
		background: rgba(255, 255, 255, 0.06);
	}
	.sf-card-icon {
		font-size: 22px;
		margin-bottom: 10px;
	}
	.sf-card-title {
		font-weight: 600;
		font-size: 13.5px;
		margin-bottom: 4px;
	}
	.sf-card-desc {
		font-size: 12px;
		color: #888;
		line-height: 1.4;
	}
	@media (max-width: 1024px) {
		.sf-cards {
			grid-template-columns: repeat(3, 1fr);
		}
	}
	@media (max-width: 640px) {
		.sf-cards {
			grid-template-columns: 1fr;
		}
		.sf-greeting {
			font-size: 24px;
		}
	}
</style>
