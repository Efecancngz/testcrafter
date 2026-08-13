# Handoff — testcrafter
Son güncelleme: 2026-08-13 (Alembic migration final fix pass sonrası), güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Alembic migration entegrasyonu (branch `feat/alembic-migrations`) tamamlandı. `Base.metadata.create_all()` yerine artık `backend/alembic/` altında migration'lar şemanın tek gerçek kaynağı. İlk migration mevcut 6 tabloyu (users, projects, scans, scenarios, runs, run_steps) yakalıyor. Docker `CMD`'si artık `alembic upgrade head && uvicorn ...` çalıştırıyor — otomatik, ek adım gerekmiyor.

Bu, kullanıcının "alembic ekleyelim" talebiyle başlayan iş — Gemini adaptörü/screenshot capture/auth/runner-fix'ten sonra bu oturumdaki beşinci feature branch'i.

Planın 3 task'ı da ayrı ayrı review'den temiz geçti. Bu arada iki gerçek yan sorun bulunup düzeltildi: (1) `backend/data/screenshots/` klasörünün `__init__.py`'si olmadığı için setuptools'un onu ikinci bir paket sanıp `pip install -e ".[dev]"`'i kırması (`pyproject.toml`'a `[tool.setuptools.packages.find] include = ["app*"]` eklendi), (2) `create_all` kaldırılınca bir testin gerçek DB'ye ihtiyaç duyması (Task 2 içinde ilk düzeltme).

**Whole-branch final review 2 Important bulgu buldu** (bu proje için altıncı kez art arda — sadece final review'de görünen entegrasyon hatası): test suite'in gerçek `testcrafter.db`'ye `create_all` ile şema yazması, bu da Alembic'in beklediği `alembic_version` satırı olmadan bir "poisoned" DB yaratıyordu — Docker'daki `volumes: ./backend:/app` bind mount'u sayesinde bu dosya container'a da sızıp `alembic upgrade head`'i "table already exists" hatasıyla çökertiyordu. Çözüm: test artık gerçek DB'ye hiç dokunmuyor, izole bir geçici engine'e `monkeypatch` ile yönlendiriliyor. İkinci bulgu: DB URL'i hem `alembic.ini`'de hem `app/db.py`'de ayrı ayrı hardcode edilmişti (spec'in "tek gerçek kaynak" kuralına aykırı, plan'ın kendi hatasıydı) — `env.py`'ye `app.db`'den fallback okuma eklendi, testin kendi override'ını bozmayacak şekilde. Ayrıca `test_alembic.py` artık Alembic'in kendi `compare_metadata` API'sini kullanıyor (sadece isim değil tip/nullability farkını da yakalıyor).

**Kendi Docker doğrulamam:** implementer'ın raporu Docker end-to-end testini network yavaşlığı yüzünden tamamlayamamıştı; ben ayrıca bir `--no-cache` rebuild yapıp gerçek container log'unu gördüm (`Running upgrade -> aef5c2b7f379, initial schema` + temiz uvicorn başlangıcı) — ilk denemede test ettiğim container aslında eski (Alembic'siz) bir imajdan çalışıyormuş, bunu fark edip düzelttim.

Tüm backend test suite'i (50 test) geçti; `testcrafter.db` artık test suite'i çalıştıktan sonra hiç oluşmuyor.

## Sıradaki somut adım
`feat/alembic-migrations` branch'i için finishing-a-development-branch akışını tamamla (test doğrulaması yapıldı). PR açma/merge kararı kullanıcıdan bekleniyor.

## Bilinmesi gerekenler
- Plan: `docs/superpowers/plans/2026-08-13-alembic-migrations.md`, spec: `docs/superpowers/specs/2026-08-13-alembic-migrations-design.md`
- Yeni şema değişikliği yapmak için: `app/models.py`'yi değiştir, `cd backend && alembic revision --autogenerate -m "..."`, üretilen dosyayı gözden geçir, commit et — elle düzenleme yapma
- `backend/tests/conftest.py`'deki `db_session` fixture'ı hâlâ `create_all` kullanıyor (in-memory test DB için) — bu bilinçli bir istisna, migration'lara geçmedi
- CI workflow'u hâlâ yok (bu işin kapsamı dışında tutuldu, kullanıcı bilinçli olarak erteledi)
- Bilinçli olarak ertelenen minor bulgular: `.dockerignore` eksikliği (kozmetik), `env.py`'nin `fileConfig(disable_existing_loggers=True)` davranışı (şu an hiçbir test log capture'a bağlı değil)

## İlgili dosyalar
- `backend/alembic/env.py` — `target_metadata` + URL fallback mantığı
- `backend/alembic/versions/aef5c2b7f379_initial_schema.py` — ilk migration, elle düzenlenmedi
- `backend/app/main.py` — `create_all()` kaldırıldı
- `backend/Dockerfile` — `CMD` artık migration'ı önce çalıştırıyor
- `backend/tests/test_alembic.py` — `compare_metadata` ile şema/model senkron kontrolü
- `backend/tests/test_api_projects.py` — gerçek DB yerine izole geçici engine kullanıyor

## Son 3 commit
- e3e190b chore: gitignore alembic init artifact, fix cd-chaining in setup docs
- 25c8aee test: check migrated schema against models with alembic's own diff api
- 1d67dae fix: derive alembic's default db url from app.db, not a duplicate hardcode
