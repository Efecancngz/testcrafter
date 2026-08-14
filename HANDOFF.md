# Handoff — testcrafter
Son güncelleme: 2026-08-14 (crawler/runner navigasyon hataları düzeltildi, uçtan uca kanıtlandı), güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Dashboard redesign PR #5 ile `main`'e merge edildi. Sonrasında kullanıcı gerçek sitelerde tarama denedi ve `status: failed` aldı; kök nedenler bulunup düzeltildi. **Şu an `main` temiz, 64 backend testi yeşil, iş tamamlanmış durumda.**

### Bu oturumda düzeltilen 3 gerçek hata

1. **Şemasız URL'ler (`6b4c9d3`)** — `github.com` gibi şemasız bir girdi Playwright'ın `page.goto()`'su tarafından "Cannot navigate to invalid URL" ile reddediliyordu; kullanıcıya sadece anlamsız bir `failed` görünüyordu. `ScanCreate.target_url` artık bir Pydantic `field_validator` ile eksik şemayı `https://` olarak tamamlıyor.

2. **Crawler navigasyonu (`7fad4d9`)** — iki ayrı sorun:
   - `page.goto()` varsayılan `wait_until="load"` kullanıyordu; tek bir takılı alt-kaynak (reklam, analytics beacon, yavaş CDN görseli) tüm navigasyonu timeout'a kadar askıda bırakıyordu. Artık `domcontentloaded` + kısa, best-effort `networkidle` bekleme kullanılıyor.
   - Bazı ağlarda (DPI middlebox'lar, kurumsal proxy'ler, bazı ISP'ler) Chromium'un HTTP/2 bağlantıları belirli hostlara takılıyor; aynı hostlar HTTP/1.1 üzerinden sorunsuz açılıyor. `--disable-http2` ile launch ediliyor. **Bu ortamda `github.com` tam olarak bu yüzden açılmıyordu** (ampirik olarak doğrulandı: `--disable-http2` ile 200 OK, onsuz timeout).

3. **Runner aynı ayarları kullanmıyordu (`824d3bd`)** — runner kendi browser'ını başlatıyor ve kendi varsayılanlarını taşıyordu, dolayısıyla crawler düzeltmesi scan'i `ready`'ye getiriyor ama çalıştırma hâlâ step 0'da aynı sitelerde takılıyordu. Ayarlar `backend/app/browser.py`'ye çıkarıldı; crawler ve runner ikisi de oradan import ediyor. İkisinin tekrar ayrışmasını engelleyen bir test eklendi (`test_run_scenario_navigates_with_shared_browser_settings`).

Navigasyon timeout'u artık `CRAWLER_TIMEOUT_MS` env var'ı ile ayarlanabilir (varsayılan 30000).

### Uçtan uca kanıt
`demo@testcrafter.dev` hesabıyla (parola `TestCrafter2026!`, lokal Docker DB'sinde duruyor) 3 sitede gerçek tarama + çalıştırma yapıldı:

| Site | Scan durumu | Senaryo | Geçen run | Ekran görüntüsü |
|---|---|---|---|---|
| the-internet.herokuapp.com/login | ready | 4 | 3/4 | 24 |
| demo.playwright.dev/todomvc | ready | 1 | 0/1 | 3 |
| github.com | ready | 2 | 1/2 | 7 |

Ekran görüntüleri açılıp görsel olarak doğrulandı — gerçek, tam render edilmiş sayfalar (boş/hatalı değil).

## Sıradaki somut adım
Belirlenmiş bir sonraki iş yok. Aşağıdaki üç konu **bu oturumun hatası değil**, ayrı ve önceden var olan kalite sınırlamaları — istenirse ayrı ticket olabilir:

- **Runner'da tuş basma aksiyonu yok.** todomvc senaryosu input'u dolduruyor ama Enter'a basamadığı için todo hiç oluşmuyor. Mevcut aksiyon sözlüğü: `goto`/`click`/`fill`/`expect_text`/`expect_url`/`expect_visible`. Bir `press` aksiyonu gerçek bir boşluğu kapatır.
- **Pozisyonel seçiciler kırılgan.** Crawler `a[href] >> nth=2` gibi seçiciler üretiyor; github.com'da bu gizli bir linke denk geldi ve run başarısız oldu. Daha anlamlı seçiciler (text/rol/aria tabanlı) üretmek kaliteyi ciddi artırır.
- **AI bazen yanlış beklenti üretiyor.** herokuapp'te yanlış şifre senaryosu "Your username is invalid!" bekledi, site "Your password is invalid!" döndü. Burada testcrafter **doğru** çalışıyor (gerçek uyuşmazlığı yakaladı), sorun senaryo üretim kalitesinde.

## Bilinmesi gerekenler
- `hcahsap.pages.dev` bu ortamdan **hiç** açılmıyor (`ERR_CONNECTION_CLOSED`, HTTP/2 kapalıyken de). curl ve bağımsız iki ağdan da doğrulandı — testcrafter bug'ı değil, sitenin/ağın kendi sorunu.
- Frontend Docker'da anonim `node_modules` volume'ü kullanıyor; yeni bağımlılık eklendiğinde `docker compose up --build --renew-anon-volumes` (veya önce `down -v`) gerekiyor, yoksa Vite yeni paketleri bulamıyor. `CONTRIBUTING.md`'de yazılı.
- Backend `--reload` ile çalışmıyor; kod değişikliğinden sonra `docker compose restart backend` gerekiyor.
- Backend'i lokal (Docker'sız) çalıştırmak için `SECRET_KEY` ve AI key'leri env var olarak export edilmeli — `main.py` dotenv otomatik yüklemiyor.
- AI provider yapılandırılı değilse scan `status: "failed"` ile sonuçlanır, crash etmez — bilinen/tasarlanmış davranış.

## İlgili dosyalar
- `backend/app/browser.py` — crawler + runner'ın paylaştığı browser/navigasyon ayarları (yeni)
- `backend/app/crawler.py`, `backend/app/runner.py` — ikisi de yukarıdaki ayarları kullanıyor
- `backend/app/api/scans.py` — `ScanCreate.target_url` şema normalizasyonu
- `backend/tests/fixtures/slow_resource_page.html` — takılı alt-kaynak regresyon fixture'ı

## Son 3 commit
- 824d3bd fix: apply the crawler's navigation settings to the runner too
- 7fad4d9 fix: make crawler survive stalled resources and broken HTTP/2 networks
- 6b4c9d3 fix: auto-prepend https:// to scan target URLs missing a scheme
