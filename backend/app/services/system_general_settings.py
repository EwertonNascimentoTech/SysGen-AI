from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_general_settings import SystemGeneralSettings

DEFAULT_ID = 1


async def ensure_system_general_settings_row(session: AsyncSession) -> SystemGeneralSettings:
    row = await session.get(SystemGeneralSettings, DEFAULT_ID)
    if row is None:
        row = SystemGeneralSettings(
            id=DEFAULT_ID,
            org_name="SysGen AI",
            locale="pt-BR",
            audit_strict=True,
            ai_indexing=False,
        )
        session.add(row)
        await session.flush()
    return row
