# Plataforma de Gestão e Governança de Projetos com IA

Monorepo: **FastAPI** + **Vue 3**, design **The Sovereign Ledger**.

## Subir tudo com Docker (recomendado)

Na pasta **`plataforma-governanca-ia`**:

```powershell
docker compose build
docker compose up -d
```

| Serviço | URL |
|--------|-----|
| **Aplicação (UI + `/api` via Nginx)** | http://localhost:8080 |
| API direta (opcional) | http://localhost:8000 |
| MinIO API | http://localhost:9000 |
| MinIO Console | http://localhost:9001 (`minioadmin` / `minioadmin`) |
| PostgreSQL | `localhost:5432` (user/pass/db: `governanca`) |
| Redis | `localhost:6379` |

Edite **`compose.env`** para `SECRET_KEY`, `GITHUB_CLIENT_ID` e `GITHUB_CLIENT_SECRET`.  
Integrações GitHub na API usam apenas o token OAuth de cada utilizador. Para OAuth, registe o callback **exatamente**: `http://localhost:8080/api/auth/github/callback`

Logs:

```powershell
docker compose logs -f backend wiki-worker frontend
```

Parar:

```powershell
docker compose down
```

(Dados Postgres e MinIO ficam nos volumes `pgdata` e `miniodata`.)

### Credenciais seed

- `admin@empresa.com.br` / `admin123`
- `coordenador@empresa.com.br` / `coord123`

---

## Desenvolvimento local (sem Docker)

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Proxy `http://localhost:5173` → API em `:8000`.

### Worker da Wiki (Redis)

```powershell
cd backend
python -m app.worker
```

### Schema SQLite antigo

```powershell
cd backend
python scripts/migrate_sqlite.py
```

---

## Variáveis e integrações

- **PostgreSQL** (Docker): `postgresql+asyncpg://governanca:governanca@postgres:5432/governanca`
- **Wiki**: fila Redis; worker `wiki-worker`
- **Anexos**: MinIO; `S3_PUBLIC_ENDPOINT_URL` expõe presigned ao browser em `localhost:9000`
- Detalhes adicionais: `.env.example` na raiz e `frontend/.env.example`
