# /oturum-kapat

`AGENTS.md` → "Oturum SONUNDA" protokolünü uygula. İş bittiğinde çalıştırılır. Yarım kaldıysa bunun yerine `/devir` kullan.

## 1. Kendi kaydını bul

Notion `📓 Oturum Kaydı`'nda bu oturumda açtığın kayıt. Bulamıyorsan **yeni kayıt açma** — kullanıcıya sor. Yanlış kaydı kapatmak, başka bir ajanın aktif işini görünmez yapar.

## 2. Gövdeyi doldur

```markdown
## Ne yapıldı

- <somut çıktılar: hangi dosyalar, hangi kararlar, hangi PR>

## Sıradaki adım

- <bir sonraki oturumun nereden devam edeceği>

## Dikkat

- <varsa: bilinen sınır, atlanmış test, kabul edilmiş risk>
```

"Ne yapıldı" kısmında dürüst ol. Test çalıştırılmadıysa çalıştırılmadığını yaz; bir kısım atlandıysa atlandığını yaz. Bu kaydı okuyacak kişi senin ne yaptığını başka yerden doğrulayamaz.

## 3. Durumu ayarla

- İş bitti → `Durum = Tamamlandı`
- Tıkandın → `Durum = Bloke`, nedeni `## Dikkat` altına

## 4. PR varsa bağla

PR açıldıysa `GitHub PR` alanını doldur. Notion görevinin de `In review` durumunda ve PR linkinin ona da işlenmiş olduğunu doğrula.

## 5. Zamanlanmış hattı ilgilendiriyor mu

**Merge canlıya çıkmak demek değil.** Zamanlanmış trend otomasyonu ayrı bir
worktree'den, sabit bir ref'e iğnelenmiş olarak koşuyor (ADR-0008) ve o iğne
yalnızca elle taşınıyor:

```bash
scripts/zamanlama-kur.sh durum              # canlı hangi ref'te
scripts/zamanlama-kur.sh tazele --ref <ref> # iğneyi taşı
```

Değişiklik `src/yt_automation/` ya da `scripts/` altındaysa sor: canlının bu
kodu koşması gerekiyor mu? Gerekiyorsa tazelendi mi? Cevap ne olursa olsun
kaydın `## Ne yapıldı` bölümüne yaz — "merge edildi ama canlı hâlâ eski ref'te"
bilinmesi gereken bir durumdur, eksikliği değil.

Ölçüldü (2026-08-04): yedi PR'lık iş yazıldı, testleri geçti, merge edildi —
ve canlı otomasyon günlerce eski ref'ten koştuğu için hiçbiri çalışmadı. Kodun
yazılmış olmasıyla koşuyor olması karıştırıldı.

## 6. Raporla

Kullanıcıya kaydın kapandığını ve sıradaki adımın ne yazıldığını söyle.
