#!/usr/bin/env python3
"""
Teste de requisição real ao Azure AI:

  - Azure OpenAI: POST .../deployments/{deployment}/chat/completions (mensagem mínima)
  - Azure AI Agents: um turno de chat (igual ao fluxo PRD)

Uso (pasta backend, com env carregado):
  PYTHONPATH=. python scripts/test_azure_ai_request.py

Variáveis: as mesmas de compose.env / .env (ver .env.example).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from app.services.epa_service import run_azure_ai_request_probes

    print("=== Teste de requisição Azure AI (POST real) ===\n")
    data = await run_azure_ai_request_probes(None)

    print("Resumo:", data["message"])
    print("\nOpenAI REST (chat/completions):")
    print("  ok:   ", data["openai_request_ok"])
    print("  detalhe:", data["openai_request_detail"])
    print("\nAzure AI Agents (turno mínimo):")
    print("  ok:   ", data["agents_request_ok"])
    print("  detalhe:", data["agents_request_detail"])
    print()

    sys.exit(0 if data["ok"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
