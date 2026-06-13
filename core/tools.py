import os
import logging
import requests
from datetime import date
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

CRM_API_URL = os.environ.get("CRM_API_URL", "https://jetur-crm.vercel.app")


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

            return f"Lead registado com sucesso no CRM. ID: {crm_id}. Nome: {nome}. Serviço: {servico}."
        else:
            erro = resp.json().get("erro", resp.text)
            logger.error(f"CRM devolveu erro {resp.status_code}: {erro}")
            return f"Erro ao registar lead no CRM ({resp.status_code}): {erro}"
    except Exception as e:
        logger.error(f"Excepção ao registar lead no CRM: {e}")
        return f"Erro ao registar lead: {str(e)}"


def notificar_equipa(
    nome: str,
    servico: str,
    qualificacao: str,
    telefone: str,
    email: str,
    canal: str,
) -> str:
    """
    Notificação à equipa de vendas — desactivada de momento.

    Args:
        nome: Nome do lead.
        servico: Serviço de interesse.
        qualificacao: Detalhes da qualificação.
        telefone: Contacto telefónico.
        email: Endereço de e-mail.
        canal: Canal de origem.

    Returns:
        Confirmação (notificações pausadas).
    """
    logger.info(f"notificar_equipa chamada (pausada): nome={nome} servico={servico} canal={canal}")
    return "Notificação à equipa registada."
