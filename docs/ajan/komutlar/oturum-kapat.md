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

## 5. Raporla

Kullanıcıya kaydın kapandığını ve sıradaki adımın ne yazıldığını söyle.
