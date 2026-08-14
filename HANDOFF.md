# Handoff — testcrafter
Son güncelleme: 2026-08-14 (dashboard redesign'in 8 task'ının tamamı shipped), güncelleyen: Claude Sonnet 5

## Şu an ne yapılıyor
**Dashboard redesign tamamlandı** — `docs/superpowers/specs/2026-08-13-dashboard-redesign-design.md`'den yazılan 8 task'lık plan (`.superpowers/sdd/2026-08-14-dashboard-redesign/`) baştan sona uygulandı, `feat/dashboard-redesign` branch'inde:

- **Backend (Task 1-3):** `Scan.created_at` migration'ı, `GET /projects/{id}`, `GET /projects/{id}/scans` (hafif `ScanSummaryOut` — senaryo taşımıyor, N+1 riski yok). 60 backend testi (yeni ownership/ordering testleri dahil) yeşil.
- **Frontend scaffolding (Task 4):** `react-router-dom`, Tailwind, shadcn/ui kuruldu.
- **Paylaşılan bileşenler (Task 5):** `StatusBadge`, `Layout`, `RequireAuth`, `LoginPage`.
- **Sayfalar (Task 6-7):** `ProjectListPage`, `ProjectDetailPage` (404 tespiti `err.status === 404` ile, string-matching değil), `ScanDetailPage`, `Screenshot` bileşeni.
- **Routing entegrasyonu (Task 8, bu oturum):** `frontend/src/App.jsx` tamamen yeniden yazıldı — eski tek-parça (single-page) yapı kaldırıldı, 4 route (`/login`, `/`, `/projects/:projectId`, `/scans/:scanId`) `RequireAuth` + `Layout` ile sarmalanarak bağlandı.

Tam manuel uçtan uca doğrulama yapıldı (Chrome MCP ile): login redirect, register, proje oluşturma, scan oluşturma (AI provider bu ortamda yapılandırılı olmadığı için scan'ler beklenen şekilde `failed` durumuna düştü — bu proje için bilinen/beklenen davranış), scan detay sayfası, proje detayına dönüp scan history tablosunda (en yeni üstte) görme, logout + logout sonrası `/`'e girince tekrar `/login`'e yönlenme, var olmayan proje/scan id'lerinde "not found" mesajı (crash yok). Hepsi beklendiği gibi çalıştı. Detaylar: `.superpowers/sdd/2026-08-14-dashboard-redesign/task-8-report.md`.

## Sıradaki somut adım
Branch tam review'e hazır: `feat/dashboard-redesign` → `main`. Kullanıcı PR açmaya veya `finishing-a-development-branch` skill'i ile ilerlemeye karar verebilir. Bu oturumda PR açılmadı, sadece kod + HANDOFF commit edildi.

## Bilinmesi gerekenler
- Backend'i lokal çalıştırmak için `SECRET_KEY` (ve varsa `ANTHROPIC_API_KEY`/`GEMINI_API_KEY`) repo kökündeki `.env`'den `uvicorn`'u başlatmadan önce ortam değişkeni olarak export edilmeli — `main.py` dotenv otomatik yüklemiyor, sadece gerçek env var'lara bakıyor.
- AI provider yapılandırılı değilse (veya API key geçersizse) scan oluşturma `status: "failed"` ile sonuçlanır, crash etmez — bu, `backend/app/api/scans.py`'nin bilinen/tasarlanmış exception handling davranışı, bug değil.
- `docker-compose.yml`/`.env.example` dashboard redesign için yeni env var gerektirmedi.

## İlgili dosyalar
- `.superpowers/sdd/2026-08-14-dashboard-redesign/` — planın 8 task brief'i + her task'ın raporu
- `docs/superpowers/specs/2026-08-13-dashboard-redesign-design.md` — orijinal tasarım spec'i
- `frontend/src/App.jsx` — yeni routed yapı (route tanımları burada)
- `frontend/src/pages/`, `frontend/src/components/` — sayfa ve paylaşılan bileşenler
- `backend/app/api/projects.py` — `GET /projects/{id}`, `GET /projects/{id}/scans`

## Son 3 commit
- (bu commit) feat: wire up dashboard routing, remove single-page layout
- d240d39 feat: add ScanDetailPage and Screenshot component
- 413d4ab fix: use error.status instead of message text for 404 detection in ProjectDetailPage
