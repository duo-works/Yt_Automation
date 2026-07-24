# AI Ajanı Konvansiyonları

Bu dosya Claude Code / Codex gibi ajanların bu repo'da çalışırken uyması gereken kuralları içerir. İnsan kuralları için [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Bağlam

Bu repo `duo-works` organizasyonuna ait, iki kişilik bir ekip tarafından geliştiriliyor. Görev takibi **Notion**'da, kod review **GitHub PR**'da yapılır. GitHub Issues kapalıdır.

## Kesin kurallar

1. **`main`'e doğrudan commit veya push yapma.** Her zaman branch aç.
2. **Branch adı:** `<tür>/DW-<numara>-<kisa-aciklama>` — Notion görev ID'si zorunlu. Kullanıcı ID vermediyse sor, uydurma.
3. **Commit mesajı:** Conventional Commits, açıklama Türkçe, gövdede `Notion: DW-<numara>` satırı.
4. **PR başlığı:** `<tür>(<kapsam>): <açıklama> [DW-<numara>]` — CI bu formatı zorunlu tutar.
5. **Repo köküne plan/rapor/analiz dosyası yazma.** Uzun form dokümantasyon Notion'a gider. Repo'da izin verilen doküman: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/` altı.
6. **Sır yazma.** `.env` dosyasına dokunma; yeni değişken gerekiyorsa `.env.example`'a değersiz olarak ekle.
7. **Kalıcı mimari karar alındığında** `docs/decisions/` altına ADR ekle (şablon: `docs/decisions/README.md`).

## Kod tarzı

- Çevredeki kodun stiline uy: isimlendirme, yorum yoğunluğu, dosya düzeni.
- Yeni bir bağımlılık eklemeden önce mevcut bağımlılıklarla çözülüp çözülmediğine bak.
- Kullanıcı istemediği sürece kapsamı genişletme; istenen işi eksiksiz yap.

## Commit ve push

- Kullanıcı açıkça istemedikçe commit veya push yapma.
- Commit yapılacaksa önce `git status` ve `git diff` ile ne değiştiğini doğrula.
