# Handoff — testcrafter
Son güncelleme: 2026-08-13 (auth sistemi final fix pass sonrası), güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Auth sistemi (branch `feat/auth-system`) tamamlandı: JWT tabanlı email+şifre girişi, tüm endpoint'ler (`projects`, `scans`, screenshot proxy) kullanıcıya bağlandı, sahiplik kontrolleri (404-not-403) eklendi, frontend'e login/register UI eklendi. Bu, üç planlanmış özelliğin (Gemini adaptörü → screenshot capture → auth sistemi) sonuncusuydu. Planın 5 task'ı da ayrı ayrı review'den temiz geçti — Task 4 (screenshot proxy) özellikle sıkı bir güvenlik incelemesinden geçti (ownership chain, path traversal, auth bypass kontrolleri).

Whole-branch final review 2 Critical bulgu buldu (bu proje için üçüncü kez art arda — sadece final review'de görülen entegrasyon hataları): `docker-compose.yml`'de `SECRET_KEY` container'a geçmiyordu (Docker üzerinden her login 500 dönüyordu), ve `test_api_projects.py`'deki gerçek-deployment testi sabit bir email ile gerçek DB'ye kullanıcı yazıyordu — ikinci çalıştırmada kalıcı olarak fail oluyordu. Ayrıca 4 Important (SECRET_KEY lazy check yerine startup-time check, 401'de login formuna dönmeme, register'ın token başarısız olursa orphan user bırakması, 72 byte üstü şifrenin 500 vermesi) ve 3 Minor bulgu düzeltildi. Tek fix dalgasıyla hepsi çözüldü, re-review temiz.

## Sıradaki somut adım
`feat/auth-system` branch'i için finishing-a-development-branch akışını tamamla (test doğrulaması yapıldı, 44/44 geçti — idempotency de doğrulandı, suite iki kez üst üste çalıştırıldı). PR açma/merge kararı kullanıcıdan bekleniyor.

**Bu, testcrafter için planlanmış üç özelliğin sonuncusuydu** (Gemini adaptörü ✅ → screenshot capture ✅ → auth sistemi ✅). Sıradaki iş henüz belirlenmedi — kullanıcıyla görüşülmeli.

## Bilinmesi gerekenler
- Plan: `docs/superpowers/plans/2026-08-13-auth-system.md`, spec: `docs/superpowers/specs/2026-08-13-auth-system-design.md`
- Bilinçli olarak ertelenen bulgular: stale-schema startup check (migration yok, sadece `CONTRIBUTING.md`'de "local db'yi sil" notu var), Swagger `/docs`'taki "Authorize" butonunun OAuth2 form format'ıyla uyumsuz olması (kozmetik, dev-tooling), tek bir uçtan-uca çok-kullanıcılı entegrasyon testi (mevcut per-endpoint testler zaten sahiplik mantığını kapsıyor)
- `SECRET_KEY` artık gerçek anlamda startup-time kontrolü — `app.auth` import edildiği an (yani app başlarken) `RuntimeError` fırlatıyor, sadece token issuance sırasında değil
- AI provider'ların ürettiği scenario action'ları (`navigate`, `assertVisibility` gibi) runner'ın desteklediği vocabulary ile hâlâ tam örtüşmüyor — bilinen, önceden var olan, auth'tan bağımsız bir sorun, hâlâ kendi ticket'ını hak ediyor

## İlgili dosyalar
- `backend/app/auth.py` — hash/JWT/`get_current_user`, artık import-time `SECRET_KEY` kontrolü
- `backend/app/api/auth.py` — register/login, flush-then-commit-after-token sırası
- `backend/app/api/projects.py` / `scans.py` — `_demo_user` kaldırıldı, tüm endpoint'ler `get_current_user` + sahiplik kontrolü kullanıyor
- `docker-compose.yml` — `SECRET_KEY` environment'a eklendi
- `frontend/src/api.js` / `App.jsx` — auth header'ları, `setUnauthorizedHandler` ile 401'de login formuna dönüş, screenshot blob fetch

## Son 3 commit
- b2221a7 fix: address final auth-system integration review findings
- 0122422 feat: add frontend auth UI and authenticated screenshot fetch, update docs
- 8964c06 feat: replace screenshot static mount with an authorizing proxy endpoint
