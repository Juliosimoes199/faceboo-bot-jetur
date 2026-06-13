from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import threading
import logging
from flask import Flask, request, jsonify
from core.agent import processar_mensagem, session_service
from core.messenger import enviar_mensagem
import requests

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
    resposta = _run(processar_mensagem(session_id, sender_id, texto, canal))
    enviado = enviar_mensagem(canal, sender_id, resposta)
    if not enviado:
        logger.warning(f"Resposta não enviada ao canal {canal} / {sender_id}")
    return resposta


@app.route("/")
def home():
    return "Jetur Bot is running!"




def enviar_mensagem_facebook(customer_psid, text_to_send):
    """Função com a URL da API da Meta corrigida"""
    PAGE_ACCESS_TOKEN = "EAAOb84AHDsEBRmDu0VIVVZAAIZCpo13GWeCrQzWypKAeHhgefOeUKnwulul8av62rGaSbIiuADSVXxdYE2o8disBSgwBID5bTCIZBo9VZA3S3m0hn50MGUqOptYcY5FaEZADoVeJgGMjZB5vBXG0toXjqMDbKz3C2yhokwtv0MUsUZCN8awUw74kuZAW09B3LLnx7wHWZAwZDZD"
    
    # URL CORRIGIDA: Aponta para o endpoint oficial de mensagens da API Graph da Meta
    url = "https://graph.facebook.com/v21.0/me/messages"
    
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "recipient": {
            "id": str(customer_psid)
        },
        "messaging_type": "RESPONSE",
        "message": {
            "text": text_to_send
        }
    }
    
    try:
        response = requests.post(url, params=params, json=payload, headers=headers)
        
        # Exibe o status e o texto bruto da resposta para facilitar o diagnóstico caso falhe por outro motivo
        print(f"Status Code do Facebook: {response.status_code}")
        print(f"Texto bruto recebido: {response.text}")
        
        response_data = response.json()
        print(f"Resposta oficial da API do Facebook: {response_data}")
        return response_data
    except Exception as e:
        print(f"Erro ao disparar requisição POST para o Facebook: {e}")
        return None



@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    VERIFY_TOKEN = "julioteste"
    
    # 1. TRATAMENTO PARA VALIDAÇÃO (GET)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        
        if mode == "subscribe" and verify_token == VERIFY_TOKEN:
            print("Webhook verificado com sucesso!")
            return challenge, 200
        else:
            print("Falha na verificação do webhook.")
            return "Token de verificação inválido", 403

    # 2. TRATAMENTO PARA RECEBER MENSAGENS (POST)
    if request.method == "POST":
        try:
            body = request.get_json()
            
            if body and "object" in body and body["object"] == "page":
                for entry in body.get("entry", []):
                    if "messaging" in entry and len(entry["messaging"]) > 0:
                        messaging_event = entry["messaging"][0]
                        print(f"Evento de Mensagem Recebido: {messaging_event}")
                        
                        sender_id = messaging_event["sender"]["id"]
                        print(f"ID do Remetente (PSID): {sender_id}")
                        
                        if "message" in messaging_event:
                            message_text = messaging_event["message"].get("text")
                            print(f"Texto da Mensagem: {message_text}")
                            
                            # --- RESPOSTA AUTOMÁTICA AQUI ---
                            # Criamos o texto que queremos devolver
                            message_text = f"{message_text} \ncanal de contato: *facebook*"
                            texto_resposta = _processar_e_responder("facebook", sender_id, message_text)
                            #texto_resposta = f"Olá! Recebi a sua mensagem: '{message_text}'."
                            
                            # Executa o envio
                            enviar_mensagem_facebook(sender_id, texto_resposta)
            
            return "EVENT_RECEIVED", 200
        except Exception as e:
            print(f"Erro ao processar POST: {e}")
            return "Erro interno", 500

