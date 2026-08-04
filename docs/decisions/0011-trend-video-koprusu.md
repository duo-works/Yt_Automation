# ADR-0011 — Trend hattı ile video üretimi arasındaki köprü

- **Durum:** Kabul edildi
- **Tarih:** 2026-08-04
- **Görev:** DW-68

## Bağlam

Proje iki hat halinde yürüyor ve ikisi ayrı repolarda:

| Hat | Repo | Kim |
|---|---|---|
| Trend/aday tespiti | `duo-works/Yt_Automation` | Mirza |
| Video üretimi | `duo-works/tablo_studio` (+ `MoneyPrinterTurbo`) | Ömer |

İkisi arasında **tanımlı bir bağ yoktu.** Ölçülen durum (2026-08-04): trend hattı `📈 Trend Adayları` veritabanına **97 aday** düşürmüş, hepsi `Durum = Yeni` ve hiçbiri tüketilmemiş. `tablo_studio` konu girdisini elle alıyor, bu tabloyu hiç okumuyor.

Yani üretim tarafı, araştırma tarafının çıktısını kullanmıyor — hattın var olma sebebi tam olarak buydu.

Repoları birleştirmek düşünüldü ve **reddedildi**: bağımlılıklar çok farklı (`MoneyPrinterTurbo` 535 MB, Windows'a özgü venv yolları), CI'ları ortak olamaz, ve iki hattın çalışma temposu birbirini beklememeli.

## Karar

**Köprü `📈 Trend Adayları` veritabanıdır.** Kod bağımlılığı, paylaşılan repo veya doğrudan API çağrısı yok — tek temas noktası bu tablo.

### Sahiplik

| | Trend hattı (Yt_Automation) | Video hattı (tablo_studio) |
|---|---|---|
| Satır **oluşturma** | ✅ tek yazan | ❌ |
| Ölçüm alanları (`Hız`, `İvme`, `Boşluk skoru`, `Talep`, `Arz`, `Kaynak sayısı`) | ✅ tek yazan | ❌ salt okuma |
| `Durum` | yalnızca `Yeni` ve `🔥 Acil` | `İnceleniyor` → `Seçildi` → `Üretiliyor` → `Üretildi` → `Yayınlandı`, `Elendi` | 
| `Video URL`, `Üretim notu` | ❌ | ✅ tek yazan |

**Kural:** bir alanı yalnızca sahibi yazar. Trend hattı bir adayın `Durum`'unu `Yeni`'den ileri taşımaz; video hattı ölçüm alanlarına dokunmaz.

### Durum akışı

```
Yeni ──► İnceleniyor ──► Seçildi ──► Üretiliyor ──► Üretildi ──► Yayınlandı
  │                          │            │
  └──────────────────────────┴────────────┴──► Elendi
```

`🔥 Acil` — sıçrama detektörünün (DW-54) işaretlediği, hızla eskiyecek adaylar. `Yeni` ile aynı düzeyde ama önceliklidir.

### Tekrar önleme

Trend hattı, `Durum` alanı `Yeni`/`🔥 Acil` **dışında** olan bir konuyu yeniden aday olarak yazmaz. Bunun altyapısı zaten var: `aktarim` tablosu (`depo.py`, şema v6) hangi videonun/boşluğun aktarıldığını tutuyor ve `notion.py` içindeki `_aktarilanlar()` bunu okuyor.

⚠️ Bu ADR'den **önce** `Üretildi` diye bir durum yoktu; üretilen bir konunun geri dönüş yolu tanımsızdı ve aynı konu tekrar önerilebilirdi. Şema bu kararla genişletildi.

## Gerekçe

**Neden Notion, neden doğrudan API değil.** İki hat farklı makinelerde, farklı işletim sistemlerinde ve farklı tempolarda çalışıyor. Doğrudan çağrı, birinin ayakta olmasını diğerine şart koşardı. Notion asenkron bir kuyruk görevi görüyor: trend hattı yazar ve unutur, video hattı hazır olduğunda alır.

**Neden insan da görebiliyor.** Bu tablo aynı zamanda karar ekranı. PRD'nin dördüncü YPP karşı önlemi *"reddedebilen bir hat"* diyor; `Elendi` durumu bunun insan tarafındaki karşılığı. Bir kuyruk kütüphanesi (Redis, SQS) bunu vermezdi.

**Neden alan sahipliği katı.** Ortak Notion hesabı kullanılıyor ve iki taraf da ajanla çalışıyor. Sahiplik yazılı olmazsa bir ajanın "iyileştirme" niyetiyle ölçüm alanını ezmesi kimseye görünmez.

## Sonuçları

**Kazanılan:** İki hat birbirini beklemeden çalışır. Video hattı, kaynağı doğrulanmış (Wikipedia/Wikidata destekli) adaylarla beslenir — PRD'nin *"her videonun altında gerçek bir kaynak"* önlemine doğrudan hizmet eder.

**Kabul edilen:** Notion tek arıza noktası. Erişilemezse iki hat da körleşir. Karşılığında `notion-yedek` reposu var (haftalık betik + aylık resmî export) ve `scripts/oturum-sorgula.py` MCP kopukken doğrudan API'ye düşüyor.

**Açık kalan:** `tablo_studio`'nun bu tabloyu **okuyan** tarafı henüz yazılmadı; bugün elle kopyalanıyor. Otomatikleşmesi Ömer'in görevidir ve bu ADR onun sözleşmesidir.
