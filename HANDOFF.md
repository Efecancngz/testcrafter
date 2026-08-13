# Handoff — testcrafter
Son güncelleme: 2026-08-13 (runner action vocabulary final fix pass sonrası), güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Runner action vocabulary (branch `feat/runner-action-vocabulary`) tamamlandı: AI sağlayıcılarının ürettiği desteklenmeyen action isimleri (`navigate`, `assertVisibility` gibi) artık runner tarafından tanınıyor. `backend/app/ai/prompts.py`'de paylaşılan `SYSTEM_PROMPT` desteklenen action'ları açıkça listeliyor; `backend/app/runner.py`'de synonym normalization eklendi ve yeni bir `expect_visible` action'ı tanıtıldı. Bu, güncel oturumda çalışılan dört özelliğin sonuncusuydu (Gemini adaptörü ✅ → screenshot capture ✅ → auth sistemi ✅ → runner action vocabulary ✅).

Whole-branch final review, bu fix dalgasıyla giderilen 1 Critical ve 3 Important bulgu buldu:
- **Critical:** `expect_visible`, Playwright'ın auto-wait yapmayan `page.is_visible()` metodunu kullanıyordu; dinamik sayfalarda (SPA/React — bu ürünün asıl hedefi) bir önceki adımdan hemen sonra render olan elementler yanlışlıkla "not visible" olarak fail ediliyordu. `wait_for_selector(state="visible", timeout=5000)` ile değiştirildi.
- **Important:** `_normalize_action`, synonym tablosunda bulunamayan action'lar için orijinal (küçük/büyük harf karışık) string'i döndürüyordu; bu yüzden `"Click"` gibi Title-cased bir canonical isim tanınmıyordu. Artık lowercase edilmiş hali fallback olarak döndürülüyor.
- **Important:** `"press": "click"` ve `"open": "goto"` synonym eşlemeleri, semantik olarak farklı bir action'ı (ör. Enter tuşuna basma) sessizce yanlış bir action'a (click) dönüştürüp sahte bir "passed" sonucu üretebiliyordu — bir QA aracında sahte yeşil, sahte kırmızıdan daha kötü. İkisi de tablodan kaldırıldı.
- **Important:** Synonym tablosunda asimetri vardı (`assertVisibility` var ama daha idiomatik `assertVisible`/`checkVisible` yoktu, `check_text` var ama `check_url` yoktu). Dört eksik synonym eklendi.

Tüm backend test suite'i (49 test) geçti.

## Sıradaki somut adım
Sıradaki iş henüz belirlenmedi — kullanıcıyla görüşülmeli.

## Bilinmesi gerekenler
- Plan/spec: `.superpowers/sdd/2026-08-13-runner-action-vocabulary/` altında
- `test_run_scenario_expect_visible_fails_for_hidden_element` artık ~5 saniye sürüyor (önceden ~0s) çünkü `wait_for_selector` timeout'u dolana kadar bekliyor — bu beklenen, kabul edilebilir bir trade-off, hata değil
- Synonym tablosu artık şunları İÇERMİYOR: `"press"` (click ile karıştırılabilir, gerçek bir Playwright `press()` semantiği var), `"open"` (genelde dropdown/modal açma anlamına gelir, literal navigasyon değil)

## İlgili dosyalar
- `backend/app/runner.py` — `_ACTION_SYNONYMS`, `_normalize_action`, `expect_visible` action implementasyonu
- `backend/app/ai/prompts.py` — paylaşılan `SYSTEM_PROMPT`, desteklenen action listesi
- `backend/tests/test_runner.py` — synonym normalization ve `expect_visible` testleri

## Son 3 commit
- 930d31b fix: address final review findings in runner action vocabulary
- c5c5815 docs: document supported scenario actions and prompt sharing
- f8ebf9a feat: normalize action synonyms and add expect_visible to the runner
