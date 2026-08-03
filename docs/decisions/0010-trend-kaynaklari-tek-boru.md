# 0010 — Trend kaynakları çoğalır, tek boruya akar

- **Durum:** Kabul
- **Tarih:** 2026-08-03
- **Karar verenler:** Mirza
- **İlgili görev:** DW-55, DW-56

## Bağlam

Kanal stratejisi format bazlı iki kanala döndü (uzun + Shorts, EN+ES). Shorts
tarafının ihtiyacı **tazelik**: Wikipedia pageviews günlük yayımlanıyor, yani
huni bir konunun patladığını en geç ~30 saat sonra öğreniyor. DW-54 sıçrama
detektörü o gecikmeyi kullanılabilir hale getirdi ama gecikmeyi *kaldıramaz* —
kaynak günlük.

Bu, hattın ilk kez **birden çok trend kaynağı** taşıyacağı anlamına geliyor:
Wikipedia (günlük, ücretsiz, güvenilir), Google Trends (saatlik, ücretsiz),
TikTok (en değerli sinyal, erişimi kısıtlı), ileride başkaları.

Karar anındaki risk açık: her kaynak kendi aday listesini, kendi skorunu ve
kendi Notion aktarımını yazarsa üç ayrı yarı-huni oluşur. Kapılar (DW-51),
format kırılımı (DW-52) ve pazar hedeflemesi (DW-53) yalnızca birinde çalışır;
diğer kaynaklardan gelen adaylar denetimsiz Notion'a düşer. Bu, DW-33'ün CI
tarafında yaşattığı hatanın aynısı olurdu: kontrol var sanılırken yok.

## Değerlendirilen seçenekler

1. **Kaynak başına bağımsız hat.** Her modül kendi keşif → skor → aktarım
   zincirini kurar. En hızlı yazılır; kapılar ve kalibrasyon çoğaltılır, biri
   güncellenip diğeri unutulur.
2. **Ortak soyut "TrendKaynagi" arayüzü.** Sınıf hiyerarşisi, her kaynak bir
   alt sınıf. İki kaynak varken erken soyutlama — PRD'nin kanal katmanı için
   verdiği kararla aynı gerekçe ("tek kanal bile yayında değilken neyin
   değişeceğini tahmin etmek erken soyutlamadır").
3. **Tek boru, takılabilir terim getirici.** Seçilen.

## Karar

Her yeni trend kaynağı yalnızca **terim üretir**. Terimden sonrası tek ve
ortak:

    kaynak terimi → Wikipedia makale eşleşmesi → Wikidata sınıfı
                  → makale + okunma (talep kanıtı)
                  → sıçrama detektörü (DW-54)
                  → sondaj + kapılar (DW-51/52/53)
                  → Notion

Uygulama biçimi sınıf değil **fonksiyon enjeksiyonu**: `gtrends.isle`
`terim_getir`, `makale_bul` ve `geo_kodlari` parametreleri alıyor; `tiktok`
modülü kendi terim kaynağını verip aynı boruyu çağırıyor. Yazma,
sınıflandırma, seri çekme ve tekrar-işlememe kodu tek yerde duruyor.

Üç kural bağlayıcı:

1. **Kaynak karar mercii değil, keşif kaynağıdır.** Hiçbir kaynak kapıları
   atlayamaz, doğrudan Notion'a yazamaz, kendi eşiğini koyamaz.
2. **Talep kanıtı olmadan konu boruya girmez.** Terim eşleşse bile okunma
   serisi yazılmıyorsa konu ne sıçrama detektörüne ne sondaj kuyruğuna girer.
   Bir kaynağın "trend" demesi, talebin ölçüldüğü anlamına gelmiyor.
3. **Dış kaynak ana hattı düşüremez.** Saatlik betikte GTrends adımı
   `basarisiz` işaretlemiyor, TikTok yapılandırılmamışsa sessizce atlanıyor.
   Gerekçe DW-47'nin dersi: yanlış alarm üreten bir bildirim düzeni, gerçek
   arızayı gürültünün içinde kaybeder.

### TikTok hakkında ölçülmüş gerçek

TikTok öncelikli tutuldu (kısa video trendleri orada doğuyor) ama ücretsiz
yolların tamamı 2026-08-03'te denendi ve kapalı:

| Yol | Sonuç |
|---|---|
| `creative_radar_api/.../hashtag/list` | HTTP 200, gövde `{"code":40101,"msg":"no permission"}` — tarayıcı UA ve Referer ile de aynı |
| Creative Center HTML | 21 KB boş SPA kabuğu; veri istemci tarafında yetkili API'den geliyor |

Çalıştırma yolları — üçü de bu görevin dışında karar gerektiriyor: headless
tarayıcı (ağır, TikTok'un JS imzasına bağımlı), Research API (resmî, ücretsiz,
**başvuru onayı** gerekiyor), üçüncü parti API (çalışıyor, ücretli).

**Kırılgan bir kazıyıcı yazmamak bilinçli.** Çalışmayan kaynak, çalıştığı
sanılan kaynaktan iyidir: ikincisi sessizce boş döner ve "TikTok'a da
bakıyoruz" yanılsaması üretir — bu projede tam olarak bu sınıftan üç hata
yaşandı (dal filtresi, CI tetikleyici, sınıflandırıcı alt çizgisi).

Bugün çalışan yol: `YT_TIKTOK_DOSYA` ile **elle besleme**. Creative Center'ı
tarayıcıda açıp hashtag'leri dosyaya yapıştırmak 30 saniye ve sinyal gerçek.
Otomatik kaynak geldiğinde `terim_getir` yerine geçiyor, boru değişmiyor.

## Sonuçlar

**Kolaylaşan:** Yeni kaynak eklemek bir fonksiyon yazmak demek; kapılar,
kalibrasyon ve Notion şeması otomatik geçerli. Kaynağın kırılması ana hattı
etkilemiyor.

**Kabul edilen kısıtlar:**

- **Wikipedia eşleşmesi darboğaz.** Wikipedia makalesi olmayan bir trend
  (yeni bir meme, henüz yazılmamış bir olay) boruya hiç giremez. Tarih/bilim
  kanalı için kabul edilebilir — o konuların Wikipedia karşılığı olur — ama
  saf güncel içerik için yapısal bir sınır.
- **Arama çağrısı toplu değil.** `list=search` tek sorgu alıyor, yani istek
  sayısı terim sayısı kadar; ilk canlı koşumda HTTP 429 alındı ve hız
  düşürüldü. Kaynak sayısı arttıkça bu sınır yeniden karşımıza çıkacak.
- **TikTok bugün elle.** Otomatik akış bir sonraki karara bağlı: Research API
  başvurusu mu, ücretli API mi. Ayrı görev olarak açılmalı.
- Boru tek olduğu için **borudaki bir hata bütün kaynakları** etkiliyor.
  Karşılığı: tek yerde düzeltiliyor ve testler tek yerde duruyor.
