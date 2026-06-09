from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import threading
import logging
from flask import Flask, request, jsonify
from core.agent import processar_mensagem
from core.messenger import enviar_mensagem

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

VERIFY_TOKEN_META = os.environ.get("VERIFY_TOKEN_META", "jetur_verify_2024")
VERIFY_TOKEN_WA   = os.environ.get("VERIFY_TOKEN_WA", "jetur_verify_2024")

# Loop assíncrono persistente em thread dedicada — evita destruição de contexto entre pedidos
_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


def _session_id(canal: str, sender_id: str) -> str:
    return f"{canal}_{sender_id}"


def _processar_e_responder(canal: str, sender_id: str, texto: str) -> str:
    session_id = _session_id(canal, sender_id)
    resposta = _run(processar_mensagem(session_id, sender_id, texto))
    enviado = enviar_mensagem(canal, sender_id, resposta)
    if not enviado:
        logger.warning(f"Resposta não enviada ao canal {canal} / {sender_id}")
    return resposta

@pp.route("/")
def home():
    return "ola do flask"
# ── Webhook Meta (IG DM + FB Messenger) ──────────────────────────────────────

@app.get("/webhook")
def webhook_meta_verificar():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN_META:
        logger.info("Webhook Meta verificado.")
        return challenge, 200

    return "Token inválido", 403


@app.post("/webhook")
def webhook_meta_receber():
    try:
        body  = request.get_json(silent=True) or {}
        objeto = body.get("object", "")

        if objeto not in ("page", "instagram"):
            return "ok", 200

        canal = "instagram" if objeto == "instagram" else "facebook"

        for entry in body.get("entry", []):
            for ev in entry.get("messaging", []):
                sender_id = ev.get("sender", {}).get("id", "")
                msg = ev.get("message", {})
                if not sender_id or "text" not in msg:
                    continue
                texto = msg["text"].strip()
                if texto:
                    logger.info(f"[{canal}] De {sender_id}: {texto[:80]}")
                    _processar_e_responder(canal, sender_id, texto)

            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                for msg in change.get("value", {}).get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    sender_id = msg.get("from", "")
                    texto = msg.get("text", {}).get("body", "").strip()
                    if sender_id and texto:
                        logger.info(f"[instagram] De {sender_id}: {texto[:80]}")
                        _processar_e_responder("instagram", sender_id, texto)

        return "ok", 200

    except Exception as e:
        logger.error(f"Erro no webhook Meta: {e}")
        return "erro", 500


# ── Webhook WhatsApp Cloud API ────────────────────────────────────────────────

@app.get("/whatsapp/webhook")
def webhook_wa_verificar():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN_WA:
        logger.info("Webhook WhatsApp verificado.")
        return challenge, 200

    return "Token inválido", 403


@app.post("/whatsapp/webhook")
def webhook_wa_receber():
    try:
        body = request.get_json(silent=True) or {}

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                for msg in change.get("value", {}).get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    sender_phone = msg.get("from", "")
                    texto = msg.get("text", {}).get("body", "").strip()
                    if sender_phone and texto:
                        logger.info(f"[whatsapp] De {sender_phone}: {texto[:80]}")
                        _processar_e_responder("whatsapp", sender_phone, texto)

        return "ok", 200

    except Exception as e:
        logger.error(f"Erro no webhook WhatsApp: {e}")
        return "erro", 500


# ── Teste local (sem canal externo) ──────────────────────────────────────────

@app.post("/chat")
def chat_directo():
    """
    Teste local: { "session_id": "...", "user_id": "...", "texto": "..." }
    session_id e user_id são opcionais (usam valores de teste por defeito).
    """
    try:
        dados      = request.get_json(silent=True) or {}
        session_id = dados.get("session_id", "test_session")
        user_id    = dados.get("user_id", "test_user")
        texto      = dados.get("texto", "").strip()

        if not texto:
            return jsonify({"erro": "Campo 'texto' é obrigatório"}), 400

        resposta = _run(processar_mensagem(session_id, user_id, texto))
        return jsonify({"resposta": resposta}), 200

    except Exception as e:
        logger.error(f"Erro no chat directo: {e}")
        return jsonify({"erro": str(e)}), 500


@app.get("/health")
def health():
    return jsonify({"status": "ok", "servico": "jetur-bot"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=True)
