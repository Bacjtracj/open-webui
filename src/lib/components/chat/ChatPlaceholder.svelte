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
	/* SocialForge custom hero — referências do V2 (chat.css) */
	.sf-hero {
		text-align: center;
		padding: 42px 16px 18px;
		max-width: 820px;
		margin: 0 auto;
	}
	.sf-greeting {
		font-size: clamp(34px, 4.1vw, 54px);
		font-weight: 800;
		letter-spacing: -0.06em;
		line-height: 1.05;
		margin: 0 0 10px;
		display: inline-flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
		justify-content: center;
	}
	.sf-subtitle {
		max-width: 720px;
		margin: 0 auto 28px;
		font-size: 18px;
		color: #5f5a55;
		font-weight: 500;
		line-height: 1.48;
	}
	:global(.dark) .sf-subtitle {
		color: #aaa;
	}
	.sf-cards {
		width: min(100%, 820px);
		margin: 26px auto 0;
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: 10px;
	}
	.sf-card {
		min-height: 92px;
		padding: 13px 12px;
		border-radius: 18px;
		background: rgba(249, 247, 244, 0.82);
		border: 1px solid rgba(225, 219, 211, 0.95);
		box-shadow: 0 10px 24px rgba(70, 50, 20, 0.055);
		text-align: left;
		transition: 0.18s ease;
		cursor: pointer;
	}
	.sf-card:hover {
		transform: translateY(-2px);
		background: #fffaf5;
		border-color: #e3c19a;
		box-shadow: 0 14px 30px rgba(70, 50, 20, 0.08);
	}
	:global(.dark) .sf-card {
		background: rgba(31, 27, 23, 0.94);
		border-color: #342d27;
	}
	:global(.dark) .sf-card:hover {
		background: rgba(255, 255, 255, 0.07);
	}
	.sf-card-icon {
		width: 30px;
		height: 30px;
		display: grid;
		place-items: center;
		border-radius: 12px;
		background: #fff1de;
		margin-bottom: 9px;
		font-size: 15px;
	}
	:global(.dark) .sf-card-icon {
		background: rgba(244, 174, 71, 0.18);
	}
	.sf-card-title {
		display: block;
		font-weight: 600;
		font-size: 12px;
		letter-spacing: -0.02em;
		margin-bottom: 4px;
	}
	.sf-card-desc {
		display: block;
		font-size: 11px;
		color: #888;
		line-height: 1.28;
	}
	@media (max-width: 768px) {
		.sf-cards {
			grid-template-columns: repeat(3, 1fr);
		}
		.sf-greeting {
			font-size: 30px;
			letter-spacing: -0.055em;
		}
		.sf-subtitle {
			font-size: 14px;
			line-height: 1.45;
		}
	}
	@media (max-width: 480px) {
		.sf-cards {
			grid-template-columns: 1fr;
		}
	}
</style>
