import logging

from fastapi import APIRouter, HTTPException, Request
from telethon.errors import SessionPasswordNeededError

from app.schemas.auth import (
    AuthActionResponse,
    AuthStatusResponse,
    SendCodeRequest,
    TwoFARequest,
    UserInfo,
    VerifyCodeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _get_user_info(client) -> UserInfo:
    me = await client.get_me()
    return UserInfo(
        phone=me.phone or "",
        first_name=me.first_name or "",
        username=me.username,
    )


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(request: Request):
    client = getattr(request.app.state, "tg_client", None)
    if client is None or not client.is_connected():
        return AuthStatusResponse(authorized=False, user=None)

    authorized = await client.is_user_authorized()
    if not authorized:
        return AuthStatusResponse(authorized=False, user=None)

    user = await _get_user_info(client)
    return AuthStatusResponse(authorized=True, user=user)


@router.post("/send-code", response_model=AuthActionResponse)
async def send_code(body: SendCodeRequest, request: Request):
    client = getattr(request.app.state, "tg_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")

    try:
        result = await client.send_code_request(body.phone)
        request.app.state.auth_phone = body.phone
        request.app.state.auth_phone_code_hash = result.phone_code_hash
        return AuthActionResponse(status="code_sent")
    except Exception as e:
        logger.error("send_code_request failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify", response_model=AuthActionResponse)
async def verify_code(body: VerifyCodeRequest, request: Request):
    client = getattr(request.app.state, "tg_client", None)
    phone = getattr(request.app.state, "auth_phone", None)
    phone_code_hash = getattr(request.app.state, "auth_phone_code_hash", None)

    if client is None:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    if not phone or not phone_code_hash:
        raise HTTPException(status_code=400, detail="No pending auth session; call send-code first")

    try:
        await client.sign_in(phone, body.code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        return AuthActionResponse(status="2fa_required")
    except Exception as e:
        logger.error("sign_in failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    await _activate_forwarding(request.app)
    user = await _get_user_info(client)
    return AuthActionResponse(status="authenticated", user=user)


@router.post("/2fa", response_model=AuthActionResponse)
async def two_fa(body: TwoFARequest, request: Request):
    client = getattr(request.app.state, "tg_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")

    try:
        await client.sign_in(password=body.password)
    except Exception as e:
        logger.error("2fa sign_in failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    await _activate_forwarding(request.app)
    user = await _get_user_info(client)
    return AuthActionResponse(status="authenticated", user=user)


@router.post("/logout", response_model=AuthActionResponse)
async def logout(request: Request):
    client = getattr(request.app.state, "tg_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")

    try:
        await client.log_out()
    except Exception as e:
        logger.error("log_out failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    request.app.state.rule_map = {}
    return AuthActionResponse(status="logged_out")


async def _activate_forwarding(app) -> None:
    from app.main import load_rules_from_db
    from app.telegram.handlers import register_handlers

    rule_map = await load_rules_from_db()
    client = app.state.tg_client
    forwarder = app.state.forwarder
    register_handlers(client, rule_map, forwarder)
    app.state.rule_map = rule_map
