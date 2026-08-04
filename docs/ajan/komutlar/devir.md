# /devir

Yarım kalan işi bir sonraki oturuma devreder. İş bittiyse bunun yerine `/oturum-kapat` kullan.

Devri okuyacak kişi senin ne yaptığını başka yerden öğrenemez — kendi kardeş ajanın veya diğer geliştiricinin ajanı olabilir. Bu kayıt onların tek bağlamı.

## 1. Kendi kaydını bul

Notion `📓 Oturum Kaydı`'nda bu oturumda açtığın kayıt. Bulamıyorsan kullanıcıya sor; başkasının kaydını devretme.

## 2. Gövdeyi doldur

```markdown
## Ne yapıldı

- <tamamlanan somut çıktılar>
- <yarım kalanlar, hangi noktada bırakıldığıyla>

## Sıradaki adım

1. <devralan ajanın atacağı ilk adım — somut, dosya adı ve komut seviyesinde>
2. <sonraki>

## Dikkat

- <denenip işe yaramayan yollar — tekrar denenmesin>
- <bilinen sınır, atlanmış test, kabul edilmiş risk>
- <yerel durum: uygulanmamış migration, ayakta duran servis, worktree>
```

**"Sıradaki adım" en kritik bölüm.** "Devam et" yazma. Hangi dosya, hangi fonksiyon, hangi komut — devralan sıfırdan başlamasın.

Denenip işe yaramayan yolları yazmak da en az yapılanlar kadar değerli: aynı çıkmaza ikinci kez girilmesini engeller.

## 3. Durumu ayarla

`Durum = Devredildi` **ve** `Tür = Devir`. İkisi birlikte olmalı — `🤝 Devirler` görünümü `Tür` alanına bakıyor.

## 4. Yerel durumu bırak

- Commit edilmemiş değişiklik varsa kullanıcıya sor: commit mi, stash mi, olduğu gibi mi kalacak
- Branch push edilmemişse söyle — devralan onu göremez
- Worktree kullandıysan yolunu `## Dikkat` altına yaz

## 5. Raporla

Kullanıcıya devrin kaydedildiğini ve sıradaki adım olarak ne yazıldığını göster.
