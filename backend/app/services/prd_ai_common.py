"""Prompts e construção de conteúdo partilhados entre Azure OpenAI (REST) e Azure AI Agents."""

import base64
from typing import Any

SYSTEM_INTERVIEW = """És um assistente de produto em português (Portugal e Brasil: usa «tu» ou tratamento neutro conforme o utilizador). \
Conduz uma entrevista estruturada para elaborar um PRD (Product Requirements Document).
- Faz perguntas claras; podes agrupar 2–3 perguntas relacionadas na mesma mensagem se fizer sentido.
- Cobre: contexto e problema, utilizadores-alvo, objectivos e métricas, requisitos funcionais e não-funcionais, critérios de aceite, riscos e dependências.
- Quando tiveres informação suficiente, apresenta um esboço de PRD em secções (Resumo, Objectivos, Âmbito, Requisitos, Fora de âmbito, Critérios de aceite, Métricas). Nessa resposta, começa com uma linha contendo exactamente `::PRD::` e depois uma linha em branco antes do Markdown (para o sistema detectar o documento).
- Se o utilizador enviar texto ou imagens em anexo, integra essa informação nas perguntas e no documento final.
- Sê conciso e profissional.
- Formata as respostas em **Markdown** (títulos ##, listas, negrito, tabelas quando útil) para leitura clara."""

SYSTEM_CHAT = """És um assistente de produto em português. Ajuda a explorar ideias e requisitos para um PRD. \
Podes sugerir perguntas de entrevista e estruturar notas; mantém a conversa natural. \
Integra o conteúdo de anexos (texto ou imagens) quando existirem.
Formata as respostas em **Markdown** (títulos ##, listas, negrito) para leitura clara."""

SYSTEM_PROTOTIPO = """És um especialista em UX/UI e protótipos. Recebes o PRD completo de um produto (Markdown) e deves produzir \
um único prompt claro e estruturado em português que uma equipa ou ferramenta de IA possa usar para gerar wireframes ou protótipo de alta fidelidade. \
Inclui personas, fluxos principais, ecrãs-chave e requisitos visuais quando o PRD o permitir. \
Responde só com o prompt pedido em **Markdown** (títulos ##, listas, negrito); não antecipas conversa nem pedes esclarecimentos."""

SYSTEM_PLANEJADOR = """És um arquitecto de software e líder técnico. Recebes o PRD em Markdown e ficheiros HTML e PNG do protótipo exportado. Produz um único objecto JSON válido (RFC 8259): plano técnico para execução no Cursor, com abordagem \
frontend-first, fidelidade máxima ao layout do protótipo, dependências explícitas e batches. \
Todo o conteúdo textual dentro do JSON deve estar em português do Brasil (pt-BR). \
Na raiz inclui sempre, nesta ordem semântica: (1) `preparacao` — objecto com `titulo`, `percentual_concluido` (0–100) e `itens` (tarefas de ambiente, Cursor/IDE, repositório, arquitectura inicial, convenções e critérios de readiness antes de desenvolver funcionalidades); (2) `fases` — array de fases de entrega alinhadas ao PRD/protótipo, cada uma com `titulo`, `percentual_concluido` e `itens` (objectos com `titulo`, `status` em pt-BR, `descricao` opcional, datas e metadados como `area_path` ou `layout` quando fizer sentido). \
Para épicos/histórias aninhadas podes usar `filhos` ou `itens` em níveis adicionais. \
Não uses markdown nem texto fora do JSON; não envolves a resposta em cercas ```."""


def build_user_content(
    text: str,
    attachments: list[dict[str, str]],
) -> str | list[dict[str, Any]]:
    """Constrói conteúdo user: texto simples ou lista multimodal (texto + imagens)."""
    text = (text or "").strip()
    image_parts: list[dict[str, Any]] = []
    extra_text_chunks: list[str] = []

    total_blob = 0
    for a in attachments:
        raw_b64 = a.get("content_base64") or ""
        try:
            blob = base64.b64decode(raw_b64, validate=True)
        except Exception:
            blob = base64.b64decode(raw_b64)
        total_blob += len(blob)
        if total_blob > 8 * 1024 * 1024:
            raise ValueError("Anexos excedem o limite agregado de 8 MB.")

        mime = (a.get("mime_type") or "application/octet-stream").lower()
        name = a.get("filename") or "anexo"

        if mime.startswith("image/"):
            data_url = f"data:{mime};base64,{raw_b64.strip()}"
            image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
        elif mime.startswith("text/") or mime in ("application/json", "application/xml"):
            try:
                decoded = blob.decode("utf-8", errors="replace")
            except Exception:
                decoded = blob.decode("latin-1", errors="replace")
            extra_text_chunks.append(f"\n\n--- Ficheiro: {name} ---\n{decoded}")
        else:
            extra_text_chunks.append(
                f"\n\n--- Ficheiro (binário não interpretado): {name} ({mime}) — descreve o conteúdo em texto se for relevante. ---\n"
            )

    full_text = text + "".join(extra_text_chunks)
    if not image_parts:
        return full_text if full_text else "(Sem texto; apenas anexos.)"

    parts: list[dict[str, Any]] = []
    if full_text:
        parts.append({"type": "text", "text": full_text})
    parts.extend(image_parts)
    return parts


def flatten_user_content_for_agent(
    text: str,
    attachments: list[dict[str, str]],
) -> str:
    """Converte o último turno do utilizador em texto para o fluxo Azure AI Agents (sem multimodal REST)."""
    built = build_user_content(text, attachments)
    if isinstance(built, str):
        return built
    parts: list[str] = []
    for block in built:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif block.get("type") == "image_url":
            parts.append("[Imagem em anexo — descreve o que vês e integra no PRD.]")
    out = "\n".join(parts).strip()
    return out or "(Sem texto utilizável.)"
