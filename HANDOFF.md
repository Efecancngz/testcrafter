# Handoff — testcrafter
Son güncelleme: 2026-08-13 (screenshot capture final fix pass sonrası), güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Gemini adaptörü (PR #2) merge edildi. Screenshot capture (branch `feat/screenshot-capture`) tamamlandı: Playwright her adımda screenshot alıyor, `backend/data/screenshots/{run_id}/{step_index}.png` altına yazıyor, FastAPI `/screenshots` static mount ile serve ediyor, frontend gösteriyor. Planın 3 task'ı da ayrı ayrı review'den temiz geçti. Whole-branch final review'de bir önemli bulgu çıktı: `run_scan`'deki reorder (Run satırını flush edip id almak) SQLite yazma kilidini tüm tarayıcı çalışması boyunca açık tutuyordu ve crash durumunda `run_id` tekrar kullanılıp eski screenshot'larla çakışabiliyordu. Fix: Run satırı flush sonrası hemen commit ediliyor. Ayrıca static-serving'i uçtan uca test eden bir test eklendi (öncekiler sadece string format kontrol ediyordu, gerçek mount'u hiç test etmiyordu).

## Sıradaki somut adım
`feat/screenshot-capture` branch'i için finishing-a-development-branch akışını tamamla (test doğrulaması yapıldı, 23/23 geçti; PR açma/merge kararı kullanıcıdan bekleniyor). Sonrasında plandaki son özellik: **auth sistemi** — henüz brainstorm edilmedi.

**Önemli:** Final review, screenshot serving'in şu an auth'suz ve tahmin edilebilir ID'lerle (`/screenshots/{run_id}/{index}.png`) çalıştığını, bunun auth sistemi tasarımına dahil edilmesi gerektiğini not etti — auth brainstorming'inde bu nokta gündeme getirilmeli (run ownership kontrolü veya tahmin edilemez path).

## Bilinmesi gerekenler
- Plan: `docs/superpowers/plans/2026-08-13-screenshot-capture.md`, spec: `docs/superpowers/specs/2026-08-13-screenshot-capture-design.md`
- Bilinçli olarak ertelenen bulgular: screenshot retention/cleanup politikası yok (MVP kapsamı dışı), AI provider'ların ürettiği scenario action'ları runner'ın desteklediği vocabulary ile tam örtüşmüyor (ayrı, önceden var olan bir sorun — screenshot feature'ı etkilemiyor ama ilk gerçek kullanıcı izlenimi "kırmızı adımlar + doğru screenshot'lar" oluyor, ayrı bir ticket değeri var)
- Gemini adaptörü PR #2 merge edildi, `main`'de; branch silindi

## İlgili dosyalar
- `backend/app/runner.py` — `_finish()` helper, her adımda screenshot capture, hata izolasyonu
- `backend/app/api/scans.py` — `SCREENSHOTS_DIR`, `run_scan` reorder + erken commit, `RunStepOut.screenshot_path`
- `backend/app/main.py` — `/screenshots` static mount
- `frontend/src/App.jsx` — screenshot `<img>` render, `alt`/`loading="lazy"`

## Son 3 commit
- ac21d66 fix: commit Run row before browser launch, serve screenshots end-to-end in tests
- 07ea855 feat: display scenario screenshots in the frontend, update docs
- 4665aeb feat: persist and serve screenshot paths for scenario runs
