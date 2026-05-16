<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { marked } from 'marked';
	import DOMPurify from 'dompurify';

	import { onMount, getContext, tick, createEventDispatcher } from 'svelte';
	import { blur, fade } from 'svelte/transition';

	const dispatch = createEventDispatcher();

	import { getChatList } from '$lib/apis/chats';
	import { updateFolderById } from '$lib/apis/folders';

	import {
		config,
		user,
		models as _models,
		temporaryChatEnabled,
		selectedFolder,
		chats,
		currentChatPage
	} from '$lib/stores';
	import { sanitizeResponseContent, extractCurlyBraceWords } from '$lib/utils';
	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';

	import Suggestions from './Suggestions.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
	import MessageInput from './MessageInput.svelte';
	import FolderPlaceholder from './Placeholder/FolderPlaceholder.svelte';
	import FolderTitle from './Placeholder/FolderTitle.svelte';

	const i18n = getContext('i18n');

	// SocialForge: saudação dinâmica por hora do dia
	function sfGreetingEmoji() {
		const h = new Date().getHours();
		if (h >= 5 && h < 12) return '☀️';
		if (h >= 12 && h < 18) return '🌤️';
		return '🌙';
	}
	function sfGreetingText() {
		const h = new Date().getHours();
		if (h >= 5 && h < 12) return 'Bom dia';
		if (h >= 12 && h < 18) return 'Boa tarde';
		return 'Boa noite';
	}

	export let createMessagePair: Function;
	export let stopResponse: Function;

	export let autoScroll = false;

	export let atSelectedModel: Model | undefined;
	export let selectedModels: [''];

	export let history;

	export let prompt = '';
	export let files = [];
	export let messageInput = null;

	export let selectedToolIds = [];
	export let selectedFilterIds = [];
	export let pendingOAuthTools = [];

	export let showCommands = false;

	export let imageGenerationEnabled = false;
	export let codeInterpreterEnabled = false;
	export let webSearchEnabled = false;

	export let onUpload: Function = (e) => {};
	export let onSelect = (e) => {};
	export let onChange = (e) => {};

	export let toolServers = [];

	export let dragged = false;

	let models = [];
	let selectedModelIdx = 0;

	$: if (selectedModels.length > 0) {
		selectedModelIdx = models.length - 1;
	}

	$: models = selectedModels.map((id) => $_models.find((m) => m.id === id));
</script>

<div class="m-auto w-full max-w-6xl px-2 @2xl:px-20 translate-y-6 py-24 text-center">
	{#if $temporaryChatEnabled}
		<Tooltip
			content={$i18n.t("This chat won't appear in history and your messages will not be saved.")}
			className="w-full flex justify-center mb-0.5"
			placement="top"
		>
			<div class="flex items-center gap-2 text-gray-500 text-base my-2 w-fit">
				<EyeSlash strokeWidth="2.5" className="size-4" />{$i18n.t('Temporary Chat')}
			</div>
		</Tooltip>
	{/if}

	<div
		class="w-full text-3xl text-gray-800 dark:text-gray-100 text-center flex items-center gap-4 font-primary"
	>
		<div class="w-full flex flex-col justify-center items-center">
			{#if $selectedFolder}
				<FolderTitle
					folder={$selectedFolder}
					onUpdate={async (folder) => {
						await chats.set(await getChatList(localStorage.token, $currentChatPage));
						currentChatPage.set(1);
					}}
					onDelete={async () => {
						await chats.set(await getChatList(localStorage.token, $currentChatPage));
						currentChatPage.set(1);

						selectedFolder.set(null);
					}}
				/>
			{:else}
				<!-- SocialForge custom hero: saudação + 5 cards -->
				<div class="sf-hero w-full" in:fade={{ duration: 200 }}>
					<h1 class="sf-greeting">
						{sfGreetingEmoji()} {sfGreetingText()}, {($user?.name ?? '').split(' ')[0] || 'amigo'}
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
			{/if}

			<div class="text-base font-normal @md:max-w-3xl w-full py-3 {atSelectedModel ? 'mt-2' : ''}">
				<MessageInput
					bind:this={messageInput}
					{history}
					{selectedModels}
					bind:files
					bind:prompt
					bind:autoScroll
					bind:selectedToolIds
					bind:selectedFilterIds
					bind:imageGenerationEnabled
					bind:codeInterpreterEnabled
					bind:webSearchEnabled
					bind:atSelectedModel
					bind:showCommands
					bind:dragged
					{pendingOAuthTools}
					{toolServers}
					{stopResponse}
					{createMessagePair}
					placeholder={$i18n.t('How can I help you today?')}
					{onChange}
					{onUpload}
					on:submit={(e) => {
						dispatch('submit', e.detail);
					}}
				/>
			</div>
		</div>
	</div>

	{#if $selectedFolder}
		<div
			class="mx-auto px-4 md:max-w-3xl md:px-6 font-primary min-h-62"
			in:fade={{ duration: 200, delay: 200 }}
		>
			<FolderPlaceholder folder={$selectedFolder} />
		</div>
	{/if}
</div>

<style>
	/* SocialForge custom hero styles */
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
