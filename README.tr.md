# testcrafter

AI destekli test senaryosu üretici + otomatik çalıştırıcı. Bir URL ve kısa bir test açıklaması ver — sayfayı tarar, bir AI sağlayıcısına test senaryoları ürettirir, Playwright ile çalıştırır, pass/fail sonuçlarını gösterir.

🇬🇧 [English](README.md)

## Neden

Backend API tasarımı, AI entegrasyonu ve QA test otomasyonunu tek bir projede bir araya getiren bir çalışma. Tam tasarım gerekçesi için `docs/architecture.md`.

## Stack

FastAPI · SQLAlchemy · SQLite · Playwright · React (Vite) · Claude / Gemini (değiştirilebilir AI sağlayıcı katmanı)

## Hızlı başlangıç

```bash
git clone <repo-url>
cd testcrafter
cp .env.example .env   # AI_PROVIDER ayarla ve uygun API anahtarını ekle (ANTHROPIC_API_KEY veya GEMINI_API_KEY)
docker compose up --build
```

Backend: http://localhost:8000 (dokümantasyon `/docs`)
Frontend: http://localhost:5173

## Dokümantasyon

- [Mimari](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [AI sağlayıcı arayüzü](docs/ai-provider-interface.md)
- [Veri modeli](docs/data-model.md)
- [Katkı rehberi](CONTRIBUTING.md)

## Lisans

MIT — bkz. [LICENSE](LICENSE)
