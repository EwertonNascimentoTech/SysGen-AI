"""Testes do payload planejamento → Kanban (ordem e marcador; sem ORM)."""

from app.services.planejamento_kanban_payload import (
    MARKER,
    build_card_description,
    build_task_title,
    flatten_planejamento_for_kanban,
    truncate_bloco_tag,
)


def test_flatten_preparacao_then_fases() -> None:
    data = {
        "preparacao": {
            "titulo": "Preparação: ambiente, arquitetura e Cursor",
            "itens": [
                {"titulo": "Configurar ambiente de desenvolvimento", "descricao": "Instalar dependências"},
                {"titulo": "Definir arquitetura", "descricao": ""},
            ],
        },
        "fases": [
            {
                "titulo": "Fase 1 — Auth",
                "itens": [{"titulo": "Login", "descricao": "Tela de login"}],
            },
        ],
    }
    rows = flatten_planejamento_for_kanban(data)
    assert len(rows) == 3
    assert rows[0][0] == "Preparação: ambiente, arquitetura e Cursor"
    assert rows[0][1] == "Configurar ambiente de desenvolvimento"
    assert "Instalar dependências" in rows[0][2]
    assert rows[0][3] == ""
    assert rows[1][1] == "Definir arquitetura"
    assert rows[2][0] == "Fase 1 — Auth"
    assert rows[2][1] == "Login"


def test_marker_constant() -> None:
    assert MARKER.startswith("__")


def test_flatten_includes_layout_like_roadmap() -> None:
    """Caminhos `layout` / listas passam para a descrição do item (sincroniza com o cartão do roadmap)."""
    data = {
        "fases": [
            {
                "titulo": "Fase Login",
                "itens": [
                    {
                        "titulo": "Login Stitch",
                        "descricao": "Implementar ecrã",
                        "layout": "prototipo_export/Login_-_Stitch_Legal/ecra.html",
                    },
                    {
                        "titulo": "Dois HTML",
                        "layouts": [
                            "prototipo_export/A/ecra.html",
                            "prototipo_export/B/ecra.html",
                        ],
                    },
                ],
            },
        ],
    }
    rows = flatten_planejamento_for_kanban(data)
    assert len(rows) == 2
    assert "layout: prototipo_export/Login_-_Stitch_Legal/ecra.html" in rows[0][2]
    assert "Implementar ecrã" in rows[0][2]
    assert rows[0][3] == ""
    assert "layout:" in rows[1][2]
    assert "prototipo_export/A/ecra.html" in rows[1][2]
    assert "prototipo_export/B/ecra.html" in rows[1][2]
    assert rows[1][3] == ""


def test_flatten_entrega_resumo_from_planejamento() -> None:
    entrega = "index.html\n\nEstrutura da tela de autenticação…"
    data = {
        "fases": [
            {
                "titulo": "Auth",
                "itens": [
                    {
                        "titulo": "Login",
                        "descricao": "Tela de login",
                        "o_que_foi_entregue": entrega,
                    },
                    {
                        "titulo": "Lista de ficheiros",
                        "deliverables": ["index.html", "style.css", "script.js"],
                    },
                ],
            },
        ],
    }
    rows = flatten_planejamento_for_kanban(data)
    assert len(rows) == 2
    assert rows[0][3] == entrega
    assert rows[1][3] == "index.html\nstyle.css\nscript.js"


def test_build_card_matches_user_example() -> None:
    phase = "Preparação: ambiente, arquitetura e Cursor"
    item = "Configurar ambiente de desenvolvimento"
    assert build_task_title(item) == item
    assert truncate_bloco_tag(phase) == phase
    desc = build_card_description(item, item)
    assert MARKER in desc
    assert "Título: Configurar ambiente de desenvolvimento" in desc
    assert "Descrição: Configurar ambiente de desenvolvimento" in desc
