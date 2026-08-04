# /pr-ac

Değişikliği PR'a dönüştürür ve Notion'daki üç kaydı senkronlar.

## 1. Ne değiştiğini doğrula

```bash
git status
git diff
git log --oneline main..HEAD
```

Kullanıcıya özetle. **Commit edilmemiş değişiklik varsa** önce onu sor — kendi başına commit'leme.

Commit mesajlarını da kontrol et: her biri Conventional Commits formatında ve gövdesinde `Notion: DW-<n>` olmalı. CI bunu zorunlu tutuyor (`pr-kurallari.yml` → `commit-mesaji`); uymayan varsa PR açmadan önce söyle.

## 2. Kapsamı kontrol et

- **PR başına tek görev.** İki görev karışmışsa dur, kullanıcıya söyle. Asıl
  ölçüt budur — satır sayısı değil.
- **~1.200 satır hedefi.** Aşıyorsa uyar; görevi Notion'da bölmek gerekebilir.

  > Eşik 2026-08-04'te 400'den yükseltildi. Sebebi: bu repoda hiçbir PR 400'ü
  > tutmadı ve tutamazdı — bir özellik kod + test + ADR ile birlikte geliyor,
  > testler bu projede kodun kendisinden uzun (ölçüldü: DW-58 PR'ı 1.214 satır,
  > 519'u test). Kimse uyarıya bakmadı, çünkü her PR'da çıkıyordu.
  > **Tutulmayan kural, tutulan kuralların da ciddiyetini aşındırır.**
  >
  > Yeni eşik de bir hedef, kapı değil: aşan PR reddedilmiyor, sorgulanıyor.
  > Bölme kararının gerçek ölçütü satır değil **tek görev** kuralı; 1.500
  > satırlık tek bir mantıksal değişiklik, 300 satırlık iki ayrı işten daha
  > kolay review edilir.
- `.env` veya sır sızmış mı bak.
- Kalıcı bir mimari karar alındıysa `docs/decisions/` altında ADR var mı kontrol et.

## 3. Başlığı üret

```
<tür>(<kapsam>): <açıklama> [DW-<numara>]
```

Türkçe açıklama. `[DW-<numara>]` zorunlu — CI reddeder.

## 4. Gövdeyi doldur

`.github/pull_request_template.md` şablonunu kullan. **Bu oturumun `📓 Oturum Kaydı` kaydındaki "Ne yapıldı" bölümünden besle** — zaten yazılmış olanı tekrar üretme.

Zorunlu: `## Notion görevi` bölümünde DW numarası **ve gerçek Notion linki**. Şablondaki `Link:` satırı yorum olarak kalırsa CI düşer (`pr-govdesi`).

"Nasıl test edildi" bölümünde dürüst ol: çalıştırılmayan testi çalıştırıldı gibi yazma, atlanan kapsamı belirt.

## 5. PR'ı aç

```bash
git push -u origin HEAD
gh pr create --title "<başlık>" --body "<gövde>"
```

Bir başka PR'ın üstüne çalışıyorsan `--base <o-branch>` ekle (stacked PR).

## 6. Notion'u senkronla

Üç yer güncellenir:

| Nerede | Ne |
|---|---|
| `📋 Görevler` → görev | `Durum = In review`, `GitHub PR` = PR linki |
| `📓 Oturum Kaydı` → bu oturum | `GitHub PR` = PR linki |
| PR gövdesi | Notion görev linki (adım 4'te yapıldı) |

## 7. CI'ı bekle ve raporla

Check'lerin sonucunu izle. Kırmızı varsa hangi job'ın neden düştüğünü kullanıcıya söyle — "CI kırmızı" demek yeterli değil.
