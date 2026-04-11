from sqlalchemy import delete, select

from app.db.sync_session import sync_session_scope
from app.models.project import Project, ProjectWiki, WikiDocument
from app.services.github_client import fetch_doc_markdown_sync, parse_github_repo_url
from app.services.github_tokens import resolve_github_token_for_project_api_sync


def run_generate_wiki(wiki_id: int, project_id: int, actor_user_id: int) -> None:
    with sync_session_scope() as session:
        wiki = session.execute(select(ProjectWiki).where(ProjectWiki.id == wiki_id)).scalar_one_or_none()
        project = session.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not wiki or not project or wiki.project_id != project.id:
            return
        wiki.error_message = None
        session.execute(delete(WikiDocument).where(WikiDocument.wiki_id == wiki_id))

        if not project.github_repo_url or not project.github_tag:
            wiki.status = "error"
            wiki.error_message = "Repositório ou tag ausente"
            return

        try:
            ref = parse_github_repo_url(project.github_repo_url)
        except ValueError as e:
            wiki.status = "error"
            wiki.error_message = str(e)
            return

        token = resolve_github_token_for_project_api_sync(session, actor_user_id)
        if not token:
            wiki.status = "error"
            wiki.error_message = (
                "Sem token GitHub OAuth para o utilizador que pediu a wiki. Ligue a conta com login OAuth GitHub "
                "(Configurações → Integrações ou «Sincronizar com GitHub» no projeto), com a mesma conta que tem acesso ao repositório."
            )
            return
        docs, err = fetch_doc_markdown_sync(ref.owner, ref.name, project.github_tag, token)
        if err:
            wiki.status = "error"
            wiki.error_message = err
            return
        for path, title, md in docs:
            session.add(WikiDocument(wiki_id=wiki_id, path=path, title=title, markdown=md))
        wiki.status = "ready"
        wiki.error_message = None
