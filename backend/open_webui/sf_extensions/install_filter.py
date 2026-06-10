"""
Auto-instala/atualiza a Filter Function context_injector no DB Functions
do Open WebUI durante o startup. Idempotente.

Lê o source de context_injector.py do mesmo diretório e faz upsert direto na
tabela `function`. Marca como is_global+is_active pra rodar em todo completion
sem precisar de admin tocar UI.

Estratégia:
  - Procura pelo id='socialforge_context_injector'
  - Se não existe → INSERT com o source atual
  - Se existe e o content mudou → UPDATE content + updated_at
  - Se já está sincronizado → noop

Falha em silêncio (log warn) se DB estiver indisponível na start — chat continua
funcionando sem context injection, só não enriquece com brand_core/RAG.
"""

from __future__ import annotations

import logging
import os
import time

from sqlalchemy import select

from open_webui.internal.db import get_async_db_context
from open_webui.models.functions import Function
from open_webui.models.users import Users

log = logging.getLogger("sf.install_filter")

FILTER_ID = "socialforge_context_injector"
FILTER_NAME = "SocialForge Context Injector"
FILTER_TYPE = "filter"
FILTER_DESCRIPTION = (
    "Lê metadata.sf.{client_id, mirror_token} do body e injeta contexto "
    "destilado + RAG do cliente vindo do SocialForge V3."
)


def _read_filter_source() -> str:
    """Lê context_injector.py do mesmo diretório."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "context_injector.py")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def _pick_admin_user_id() -> str | None:
    """Função no Open WebUI precisa de user_id dono. Usamos o 1º admin."""
    async with get_async_db_context() as db:
        admin = await Users.get_first_user(db)
        return admin.id if admin else None


async def ensure_socialforge_filter_installed() -> bool:
    """
    Upsert da Filter Function. Retorna True se inseriu/atualizou, False se noop.
    Não levanta exceções — caller (lifespan) não deve abortar a startup.
    """
    try:
        source = _read_filter_source()
    except Exception as e:
        log.warning("não consegui ler context_injector.py: %s", e)
        return False

    try:
        async with get_async_db_context() as db:
            result = await db.execute(select(Function).where(Function.id == FILTER_ID))
            existing = result.scalar_one_or_none()

            if existing and existing.content == source and existing.is_active:
                return False

            now = int(time.time())
            meta = {
                "description": FILTER_DESCRIPTION,
                "manifest": {"author": "SocialForge", "version": "1.0.0"},
            }

            if existing is None:
                user_id = await _pick_admin_user_id()
                if not user_id:
                    log.warning("sem admin user — adiando instalação do filter")
                    return False
                fn = Function(
                    id=FILTER_ID,
                    user_id=user_id,
                    name=FILTER_NAME,
                    type=FILTER_TYPE,
                    content=source,
                    meta=meta,
                    valves={},
                    is_active=True,
                    is_global=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(fn)
                await db.commit()
                log.info("Filter %s instalada (insert)", FILTER_ID)
                return True

            existing.content = source
            existing.meta = meta
            existing.is_active = True
            existing.is_global = True
            existing.updated_at = now
            await db.commit()
            log.info("Filter %s atualizada (content sync)", FILTER_ID)
            return True
    except Exception as e:
        log.warning("ensure_socialforge_filter_installed falhou: %s", e)
        return False
