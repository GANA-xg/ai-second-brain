# AI Second Brain - System Architecture

```mermaid
flowchart TD

    A[Internet] --> B[HTTPS]
    B --> C[Nginx]

    C --> D[Next.js Frontend]
    C --> E[FastAPI Backend]

    E --> F[PostgreSQL]
    E --> G[Redis]
    E --> H[Qdrant]
    E --> I[Gemini API]
    E --> J[Storage]
```
