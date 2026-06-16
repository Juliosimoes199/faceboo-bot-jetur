import os
import logging
import urllib.request
import requests
import redis as redis_lib
from datetime import date, datetime
from zoneinfo import ZoneInfo
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

CRM_API_URL = os.environ.get("CRM_API_URL", "https://jetur-crm.vercel.app")
_TZ = ZoneInfo("Africa/Luanda")

_REDIS_URL = os.environ.get("REDIS_URL")
_redis = redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_timeout=5) if _REDIS_URL else None


def _adquirir_lock(chave: str, ttl_segundos: int = 120) -> bool:
    """Retorna True se o lock foi adquirido (primeira vez). False se já existe."""
    if _redis is None:
        return True  # sem Redis, permite sempre (fallback)
    try:
        return bool(_redis.set(chave, "1", nx=True, ex=ttl_segundos))
    except Exception as e:
        logger.error(f"Redis lock error ({chave}): {e}")
        return False  # em caso de falha Redis, bloqueia para evitar duplicados


def enviar_notificacao_ntfy(nome: str,
    servico: str,
    qualificacao: str,
    telefone: str,
    email: str,
    canal: str,
    tool_context: ToolContext) -> str:
    TOPICO = "teste_jetur_viagens" 
    URL = f"https://ntfy.sh/{TOPICO}"

    # Mensagem que será exibida no celular
    MENSAGEM = f"Novo lead registado: {nome} | Serviço: {servico} | Detalhes: {qualificacao} | Tel: {telefone} | Email: {email} | Canal: {canal}"

    # CORREÇÃO: Removido o .encode() dos cabeçalhos e padronizados os nomes das chaves
    headers = {
        "Title": "Alerta de Vendas",
        "Priority": "default",       
        "Sound": "cashregister",  # Chave oficial aceita pelo servidor ntfy
        "Tags": "moneybag,fire"   
    }

    # Prepara a requisição (Apenas a MENSAGEM deve ser transformada em bytes usando .encode)
    req = urllib.request.Request(
        URL, 
        data=MENSAGEM.encode('utf-8'), 
        headers=headers, 
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            print(f"Sucesso! Código de resposta: {response.getcode()}")
            print(f"Monitore as mensagens em: https://ntfy.sh/{TOPICO}")
    except Exception as e:
        print(f"Ocorreu um erro ao enviar: {e}")


def obter_data_atual() -> str:
    """
    Devolve a data e hora actual em Luanda (Angola, UTC+1).
    Usa esta ferramenta sempre que precisares saber a data de hoje,
    calcular 'amanhã', 'próximo mês', 'próxima semana', etc.

    Returns:
        String com data e hora actuais, dia da semana e mês por extenso.
    """
    agora = datetime.now(_TZ)
    dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
            "Sexta-feira", "Sábado", "Domingo"]
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return (
        f"Hoje é {dias[agora.weekday()]}, {agora.day} de {meses[agora.month - 1]} de {agora.year}. "
        f"Hora em Luanda: {agora.strftime('%H:%M')}."
    )


def registrar_lead(
    nome: str,
    servico: str,
    qualificacao: str,
    telefone: str,
    email: str,
    canal: str,
    tool_context: ToolContext,
) -> str:
    """
    Regista um lead qualificado no CRM JEtur via API.

    Args:
        nome: Nome do lead.
        servico: Serviço de interesse (ex: 'Passagem Aérea', 'Pacote Romântico').
        qualificacao: Detalhes recolhidos na qualificação (destino, datas, grupo, ocasião).
        telefone: Número de telefone do lead (com indicativo).
        email: Endereço de e-mail do lead.
        canal: Canal de origem (IG DM / FB DM / WhatsApp / chat).

    Returns:
        Confirmação com o ID do lead registado no CRM.
    """
    _sender = tool_context.state.get("sender_id", "")
    _canal_lock = tool_context.state.get("canal", "")
    _lock_key = f"jetur:lead_registrado:{_canal_lock}:{_sender}"
    if not _adquirir_lock(_lock_key):
        return "Lead já registado nesta sessão. Não repetir."

    # Usa o canal da sessão (origem real do webhook) em vez do que o LLM preenche
    canal_real = tool_context.state.get("canal") or canal

    payload = {
        "nomeCliente":   nome,
        "contacto":      telefone,
        "pacoteServico": servico,
        "qualificacao":  qualificacao,
        "email":         email,
        "canal":         canal_real,
        "status":        "novo_lead",
        "prioridade":    "medio",
        "dataEntrada":   date.today().isoformat(),
    }
    try:
        resp = requests.post(
            f"{CRM_API_URL}/api/clientes",
            json=payload,
            timeout=15,
        )
        if resp.status_code == 201:
            crm_id = resp.json().get("id", "—")
            logger.info(f"Lead registado no CRM: id={crm_id} nome={nome} servico={servico} canal={canal}")

            try:
                sender_id = tool_context.state.get("sender_id", "")
                if sender_id:
                    from .memory import save_perfil
                    perfil = (
                        f"Nome: {nome} | Serviço: {servico} | Tel: {telefone} | "
                        f"Email: {email} | Canal: {canal} | Detalhe: {qualificacao}"
                    )
                    save_perfil(sender_id, perfil)
                tool_context.state["sessao_concluida"] = True
            except Exception as mem_err:
                logger.warning(f"Memória não guardada (não afecta o CRM): {mem_err}")

            _notif_key = f"jetur:notificacao_enviada:{_canal_lock}:{_sender}"
            if _adquirir_lock(_notif_key):
                enviar_notificacao_ntfy(nome, servico, qualificacao, telefone, email, canal, tool_context)
            return f"Lead registado com sucesso no CRM. ID: {crm_id}. Nome: {nome}. Serviço: {servico}."
        else:
            erro = resp.json().get("erro", resp.text)
            logger.error(f"CRM devolveu erro {resp.status_code}: {erro}")
            return f"Erro ao registar lead no CRM ({resp.status_code}): {erro}"
    except Exception as e:
        logger.error(f"Excepção ao registar lead no CRM: {e}")
        return f"Erro ao registar lead: {str(e)}"

def notificar_equipa(nome: str, email: str, telefone: str, servico: str, qualificacao: str, canal: str, tool_context: ToolContext) -> str:
    """
    NOTIFICA A EQUIPA DE VENDAS via email ou outro canal interno.
    (Esta função é um placeholder e deve ser implementada com o método de notificação escolhido.)

    Args:
        nome: Nome do lead.
        email: Email do lead.
        telefone: Telefone do lead.
        servico: Serviço de interesse.
        qualificacao: Detalhes da qualificação.
        canal: Canal de origem.

    Returns:
        Confirmação de que a equipa foi notificada.
    """
    _sender = tool_context.state.get("sender_id", "")
    _canal_lock = tool_context.state.get("canal", "")
    _notif_key = f"jetur:notificacao_enviada:{_canal_lock}:{_sender}"
    if not _adquirir_lock(_notif_key):
        return "Equipa já notificada nesta sessão. Não repetir."

    enviar_notificacao_ntfy(nome, servico, qualificacao, telefone, email, canal, tool_context)
    return f"Equipa de vendas notificada sobre novo lead: {nome}, Serviço: {servico}."