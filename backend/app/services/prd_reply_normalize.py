"""Deteção de respostas «documento PRD» e remoção do marcador opcional ::PRD::."""

PRD_MARKER = "::PRD::"


def looks_like_prd_document(text: str) -> bool:
    """Heurística para esboços longos com secções típicas de PRD (fallback sem marcador)."""
    t = (text or "").strip()
    if len(t) < 400:
        return False
    if "##" not in t:
        return False
    low = t.lower()
    signals = (
        "requisitos",
        "critério",
        "aceite",
        "âmbito",
        "ambito",
        "fora de âmbito",
        "prd",
        "product requirements",
        "objetivo",
        "métrica",
        "stakeholder",
    )
    return sum(1 for s in signals if s in low) >= 2


def strip_prd_marker_and_flag(text: str) -> tuple[str, bool]:
    """
    Se a resposta começar por ::PRD::, remove essa linha e marca como documento PRD.
    Caso contrário devolve o texto original e o resultado da heurística.
    """
    raw = text or ""
    stripped = raw.lstrip()
    if stripped.startswith(PRD_MARKER):
        i = raw.find(PRD_MARKER)
        rest = raw[i + len(PRD_MARKER) :].lstrip()
        if rest.startswith("\n"):
            rest = rest[1:]
        return rest, True
    return raw, looks_like_prd_document(raw)
