"""
SocialForge Context Injector + Credits — Open WebUI Filter Function.

Funcionalidade dupla:

  1. RAG: lê metadata.sf.{client_id, mirror_token} e enriquece o body com
     PERSONA_BASE_PROMPT + contexto destilado (/clients/:id/context-pack) +
     trechos top-k de busca semântica (/clients/:id/search-knowledge).

  2. Créditos (Doc4): chama /credits/decide no inlet pra:
       - BLOQUEAR (saldo zero): substitui messages por instrução pra modelo
         de peso 1 responder LITERALMENTE a mensagem amigável.
       - DEGRADAR (saldo < weight escolhido): reescreve body['model'] pro
         fallback (DeepSeek/Gemini, peso 1) e injeta nota system curta.
       - PASSAR (saldo OK): segue fluxo de RAG normal.
     E chama /credits/debit no outlet após resposta completa (idempotente
     por message_id; não cobra blocked nem erros).

Por que metadata.sf no body em vez de header HTTP:
  Filter Functions recebem (body, __user__), não Request. Headers HTTP
  custom ficam invisíveis. Frontend injeta no body.

Por que mirror_token e não cookie:
  Esse código roda no servidor Open WebUI; não tem o cookie sf_token do V3.
  mirror_token (30min, assinado pelo V3) é credencial curta — limita blast
  radius caso vaze nos logs.

Falhas são silenciosas: se o V3 estiver fora ou o mirror expirou, o chat
segue sem injeção + sem cobrança (failsafe pró-cliente).

Modos de deploy:
  A) Upload via Admin → Functions → Import (cola este arquivo)
  B) Auto-install programático na 1ª start, via install_filter.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Awaitable, Callable, Optional

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger("sf.context_injector")
log.setLevel(logging.INFO)

# Marcadores pra detectar/evitar re-injeção entre turnos
SF_SYS_MARKER = "<!-- sf:v3-context-injected -->"
RAG_BLOCK_RE = re.compile(r"\n+<!-- sf:rag-start -->.*?<!-- sf:rag-end -->\n*", re.DOTALL)


class Filter:
    """Open WebUI Filter Function: inlet (rag + credits) + outlet (debit)."""

    class Valves(BaseModel):
        priority: int = Field(default=0, description="Ordem entre Filters (menor = primeiro)")
        v3_api_base: str = Field(
            default_factory=lambda: os.environ.get(
                "V3_API_BASE", "http://172.17.0.1:3903"
            ),
            description="URL interna do SocialForge V3 (não passe pelo domínio público)",
        )
        rag_top_k: int = Field(default=4, description="Trechos vetoriais por turno")
        rag_min_similarity: float = Field(
            default=0.30,
            description="Floor de similaridade pra incluir chunk no contexto",
        )
        http_timeout_s: float = Field(default=4.0)
        enabled: bool = Field(default=True)
        credits_enabled: bool = Field(default=True, description="Bloqueio/degradação por créditos")

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._client: Optional[httpx.AsyncClient] = None
        # Open WebUI passa body limpo (sem metadata.variables.sf) pro outlet.
        # Stash do sf no inlet por message_id pra recuperar no outlet.
        # TTL implícito: limpa entries com idade > 600s no próximo write.
        self._sf_stash: dict[str, tuple[float, dict]] = {}

    def _stash_set(self, message_id: Optional[str], sf: dict) -> None:
        if not message_id:
            return
        import time as _time
        now = _time.time()
        # Cleanup TTL: entries com mais de 10min são removidas
        if len(self._sf_stash) > 256:
            self._sf_stash = {
                k: v for k, v in self._sf_stash.items() if now - v[0] < 600
            }
        self._sf_stash[message_id] = (now, sf)

    def _stash_pop(self, message_id: Optional[str]) -> Optional[dict]:
        if not message_id:
            return None
        entry = self._sf_stash.pop(message_id, None)
        return entry[1] if entry else None

    # ---- HTTP helper -----------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.valves.http_timeout_s,
                base_url=self.valves.v3_api_base.rstrip("/"),
            )
        return self._client

    # ---- extração de sf metadata ----------------------------------------

    @staticmethod
    def _extract_sf_meta(body: dict) -> Optional[dict]:
        """
        Prioridade: metadata.variables.sf → variables.sf → metadata.sf.
        Retorna None se ausente/incompleto.
        """
        if not isinstance(body, dict):
            return None
        sf = None
        meta = body.get("metadata") if isinstance(body, dict) else None
        if isinstance(meta, dict):
            mv = meta.get("variables")
            if isinstance(mv, dict):
                cand = mv.get("sf")
                if isinstance(cand, dict):
                    sf = cand
        if sf is None:
            variables = body.get("variables")
            if isinstance(variables, dict):
                cand = variables.get("sf")
                if isinstance(cand, dict):
                    sf = cand
        if sf is None and isinstance(meta, dict):
            cand = meta.get("sf")
            if isinstance(cand, dict):
                sf = cand
        if not isinstance(sf, dict):
            return None
        if not sf.get("client_id") or not sf.get("mirror_token"):
            return None
        return sf

    @staticmethod
    def _set_sf_meta(body: dict, key: str, value: Any) -> None:
        """Grava sf.<key> em metadata.variables.sf (lugar que persiste)."""
        if not isinstance(body, dict):
            return
        meta = body.setdefault("metadata", {})
        vars_ = meta.setdefault("variables", {})
        sf = vars_.setdefault("sf", {})
        sf[key] = value

    @staticmethod
    def _last_user_text(body: dict) -> Optional[str]:
        msgs = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(msgs, list):
            return None
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    return c.strip() or None
                if isinstance(c, list):
                    parts = [
                        p.get("text", "")
                        for p in c
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    txt = " ".join(p for p in parts if p).strip()
                    return txt or None
                return None
        return None

    # ---- chamadas V3 -----------------------------------------------------

    async def _fetch_context_pack(
        self, client_id: str, mirror_token: str
    ) -> Optional[str]:
        try:
            r = await self._http().get(
                f"/api/chat-ia/clients/{client_id}/context-pack",
                headers={"Authorization": f"Bearer {mirror_token}"},
            )
            if r.status_code != 200:
                log.warning("context-pack %s: %s", r.status_code, r.text[:120])
                return None
            return (r.json() or {}).get("system_prompt") or None
        except Exception as e:
            log.warning("context-pack erro: %s", e)
            return None

    async def _fetch_rag(
        self, client_id: str, mirror_token: str, query: str
    ) -> list[dict]:
        try:
            r = await self._http().post(
                f"/api/chat-ia/clients/{client_id}/search-knowledge",
                headers={"Authorization": f"Bearer {mirror_token}"},
                json={"query": query, "limit": self.valves.rag_top_k},
            )
            if r.status_code != 200:
                log.warning("search-knowledge %s: %s", r.status_code, r.text[:120])
                return []
            results = (r.json() or {}).get("results", [])
            return [
                r_
                for r_ in results
                if isinstance(r_, dict)
                and float(r_.get("similarity") or 0.0) >= self.valves.rag_min_similarity
            ]
        except Exception as e:
            log.warning("search-knowledge erro: %s", e)
            return []

    async def _decide_credits(
        self, mirror_token: str, model_id: str
    ) -> Optional[dict]:
        """Chama /credits/decide. Retorna o dict 'decision' ou None se falhar."""
        try:
            r = await self._http().post(
                "/api/chat-ia/credits/decide",
                headers={"Authorization": f"Bearer {mirror_token}"},
                json={"model_id": model_id},
            )
            if r.status_code != 200:
                log.warning("credits/decide %s: %s", r.status_code, r.text[:120])
                return None
            data = r.json() or {}
            return data.get("decision")
        except Exception as e:
            log.warning("credits/decide erro: %s", e)
            return None

    async def _debit_credits_bg(self, mirror_token: str, payload: dict) -> None:
        """Background task: chama /credits/debit. Falha em silêncio."""
        try:
            r = await self._http().post(
                "/api/chat-ia/credits/debit",
                headers={"Authorization": f"Bearer {mirror_token}"},
                json=payload,
            )
            if r.status_code != 200:
                log.warning("credits/debit %s: %s", r.status_code, r.text[:120])
            else:
                data = r.json() or {}
                if data.get("debited"):
                    log.info(
                        "sf.debit ok model=%s weight=%s balance_after=%s",
                        payload.get("model_id"),
                        payload.get("weight"),
                        data.get("balance_after"),
                    )
                elif data.get("skipped"):
                    log.info("sf.debit skipped reason=%s", data.get("skipped"))
        except Exception as e:
            log.warning("credits/debit erro: %s", e)

    # ---- mutações no body ------------------------------------------------

    @staticmethod
    def _format_rag_block(results: list[dict]) -> str:
        if not results:
            return ""
        lines = ["<!-- sf:rag-start -->", "[CONTEXTO RECUPERADO DO CLIENTE]"]
        for i, r in enumerate(results, 1):
            sim = r.get("similarity")
            sim_s = f" (sim={sim:.2f})" if isinstance(sim, (int, float)) else ""
            txt = (r.get("chunk_text") or "").strip()
            lines.append(f"\n— Trecho {i}{sim_s} —\n{txt}")
        lines.append("\n<!-- sf:rag-end -->")
        return "\n".join(lines)

    @staticmethod
    def _upsert_system_message(messages: list, system_text: str) -> list:
        if not messages:
            return [{"role": "system", "content": system_text}]
        if messages[0].get("role") == "system":
            content = messages[0].get("content") or ""
            if SF_SYS_MARKER in content:
                messages[0]["content"] = system_text
            else:
                messages.insert(0, {"role": "system", "content": system_text})
        else:
            messages.insert(0, {"role": "system", "content": system_text})
        return messages

    @staticmethod
    def _attach_rag_to_last_user(messages: list, rag_block: str) -> None:
        if not rag_block or not messages:
            return
        for m in reversed(messages):
            if m.get("role") != "user":
                continue
            content = m.get("content")
            if isinstance(content, str):
                cleaned = RAG_BLOCK_RE.sub("\n", content).rstrip()
                m["content"] = f"{cleaned}\n\n{rag_block}"
            return

    def _apply_block(self, body: dict, decision: dict) -> dict:
        """
        Saldo zero: substitui messages por instrução pro modelo escolhido
        responder LITERALMENTE a mensagem amigável. NÃO troca o model
        (fallback do V3 pode não existir na lista do Open WebUI; deixar
        o escolhido evita "model not found" e o outlet skipa debit via
        sf.blocked=true).

        Custo: ~1 chamada com payload curtíssimo, mas o outlet NÃO cobra
        (sf.blocked=true).
        """
        msg = (decision.get("message") or "Créditos esgotados.").strip()
        body["messages"] = [
            {
                "role": "system",
                "content": (
                    f"{SF_SYS_MARKER}\n"
                    "Você é um aviso fixo. Responda LITERALMENTE com o conteúdo "
                    "entre as marcas <SF_RESP> e </SF_RESP>, sem adicionar mais nada, "
                    "sem reformulação, sem cumprimento.\n\n"
                    f"<SF_RESP>💳 {msg}</SF_RESP>"
                ),
            },
            {"role": "user", "content": "Responda agora."},
        ]
        # remove tools/files pra evitar latência
        body.pop("tools", None)
        body.pop("files", None)
        if isinstance(body.get("metadata"), dict):
            body["metadata"].pop("files", None)
        self._set_sf_meta(body, "blocked", True)
        return body

    def _apply_degrade(self, body: dict, decision: dict) -> None:
        """
        Saldo insuficiente pro modelo escolhido: troca pra fallback (peso 1)
        e injeta system note curta pro user perceber.
        """
        requested = (decision.get("requested_model") or {}).get("model_id")
        fallback = (decision.get("model") or {}).get("model_id")
        if fallback:
            body["model"] = fallback
        self._set_sf_meta(body, "was_degraded", True)
        if requested:
            self._set_sf_meta(body, "original_model", requested)
        notice = decision.get("degrade_notice") or "Modelo degradado por saldo insuficiente."
        messages = body.get("messages") or []
        messages.insert(
            0,
            {
                "role": "system",
                "content": f"[Aviso SocialForge] {notice}",
            },
        )
        body["messages"] = messages

    # ---- entrypoint INLET ------------------------------------------------

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __request__: Any = None,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> dict:
        if not self.valves.enabled:
            return body

        sf = self._extract_sf_meta(body)
        if not sf:
            return body  # cliente não logou via SocialForge, segue normal

        client_id = sf["client_id"]
        mirror_token = sf["mirror_token"]
        requested_model = body.get("model")

        # Stash pra o outlet (Open WebUI não passa variables.sf pro outlet)
        meta = body.get("metadata") or {}
        msg_id_for_stash = meta.get("message_id") or body.get("id")
        if msg_id_for_stash:
            self._stash_set(str(msg_id_for_stash), dict(sf))

        # Etapa 1: créditos (bloqueio/degradação) — ANTES do RAG pra economizar
        if self.valves.credits_enabled and requested_model:
            decision = await self._decide_credits(mirror_token, requested_model)
            if decision:
                if not decision.get("allow"):
                    log.info(
                        "sf.block client=%s reason=%s",
                        client_id, decision.get("reason"),
                    )
                    return self._apply_block(body, decision)
                if decision.get("degraded"):
                    log.info(
                        "sf.degrade client=%s from=%s to=%s",
                        client_id,
                        (decision.get("requested_model") or {}).get("model_id"),
                        (decision.get("model") or {}).get("model_id"),
                    )
                    self._apply_degrade(body, decision)

        # Etapa 2: RAG (contexto + chunks vetoriais)
        system_text = await self._fetch_context_pack(client_id, mirror_token)
        last_user = self._last_user_text(body)
        rag_results = (
            await self._fetch_rag(client_id, mirror_token, last_user)
            if last_user
            else []
        )

        if system_text:
            tagged = f"{SF_SYS_MARKER}\n{system_text.strip()}"
            messages = body.get("messages") or []
            body["messages"] = self._upsert_system_message(messages, tagged)

        if rag_results:
            self._attach_rag_to_last_user(
                body.get("messages") or [], self._format_rag_block(rag_results)
            )

        log.info(
            "sf.inject ok client=%s system=%s rag_n=%d",
            client_id, bool(system_text), len(rag_results),
        )
        return body

    # ---- entrypoint OUTLET ----------------------------------------------

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        """
        Chamado APÓS resposta. Debita créditos em background (não bloqueia user).
        Não cobra:
          - sf.blocked=true (bloqueio de saldo já deu mensagem fixa)
          - was_completed=false (erro/timeout)
          - sf metadata ausente (cliente não logou via SocialForge)
        """
        if not self.valves.enabled or not self.valves.credits_enabled:
            return body

        # Tenta extrair sf do body (raro no outlet — Open WebUI passa shape limpo)
        sf = self._extract_sf_meta(body)
        if not sf:
            # Fallback: recupera do stash via message_id (body['id'] no outlet)
            stash_key = body.get("id") if isinstance(body, dict) else None
            sf = self._stash_pop(str(stash_key)) if stash_key else None
        if not sf or sf.get("blocked"):
            return body

        mirror_token = sf["mirror_token"]
        client_id_meta = sf.get("client_id")

        # Localiza a mensagem do assistant que acabou de chegar
        msgs = body.get("messages") or []
        last_assistant = None
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "assistant":
                last_assistant = m
                break

        content = ""
        if last_assistant:
            c = last_assistant.get("content")
            if isinstance(c, str):
                content = c
            elif isinstance(c, list):
                content = " ".join(
                    p.get("text", "")
                    for p in c
                    if isinstance(p, dict) and p.get("type") == "text"
                )

        # Tokens + finish_reason vem em info de runs/usage no Open WebUI
        info = (last_assistant or {}).get("info") or {}
        usage = info.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens") or info.get("prompt_eval_count")
        completion_tokens = usage.get("completion_tokens") or info.get("eval_count")
        total_tokens = usage.get("total_tokens")

        # Modelo realmente usado (já pode estar degradado)
        model_used = (
            (last_assistant or {}).get("model")
            or info.get("model")
            or body.get("model")
        )

        # was_completed: qualquer resposta não-vazia conta. Erros vêm com
        # content vazio + error_message. Threshold 100 chars era muito alto
        # (slogan/resposta curta caía fora).
        has_content = bool(content and content.strip())
        was_completed = has_content or (info.get("done") is True)
        was_degraded = bool(sf.get("was_degraded"))

        # Weight: descobre via decide (que devolve weight do modelo)
        weight = 0
        if model_used and was_completed:
            decision = await self._decide_credits(mirror_token, model_used)
            if decision and decision.get("model"):
                weight = int(decision["model"].get("weight") or 0)

        if not was_completed or weight <= 0:
            return body

        payload = {
            "client_id": client_id_meta,
            "chat_id": body.get("chat_id"),
            "model_id": model_used,
            "weight": weight,
            "was_degraded": was_degraded,
            "original_model_id": sf.get("original_model"),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "was_completed": True,
            "conversation_id": body.get("chat_id"),
            "message_id": (last_assistant or {}).get("id"),
            "duration_ms": info.get("eval_duration"),
        }

        # Fire-and-forget: não atrasa user
        try:
            asyncio.create_task(self._debit_credits_bg(mirror_token, payload))
        except RuntimeError:
            # Sem event loop (cenário raro de teardown) → debita sync best-effort
            try:
                await self._debit_credits_bg(mirror_token, payload)
            except Exception:
                pass

        return body
