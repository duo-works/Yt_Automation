# ADR-0013 — Köprünün tüketici API'si sözleşme sahibinin reposunda yaşar

- **Durum:** Kabul edildi
- **Tarih:** 2026-08-05
- **Görev:** DW-80

## Bağlam

[ADR-0011](0011-trend-video-koprusu.md) köprüyü sözleşmeye bağladı: temas noktası `📈 Trend Adayları` veritabanı, hangi alanı kimin yazabileceği tablo halinde yazılı. Notion tarafı da tamamlandı — `Durum` akışının tümü (`Yeni → İnceleniyor → Seçildi → Üretiliyor → Üretildi → Yayınlandı`, ayrıca `Elendi`), `Video URL` ve `Üretim notu` alanları yerinde.

**Eksik olan tek şey tüketiciydi.** Kimse tabloyu okumuyordu; `tablo_studio` konu girdisini elle alıyordu. Sözleşme vardı, boru yoktu.

Soru "köprü nereden geçecek" değil (ADR-0011 cevapladı), **"okuma kodunu kim yazacak"**.

## Değerlendirilen seçenekler

1. **Notion istemcisini `tablo_studio`'ya yaz.** Tüketici kendi veritabanı erişimini kurar, filtreler, `Durum`'u kendi ilerletir.
2. **Sözleşme sahibi dar bir operasyon sunar.** `Yt_Automation` `ytoto aday listele/sec/bitir` verir; `tablo_studio` yalnızca çağırır.

## Karar

**İkincisi.** Tüketici API'si `src/yt_automation/trend/notion.py` içinde, yazan tarafın yanında yaşar.

Dört gerekçe, ağırlık sırasına göre:

### 1 · Sözleşme kodda zorlanır, yalnız dokümanda değil

ADR-0011 ölçüm alanlarını (`Hız`, `İvme`, `Boşluk skoru`, `Talep`, `Arz`, `Kaynak sayısı`, `Sınıf`) salt okuma ilan etti — ama bunu **hiçbir şey engellemiyordu.** Tüketici kendi PATCH gövdesini kuruyor olsaydı, bir ajanın "iyileştirme" niyetiyle skora dokunması mümkün kalırdı ve `tablo_studio`'nun `AGENTS.md`'si bu riski zaten uyarı olarak yazmıştı: *bu tür bir dokunuş kimseye görünmez ve huninin sıralamasını sessizce bozar.*

Dar operasyonda PATCH gövdesini sözleşmenin sahibi kuruyor. `adayi_sec` gövdesi tam olarak `{"Durum": ...}`; ölçüm alanı oraya **giremez**. Yazılı kural, zorlanan kurala dönüştü.

Bu, seçeneği belirleyen asıl gerekçe. Kalan üçü onu destekliyor.

### 2 · Tüketicinin bağımlılık yükü sıfır kalıyor

`tablo_studio`'da bağımlılık manifesti yok — bu yüzden `ci-ok` bile kurulamadı ([ADR-0012](0012-org-repo-politikasi.md), açık iş DW-77). Oraya bir Notion istemcisi yazmak yeni bir bağımlılık demekti. Bir CLI çağrısı hiçbir şey istemiyor.

Windows tarafı ayrıca sınanmış durumda: `scripts/oturum-sorgula.py` saf stdlib ile orada da çalışıyor.

### 3 · Şema eşlemesi tek yerde kalıyor

`"Shorts" ↔ "shorts"`, `"Uzun kanal" ↔ uzun format gibi eşlemeler zaten `bosluk_ozellikleri`'nde. `bosluklari_guncelle`'nin yorumu bu ayrışmayı çoktan uyarı olarak yazmıştı: *format eşlemesi tek yerde kalsın, yoksa aktarım ile güncelleme zamanla birbirinden ayrışır.* Okuma tarafını başka repoya koymak, aynı eşlemenin ikinci bir kopyasını yaratırdı.

### 4 · Eşzamanlı çalışmayı engellemiyor

Karar günü `tablo_studio`'da aktif bir oturum kaydı vardı ve tam o dosyalara dokunuyordu. Bu tasarım `Yt_Automation` içinde kaldığı için iki hat birbirini beklemedi. Geçici bir sebep — ama iki kişilik bir ekipte tekrarlayan bir durum.

## Yüzey

```
ytoto aday listele [--format shorts|uzun] [--limit N] [--json]
ytoto aday sec     <sayfa-url|kimlik> [--kuru]
ytoto aday bitir   <sayfa-url|kimlik> --video-url <link> [--not "..."] [--kuru]
```

`--json` çıktısının alan adları Notion sütun adlarından **bilinçle farklı** (`bosluk_skoru`, `onerilen_format`, …): sütun yeniden adlandırılırsa tüketici kırılmasın.

`sec` ve `bitir` hem sayfa URL'ini hem çıplak 32 haneli kimliği kabul ediyor — insan tarayıcıdan URL kopyalıyor, ajan `--json`'daki `kimlik` alanını geri veriyor.

## Korumalar

Her iki yazma yolu da tek bir gövdeden (`_durumu_ilerlet`) geçiyor. Ayrı yazmak, korumalardan birinin bir yolda unutulması demekti. İkisi de bu repoda **ölçülerek** öğrenildi:

| Koruma | Neyi engelliyor |
|---|---|
| **Çöp kontrolü** | Çöpe atılmış sayfaya PATCH başarılı döner ve hiçbir yerde görünmez. 2026-08-04'te yaşandı: mükerrer bir sayfa elle silinmiş, defter silineni gösteriyordu. |
| **Beklenen durum kontrolü** | Tek kontrol iki şeyi birden koruyor: iki tüketicinin aynı adayı kapması (yarış) ve insanın verdiği kararın ezilmesi. `bosluklari_guncelle` aynı gerekçeyle `DOKUNULMAMIS_DURUM` şartını taşıyor. |

`bitir` `video_url`'i zorunlu tutuyor: bağlantısız bir `Üretildi` köprünün geri dönüş yolunu koparır — trend hattı adayı tükenmiş sayar ama çıktının nereye gittiği hiçbir yerde yazmaz.

Dördü de mutasyonla sınandı: koruma kaldırıldığında testler düşüyor.

## Sonuçlar

- `tablo_studio`'nun işi üç komutu çağırmak; Notion istemcisi yazması gerekmiyor
- `Durum` akışının hangi ucunu kimin sürdüğü artık kodla ayrılmış durumda: trend hattı `Yeni`/`🔥 Acil`/`Elendi`, video hattı `Seçildi`/`Üretiliyor`/`Üretildi`
- Yeni bir tüketici (ör. ikinci bir üretim hattı) aynı komutları kullanır; sözleşme çoğaltılmaz
- **Bedeli:** video hattı `Yt_Automation`'ın kurulu olmasına bağımlı. İki repo zaten aynı makinede çalıştığı için bugün bedava; ayrışırlarsa bu ADR yeniden değerlendirilmeli.

## Not: köprünün taşıdığı yük ölçüldü

Karar günü Notion'daki 97 adayın **95'i `Elendi`, 2'si `Yeni`**. ADR-0011 yazıldığında 97'sinin tamamı `Yeni`ydi; aradaki fark kalibrasyon işinin (DW-51, DW-58) sonucu.

Bu köprüyü gereksiz kılmıyor — PRD günde 1–5 video diyor, iki aday bir günlük üretime yeter. Ama huninin verimi ayrı bir soru: 114 ölçülmüş adayın 106'sı tek bir kapıdan (`kalibre < 2.0 MAD`) eleniyor. Eşiğin doğru olup olmadığı bu ADR'nin konusu değil, ayrı bir görev.
