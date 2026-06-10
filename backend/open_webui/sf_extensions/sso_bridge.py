"""
SocialForge SSO Bridge — endpoint dedicado em vez de middleware.

Por que rota e não middleware:
- main.py do Open WebUI 0.9.5 alerta explicitamente contra BaseHTTPMiddleware
  por causar CancelledError em chamadas DB durante client disconnect.
- Rota é idiomática, async-safe, e segue o padrão dos routers do Open WebUI.

Endpoint:
- GET /sso?token=<jwt>
    Recebe token bridge HS256 vindo do SocialForge V3 (novo.socialforge.pro)
    e faz signin automático no Open WebUI.

Fluxo:
1. Verifica assinatura HS256 com SSO_BRIDGE_SECRET (env var)
2. Procura user por email == agency_email (1 conta por agência)
3. Se não existir, cria via Auths.insert_new_auth
4. Gera JWT do Open WebUI via create_token (7 dias)
5. Retorna HTML bootstrap que: seta localStorage.token + cookie + redireciona
6. Próxima página é '/' limpa, com sf_plan, sf_client_id, etc na query

Payload do token bridge:
{
  agency_id, agency_email, agency_name,
  user_id, user_email, user_display_name,
  plan, plan_name,
  client: { id, name, segment, instagram_handle } | null,
  iss: "sf-v3", aud: "sf-chat-ia"
}
"""

import logging
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

log = logging.getLogger(__name__)

SSO_BRIDGE_SECRET = os.environ.get("SSO_BRIDGE_SECRET")
ALLOWED_ISS = "sf-v3"
ALLOWED_AUD = "sf-chat-ia"

router = APIRouter(tags=["sf-sso"])


def _error_html(code: str, detail: str = "") -> HTMLResponse:
    """Página de erro amigável (em vez de tela em branco)."""
    safe = detail.replace("<", "&lt;").replace(">", "&gt;") if detail else ""
    body = f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><title>SocialForge — erro de SSO</title>
