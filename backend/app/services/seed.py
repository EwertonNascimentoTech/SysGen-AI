from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.directory import Directory
from app.models.kanban import KanbanTemplate, KanbanTemplateColumn
from app.models.project import Project
from app.models.user import Role, User
from app.services.column_rules import default_rules_dict, dumps_rules


async def seed_if_empty(session: AsyncSession) -> None:
    r = await session.execute(select(User).limit(1))
    if r.scalar_one_or_none():
        return

    roles_data = [
        ("admin", "Administrador"),
        ("coordenador", "Coordenador"),
        ("po", "Product Owner"),
        ("dev", "Desenvolvedor"),
        ("visualizador", "Visualizador"),
    ]
    roles: dict[str, Role] = {}
    for code, name in roles_data:
        role = Role(code=code, name=name)
        session.add(role)
        roles[code] = role
    await session.flush()

    admin = User(
        email="admin@empresa.com.br",
        full_name="Administrador",
        hashed_password=hash_password("admin123"),
    )
    admin.roles = [roles["admin"], roles["coordenador"]]
    session.add(admin)

    coord = User(
        email="coordenador@empresa.com.br",
        full_name="Maria Coordenadora",
        hashed_password=hash_password("coord123"),
    )
    coord.roles = [roles["coordenador"]]
    session.add(coord)

    for dname in ["STI", "Operações", "Inovação"]:
        session.add(Directory(name=dname))

    await session.flush()

    tpl = KanbanTemplate(name="Fluxo padrão (Anexo C)", status="publicado", version=1)
    session.add(tpl)
    await session.flush()
    cols_titles = [
        "Backlog",
        "Em concepção",
        "Em desenvolvimento",
        "Em homologação",
        "Concluído",
    ]
    col_objs: list[KanbanTemplateColumn] = []
    for i, title in enumerate(cols_titles):
        c = KanbanTemplateColumn(
            template_id=tpl.id,
            title=title,
            position=i,
            rules_json=dumps_rules(default_rules_dict(i)),
        )
        session.add(c)
        col_objs.append(c)
    await session.flush()

    dir_sti = (
        await session.execute(select(Directory).where(Directory.name == "STI"))
    ).scalar_one()
    p = Project(
        name="Piloto Governança IA",
        product_owner="João PO",
        directory_id=dir_sti.id,
        methodology="prd",
        planned_start=date.today() - timedelta(days=30),
        planned_end=date.today() + timedelta(days=60),
        template_id=tpl.id,
        current_column_id=col_objs[2].id,
        github_repo_url="https://github.com/org/repo",
    )
    session.add(p)

    await session.commit()
