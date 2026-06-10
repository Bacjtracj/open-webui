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
				<!-- SocialForge: hero removido (sem saudação/cards) -->
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
	/* SocialForge custom hero — referências do V2 (chat.css) */
	.sf-hero {
		text-align: center;
		padding: 0 16px;
		max-width: 820px;
		margin: 0 auto 34px;
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
		margin: 0 auto;
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
		grid-template-columns: repeat(5, 156px);
		justify-content: center;
		gap: 10px;
	}
	.sf-card {
		width: 156px;
		height: 131px;
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
