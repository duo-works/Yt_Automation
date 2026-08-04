# /denetle

`/soguk-baslangic` çıktısını kaynaklara karşı denetler. Kullanıcı özeti yapıştırır, sen doğrularsın.

> ⚠️ **Farklı bir oturumda çalıştır.** Özeti üreten oturum kendi çıktısını denetlerse aynı kör noktaları taşır ve denetim değersizleşir. Kullanıcı aynı oturumdaysa uyar.

Burada **statik bir cevap anahtarı yok** — kasten. Anahtar bakım ister, bakılmazsa sessizce yanlış ölçer. Onun yerine kaynaklara bakılır: proje durumu değişse de kaynaklar aynı yerde durur.

## 1. Kaynakları doğrula

Özetteki **her** iddia için kaynağı çek ve iddianın gerçekten orada yazdığını gör.

| Alan | Kaynak | Nasıl doğrulanır |
|---|---|---|
| Proje ne yapıyor | PRD §Problem · `README.md` başlığı | sayfayı çek |
| Aşama | Görevler durumları · açık PR'lar · `git rev-list --count origin/main` | sorgu + komut |
| v1 kapsam dışı | PRD §Kapsam — ilk sürümde OLMAYACAKLAR | sayfayı çek |
| Kısıtlar | PRD §Bilinen kısıtlar | sayfayı çek |
| Sıradaki iş / blokaj | Görevler (`Durum != Done`) · PR `mergeStateStatus` | sorgu + `gh pr view` |
| Aktif oturum | Oturum Kaydı (`Durum = 'Devam ediyor'`) | sorgu |

Üç sonuç mümkün: **doğrulandı**, **kaynak iddiayı desteklemiyor**, **kaynak yok**.

## 2. Tuzakları kontrol et

Bunlar akıl yürütme hataları, gerçek değil — proje durumu değişse de aynı kalırlar:

1. **Açık soruyu karar gibi sunmak** — PRD'de cevaplanmamış bir şey kesinleşmiş gibi anlatılmış mı?
2. **Kapsam dışını kapsam sanmak** — "OLMAYACAKLAR" listesindeki bir şey yapılacaklar arasında gösterilmiş mi?
3. **Merge edilmemiş işi merge edilmiş sanmak** — PR'daki bir şey `main`'de var gibi anlatılmış mı?
4. **Bağımlı görevi hazır sanmak** — önkoşulu bitmemiş bir görev "yapılabilir" denmiş mi?
5. **Bloke işi yapılabilir sanmak** — blokaj atlanmış mı?
6. **"Teyit edilmeli" denen sayıyı kesin gerçek gibi sunmak** — kaynak şüphe belirtmişken özet belirtmemiş mi?
7. **Kaynaksız iddia** — en ağırı, tek başına başarısızlık sebebi.

## 3. Geçme ölçütü

**Geçti:** altı alanın hepsi kaynaklı ve doğrulanmış, hiçbir tuzağa düşülmemiş.

**Kaldı:** tek bir kaynaksız iddia bile yeterli.

"Bilmiyorum" ve "erişemedim" **başarısızlık değildir** — dürüstlük sinyalidir. Uydurma başarısızlıktır.

## 4. Raporla

```
ALAN DENETİMİ
  1 Proje ne yapıyor    ✅ doğrulandı
  2 Aşama               ❌ "kod var" denmiş, main tek commit
  ...

TUZAKLAR
  ✅ 1,2,4,5,6,7 temiz
  ❌ 3 — PR #1'deki komut seti main'de var gibi anlatılmış

SONUÇ: kaldı — 1 kaynaksız iddia, 1 tuzak

HANGİ DOKÜMAN YETERSİZ KALDI
  - README'nin "Bu proje şu an nerede" bölümü branch/main ayrımını söylemiyor
```

**Son bölüm bu işin asıl değeri.** Ajanı yargılamak amaç değil; hangi dokümanın yanlış anlaşılmaya açık olduğunu bulmak amaç. Düzeltme oraya gider.