def enviar_mensagem_instagram2(igsid: str, texto: str):
    """Envia mensagem via Instagram Business Messaging API."""
    token = os.environ.get("PAGE_ACCESS_TOKEN_INSTAGRAM")
    ig_id = os.environ.get("INSTAGRAM_BUSINESS_ID", "17841448397273178")  # ID da conta nível_776
    if not token:
        logger.error("PAGE_ACCESS_TOKEN_INSTAGRAM não configurado nas variáveis de ambiente.")
        return None
    # Endpoint da Instagram Business Messaging API — usa o ID da conta IG, não /me
    url = f"https://graph.instagram.com/v21.0/{ig_id}/messages"
    payload = {
        "recipient": {"id": igsid},
        "messaging_type": "RESPONSE",
        "message": {"text": texto},
    }
    try:
        resp = requests.post(
            url,
            params={"access_token": token},
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        logger.info(f"Instagram send status={resp.status_code} body={resp.text}")
        return resp.json()
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem Instagram: {e}")
        return None

def enviar_mensagem_instagram11(igsid: str, texto: str):
    """Envia mensagem via Instagram Business Messaging API com o Token e URL Corrigidos."""
    token = "IGAAR1nZBZBTFatBZAGFTV2J1VGhTb0VaNnRuVW1SNEVPaWh5NnhrQkFaS2o2eFFjZAXBma1hvRjJFS3RlVG1XN0FMWFk2aGdldk52Y3ZA2SXRjNjJMNjRpdHVPVDVYOG52cnh1VVNydVg5NmJJVDJBNnR6cUF1Wk16djI4WTBxT3djVQZDZD"
    ig_id = "17841448397273178"
    
    # GARANTA QUE ESSA LINHA TENHA A BARRA APÓS O DOMÍNIO E A VERSÃO
    url = f"https://graph.instagram.com/v21.0/{ig_id}/messages"
    
    payload = {
        "recipient": {"id": igsid},
        "messaging_type": "RESPONSE",
        "message": {"text": texto},
    }
    try:
        resp = requests.post(
            url,
            params={"access_token": token},
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        logger.info(f"Instagram send status={resp.status_code} body={resp.text}")
        return resp.json()
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem Instagram: {e}")
        return None


@app.route("/webhook/instagram", methods=["GET", "POST"])
def instagram_webhook():
    VERIFY_TOKEN = "instagramjetur2026"

    # 1. VALIDAÇÃO DO WEBHOOK (GET)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and verify_token == VERIFY_TOKEN:
            logger.info("Instagram webhook verificado com sucesso.")
            return challenge, 200
        logger.warning("Falha na verificação do Instagram webhook.")
        return "Token de verificação inválido", 403

    # 2. RECEBER MENSAGENS (POST)
    if request.method == "POST":
        try:
            body = request.get_json()
            logger.info(f"Instagram webhook payload: {body}")

            # A Meta envia object="instagram" para eventos da plataforma Instagram
            if body and body.get("object") in ("instagram", "page"):
                for entry in body.get("entry", []):
                    for event in entry.get("messaging", []):
                        sender_igsid = event.get("sender", {}).get("id")

                        # Ignora eco das próprias mensagens enviadas pelo bot
                        msg = event.get("message", {})
                        if msg.get("is_echo"):
                            continue

                        texto = msg.get("text")
                        texto = f"{texto} \ncanal de contato: *instagram*"
                        if sender_igsid and texto:
                            logger.info(f"Instagram msg de {sender_igsid}: {texto}")
                            _processar_e_responder("instagram", sender_igsid, texto)
                            #enviar_mensagem_instagram11(sender_igsid, f"Recebi sua mensagem: '{texto}'")

            return "EVENT_RECEIVED", 200
        except Exception as e:
            logger.error(f"Erro ao processar POST do Instagram: {e}")
            return "Erro interno", 500


# ─── Endpoints de administração de sessões ───────────────────────────────────
# Header obrigatório: x-admin-token: <ADMIN_TOKEN>

def _require_admin(req):
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token or req.headers.get("x-admin-token") != token:
        return jsonify({"erro": "Token de admin inválido ou em falta."}), 401
    return None


@app.route("/admin/sessao", methods=["DELETE"])
def apagar_sessao():
    """Apaga a sessão de um utilizador específico.
    Body JSON: { "sender_id": "123456", "canal": "facebook" }
    """
    err = _require_admin(request)
    if err:
        return err
    body = request.get_json() or {}
    sender_id = body.get("sender_id", "").strip()
    canal = body.get("canal", "").strip()
    if not sender_id or not canal:
        return jsonify({"erro": "Campos obrigatórios: sender_id, canal."}), 400

    session_id = f"{canal}_{sender_id}"
    try:
        _run(session_service.delete_session(
            app_name="jetur_bot",
            user_id=sender_id,
            session_id=session_id,
        ))
        logger.info(f"Sessão apagada manualmente: {session_id}")
        return jsonify({"ok": True, "session_id": session_id})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/admin/sessoes/<sender_id>", methods=["GET"])
def listar_sessoes(sender_id):
    """Lista as sessões activas de um utilizador."""
    err = _require_admin(request)
    if err:
        return err
    try:
        resultado = _run(session_service.list_sessions(
            app_name="jetur_bot",
            user_id=sender_id,
        ))
        sessoes = [
            {"session_id": s.id, "canal": s.id.split("_")[0] if "_" in s.id else "?"}
            for s in (resultado.sessions if hasattr(resultado, "sessions") else [])
        ]
        return jsonify({"sender_id": sender_id, "sessoes": sessoes})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=True)
