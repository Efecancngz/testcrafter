# testcrafter

AI-powered test scenario generator + automated runner. Give it a URL and a short description of what to test — it crawls the page, asks an AI provider to generate test scenarios, runs them with Playwright, and shows pass/fail results.

🇹🇷 [Türkçe](README.tr.md)

## Why

A single project demonstrating backend API design, AI integration, and QA test automation together. See `docs/architecture.md` for the full design rationale.

## Stack

FastAPI · SQLAlchemy · SQLite · Playwright · React (Vite) · Claude / Gemini (pluggable AI provider layer)

## Quick start

```bash
git clone <repo-url>
cd testcrafter
cp .env.example .env   # set AI_PROVIDER, the matching API key (ANTHROPIC_API_KEY or GEMINI_API_KEY), and SECRET_KEY
docker compose up --build
```

Backend: http://localhost:8000 (docs at `/docs`)
Frontend: http://localhost:5173

On first use, register an account in the app — every project/scan is scoped to your login.

## Documentation

- [Architecture](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [AI provider interface](docs/ai-provider-interface.md)
- [Data model](docs/data-model.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT — see [LICENSE](LICENSE)
