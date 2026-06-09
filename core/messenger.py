import os
import logging
import requests

logger = logging.getLogger(__name__)

META_PAGE_TOKEN   = os.environ.get("META_PAGE_TOKEN", "")
META_IG_TOKEN     = os.environ.get("META_IG_TOKEN", "")
META_API_VERSION  = os.environ.get("META_API_VERSION", "v20.0")
WHATSAPP_TOKEN    = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")


def _post(url: str, payload: dict, token: str) -> bool:
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Messenger error {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.error(f"Messenger exception: {e}")
        return False


def enviar_facebook(recipient_id: str, texto: str) -> bool:
    if not META_PAGE_TOKEN:
        logger.info(f"[facebook] (sem token) → {recipient_id}: {texto[:80]}")
        return True
    url = f"https://graph.facebook.com/{META_API_VERSION}/me/messages"
    return _post(url, {"recipient": {"id": recipient_id}, "message": {"text": texto}, "messaging_type": "RESPONSE"}, META_PAGE_TOKEN)


def enviar_instagram(recipient_id: str, texto: str) -> bool:
    token = META_IG_TOKEN or META_PAGE_TOKEN
    if not token:
        logger.info(f"[instagram] (sem token) → {recipient_id}: {texto[:80]}")
        return True
    url = f"https://graph.facebook.com/{META_API_VERSION}/me/messages"
    return _post(url, {"recipient": {"id": recipient_id}, "message": {"text": texto}}, token)


def enviar_whatsapp(recipient_phone: str, texto: str) -> bool:
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        logger.info(f"[whatsapp] (sem token) → {recipient_phone}: {texto[:80]}")
        return True
    url = f"https://graph.facebook.com/{META_API_VERSION}/{WHATSAPP_PHONE_ID}/messages"
    return _post(url, {
        "messaging_product": "whatsapp",
        "to": recipient_phone,
        "type": "text",
        "text": {"body": texto},
    }, WHATSAPP_TOKEN)


def enviar_mensagem(canal: str, recipient_id: str, texto: str) -> bool:
    canal = canal.lower()
    if canal in ("facebook", "fb", "site"):
        return enviar_facebook(recipient_id, texto)
    if canal in ("instagram", "ig"):
        return enviar_instagram(recipient_id, texto)
    if canal in ("whatsapp", "wa"):
        return enviar_whatsapp(recipient_id, texto)
    logger.warning(f"Canal desconhecido: {canal}")
    return False
