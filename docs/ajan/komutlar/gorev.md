# /gorev DW-\<numara\>

Bir görevi almanın ilk üç adımını tek komutta yapar: Notion'da görevi üstlen, doğru formatta branch aç, oturum kaydını başlat.

Argüman verilmediyse kullanıcıya DW numarasını sor. **ID uydurma.**

## 1. Görevi çek

Notion `📋 Görevler` (`collection://887316e7-61e2-4fd6-815e-282afbbd9e54`) içinden `userDefined:ID` ile bul. Kullanıcıya göster: başlık, tür, öncelik, durum, sahip, gövdedeki açıklama.

Kontrol et ve gerekiyorsa uyar:

- Görev **başkasının üstündeyse** → dur, kullanıcıya sor
- Durum zaten `In progress` veya `In review` ise → dur, üzerine yazma
- Görev bir başkasına bağımlıysa (gövdede "önce şu bitmeli" gibi) → söyle

## 2. Görevi üstlen

`Durum = In progress`, `Sahip = kullanıcı`.

## 3. Branch aç

```bash
git switch main
git pull
git switch -c <tür>/DW-<numara>-<kisa-aciklama>
```

`<tür>` görevin Notion'daki `Tür` alanından türetilir:

| Notion `Tür` | branch türü |
|---|---|
| Özellik | `feat` |
| Hata | `fix` |
| Dokümantasyon | `docs` |
| Teknik borç | `chore` veya `refactor` |
| Araştırma | `docs` |

`<kisa-aciklama>`: küçük harf, tek tire ile ayrık, **Türkçe karaktersiz** (ş→s, ı→i, ğ→g, ü→u, ö→o, ç→c). CI bu formatı zorunlu tutuyor (`pr-kurallari.yml` → `branch-adi`), uymayan branch'in PR'ı kırmızı olur.

Branch adını Notion görevindeki `Branch` alanına da yaz.

## 4. Oturum kaydını başlat

`/oturum-basla` adımlarını uygula — çakışma kontrolü dahil. Kayıttaki `Görev` alanı bu göreve, `Branch` alanı yeni branch'e bağlanır.

## 5. Raporla

Görevin özeti, açılan branch, oturum kaydı linki. Sonra kullanıcıya ne yapmak istediğini sor — göreve kendi başına başlama.
