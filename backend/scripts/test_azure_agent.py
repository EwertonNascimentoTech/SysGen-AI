#!/usr/bin/env python3
"""
Teste de ligação Azure AI (Agents + OpenAI REST) para o chat PRD.

Uso (na pasta backend, com variáveis no ambiente ou .env):
  PYTHONPATH=. python scripts/test_azure_agent.py

Docker:
  docker compose --profile test run --rm test-azure-agent
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from app.services.epa_service import run_azure_ai_connection_tests

    print("=== Teste de ligação Azure AI (PRD) ===\n")
    data = await run_azure_ai_connection_tests(None)

    def line(label: str, val: object) -> None:
        print(f"  {label}: {val}")

    print("Resultado agregado:")
    line("ok", data["ok"])
    line("message", data["message"])
    print()
    print("Azure AI Agents:")
    line("  agents_ok", data.get("agents_ok"))
    line("  agents_detail", data.get("agents_detail"))
    print()
    print("Azure OpenAI (REST):")
    line("  openai_ok", data.get("openai_ok"))
    line("  openai_detail", data.get("openai_detail"))
    print()

    sys.exit(0 if data["ok"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