<style>body{{font-family:system-ui,sans-serif;max-width:520px;margin:64px auto;padding:0 16px;color:#222}}
.box{{background:#fff7f5;border:1px solid #e8c5b8;border-radius:14px;padding:24px}}
code{{background:#f4eee8;padding:2px 6px;border-radius:4px;font-size:13px}}
a{{color:#c04a1b}}</style>
<body><div class="box">
<h2>Não foi possível abrir o Chat IA</h2>
<p><strong>Motivo:</strong> {code}</p>
{f"<p><code>{safe}</code></p>" if safe else ""}
<p>Volte ao <a href="https://novo.socialforge.pro">SocialForge</a> e tente novamente. Se persistir, fale com o suporte.</p>
</div></body></html>"""
    return HTMLResponse(body, status_code=400)


@router.get("/sso")
async def sso_bridge(token: str = Query(..., description="Bridge JWT vindo do V3")):
    """Endpoint público que faz signin automático via token bridge do V3."""
    if not SSO_BRIDGE_SECRET:
        log.error("[sf-sso] SSO_BRIDGE_SECRET não configurado")
        return _error_html("config", "SSO_BRIDGE_SECRET ausente no servidor")

    # 1. Verifica assinatura + claims
    try:
        payload = jwt.decode(
            token,
            SSO_BRIDGE_SECRET,
            algorithms=["HS256"],
            audience=ALLOWED_AUD,
            issuer=ALLOWED_ISS,
        )
    except jwt.ExpiredSignatureError:
        log.warning("[sf-sso] token expirado")
        return _error_html("expired", "Token válido por apenas 60s — abra de novo a partir do SocialForge")
    except jwt.InvalidTokenError as e:
        log.warning(f"[sf-sso] token inválido: {e}")
        return _error_html("invalid", str(e))

    agency_email = (payload.get("agency_email") or "").lower().strip()
    agency_name = payload.get("agency_name") or agency_email
    plan = payload.get("plan", "free")
    client = payload.get("client")
    user_email = payload.get("user_email")
    user_display_name = payload.get("user_display_name")
    mirror_token = payload.get("mirror_token") or ""
    mirror_expires_at = payload.get("mirror_expires_at") or ""

    if not agency_email:
        return _error_html("no_email", "Payload sem agency_email")

    # 2. Get-or-create user (async)
    try:
        from open_webui.models.users import Users
        from open_webui.models.auths import Auths
        from open_webui.utils.auth import create_token
    except ImportError as e:
        log.error(f"[sf-sso] import falhou: {e}")
        return _error_html("internal_import", str(e))

    try:
        user = await Users.get_user_by_email(agency_email)
    except Exception as e:
        log.error(f"[sf-sso] get_user_by_email falhou: {e}")
        return _error_html("internal_lookup", str(e))

    if not user:
        try:
            random_password = secrets.token_urlsafe(32)
            user = await Auths.insert_new_auth(
                email=agency_email,
                password=random_password,
                name=agency_name,
                profile_image_url="/user.png",
                role="user",
            )
            log.info(f"[sf-sso] novo user criado: {agency_email}")
        except Exception as e:
            log.error(f"[sf-sso] insert_new_auth falhou: {e}")
            return _error_html("user_create_failed", str(e))

    if not user:
        return _error_html("user_not_found", agency_email)

    # 2b. Atualiza nome se mudou
    if user.name != agency_name:
        try:
            await Users.update_user_by_id(user.id, {"name": agency_name})
        except Exception as e:
            log.warning(f"[sf-sso] update_user_by_id falhou (não-crítico): {e}")

    # 3. Token interno Open WebUI (7 dias)
    try:
        owui_token = create_token(
            data={"id": user.id},
            expires_delta=timedelta(days=7),
        )
    except Exception as e:
        log.error(f"[sf-sso] create_token falhou: {e}")
        return _error_html("token_fail", str(e))

    # 4. Query limpa pra próxima página
    qs = {"sf_plan": plan}
    if client:
        cid = client.get("id")
        cname = client.get("name")
        if cid:
            qs["sf_client_id"] = cid
        if cname:
            qs["sf_client_name"] = cname
    if user_email:
        qs["sf_user"] = user_email
    if user_display_name:
        qs["sf_user_name"] = user_display_name
    clean_url = "/?" + urlencode(qs) if qs else "/"

    # 5. Bootstrap: seta localStorage.token (Svelte do Open WebUI lê dali)
    # + redireciona pra raiz limpa.
    safe_token = owui_token.replace("\\", "\\\\").replace("'", "\\'")
    safe_url = clean_url.replace("\\", "\\\\").replace("'", "\\'")
    safe_mirror = mirror_token.replace("\\", "\\\\").replace("'", "\\'")
    safe_mirror_exp = mirror_expires_at.replace("\\", "\\\\").replace("'", "\\'")
    bootstrap = f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><title>SocialForge — entrando…</title>
<style>body{{font-family:system-ui,sans-serif;max-width:420px;margin:120px auto;text-align:center;color:#888}}</style>
<body>
<p>Abrindo Chat IA…</p>
<script>
try {{
  localStorage.setItem('token', '{safe_token}');
  if ('{safe_mirror}') {{
    localStorage.setItem('sf_mirror_token', '{safe_mirror}');
    localStorage.setItem('sf_mirror_expires_at', '{safe_mirror_exp}');
  }}
}} catch (e) {{ console.warn('[sf-sso] sem localStorage:', e); }}
window.location.replace('{safe_url}');
</script>
<noscript><a href="{safe_url}">Continuar</a></noscript>
</body></html>"""

    response = HTMLResponse(bootstrap, status_code=200)
    # Cookie httpOnly como defesa em profundidade (caso backend cheque cookie)
    response.set_cookie(
        key="token",
        value=owui_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return response
