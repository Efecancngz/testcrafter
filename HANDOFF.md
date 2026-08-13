# Handoff — testcrafter
Son güncelleme: 2026-08-13 10:09, güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Gemini adaptörü + `AI_PROVIDER` env var seçimi ekleniyor (branch `feat/gemini-adapter`), subagent-driven-development ile Task 1 (GeminiProvider) tamamlandı, task review'i bekleniyor.

## Sıradaki somut adım
Task 1'in review paketini çıkar (`scripts/review-package`), task reviewer subagent'ı dispatch et; review temizse Task 2'ye (provider seçim mekanizması, `docs/superpowers/plans/2026-08-13-gemini-adapter.md`) geç. Sonrasında sırada screenshot capture ve auth sistemi var (henüz brainstorm edilmedi).

## Bilinmesi gerekenler
- Plan: `docs/superpowers/plans/2026-08-13-gemini-adapter.md`, spec: `docs/superpowers/specs/2026-08-13-gemini-adapter-design.md`
- SDD ledger: `.superpowers/sdd/2026-08-13-gemini-adapter/progress.md` (git-ignored, sadece bu makinede)
- Python bağımlılıkları global ortama kuruldu (venv yok) — `google-genai` henüz eklenmedi, Task 1 implementer'ı bunu ekleyecekti, sonucu doğrulanmadı
- Bu dosya (HANDOFF.md) proje standardına (§16, vault: Yazılım Projesi Standartları.md) uyularak bugün ilk kez oluşturuldu — önceki oturumlarda yoktu

## İlgili dosyalar
- `backend/app/ai/gemini_provider.py` — bu oturumda eklendi
- `backend/app/api/scans.py` — Task 2'de `get_ai_provider()` değişecek
- `CLAUDE.md` — bu dosyaya pointer eklenmesi gerekiyor (yapılmadıysa)

## Son 3 commit
- d088ac8 feat: add GeminiProvider implementing AIProvider
- a1d9345 docs: add implementation plan for Gemini adapter
- 86e2bb0 docs: add design spec for Gemini adapter + provider selection
