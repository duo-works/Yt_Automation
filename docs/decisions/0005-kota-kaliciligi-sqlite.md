# 0005 — Kota sayacı SQLite'ta tutulur; durum katmanı için veritabanı kararı

- **Durum:** Kabul
- **Tarih:** 2026-07-29
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-24

## Bağlam

ADR-0004 *"veritabanı yok"* dedi ve gerekçesi doğruydu: **"günde 6 videoluk bir tavanda veritabanının çözeceği bir problem yok, ekleyeceği kurulum yükü var."** O gün ortada tek bir süreç vardı — elle tetiklenen yükleme hattı.

İki şey değişti:

1. **`kota.Sayac` bellekte yaşıyor.** Kendi docstring'i bunu itiraf ediyordu: *"tek çalıştırma tek oturum"*. Gün içindeki ikinci çalıştırma sıfırdan sayar, yani PRD'nin 2. başarı ölçütü (*"sistem hiçbir gün 10.000 birimi aşmaz"*) fiilen ölçülmüyordu.
2. **İkinci bir tüketici geldi.** Trend tespit hattı (DW-28…DW-32) aynı günlük bütçeden içecek: günde 24+ çalıştırma, yükleme hattından **ayrı bir süreçte**.

Yani asıl problem kalıcılık değil, **eşzamanlılık.** İki süreç "kalanı oku → yeter mi bak → harca" sırasını iç içe çalıştırırsa ikisi de aynı kalanı görür, ikisi de harcar ve bütçe sessizce aşılır. Kota aşımı da ucuz değil: reddedilen istek de birim harcıyor, yani sınırı geçtikten sonra sistem kendini onarmıyor, sadece boşa yakıyor.

## Değerlendirilen seçenekler

1. **JSON dosyası + dosya kilidi** — Bağımlılık yok, ADR-0004'ün çizgisini bozmaz. Ama doğru kilitleme yazmak (atomik oku-değiştir-yaz, çökme sonrası bayat kilit, platformlar arası `fcntl`/`msvcrt` farkı — ekipte Windows var) tam olarak `sqlite3`'ün hazır verdiği şeyi elden yazmak olurdu.
2. **Notion'a yazmak** — Ortak ve zaten var. Reddedildi: `query_data_sources` ücretsiz planda saatlik kotalı ve PRD aynı gerekçeyle Notion'ı yükleme kuyruğu olmaktan çıkarmıştı. Bir kota sistemini başka bir kotaya bağlamak.
3. **SQLite (standart kütüphane)** — İşlem (transaction) desteği hazır; `BEGIN IMMEDIATE` yazarları serileştiriyor. Yeni bağımlılık **yok** — `sqlite3` stdlib'de.
4. **Gerçek bir sunucu veritabanı** (Postgres vb.) — Tek makinede çalışan iki süreç için kurulum, servis ve sır yönetimi. Karşılığı yok.

## Karar

**Seçenek 3.** Kota harcaması `veri/yt_automation.db` içinde bir SQLite tablosunda tutulur.

Üç tasarım detayı kararın parçası:

**Ekle-only defter.** Her harcama bir satır (`gun`, `an`, `islem`, `birim`, `surec`); günün toplamı `SUM`'dan okunur, hiçbir yerde önbelleğe alınmaz. Bellekteki bir "kalan" değeri iki süreçli dünyada anında bayatlıyor. Yan fayda: bütçe beklenmedik şekilde bittiğinde kimin harcadığı defterde yazıyor.

**Kontrol yazmanın içinde.** `harca()` tek bir `BEGIN IMMEDIATE` işleminde hem toplamı okur hem satırı yazar. Ayrılsalardı TOCTOU yarışı kalırdı — ki bu, ADR'nin çözmek için var olduğu şeyin ta kendisi. Aynı sebeple `rezerve` parametresi (trend hattının dokunamayacağı yükleme payı) çağıranda değil, `harca()`'nın içindedir.

**Gün sınırı Pasifik takviminde.** Kota Pasifik gece yarısı sıfırlanıyor, UTC'de değil. `kota_gunu()` bunu `zoneinfo` ile çözer. Sabit `-8` ofseti varsaymak yaz saatinde bir saat kayardı; UTC gününü kullanmak sınırı sekiz saat kaydırırdı — ikisi de günde bir kez ya bütçeyi ikiye katlar ya da erken kapatır.

ADR-0004'ün *"veritabanı yok"* maddesi **bu alan için** değiştirilmiştir. Yükleme hattının girdi biçimi değişmiyor: kuyruk hâlâ bir dizin, metadata hâlâ video başına bir `.yaml`. Veritabanı yalnızca **süreçler arası paylaşılan durum** için.

## Sonuçlar

**Kolaylaştırdıkları:** Kota muhasebesi artık gerçekten ölçülebilir; PRD'nin 2. başarı ölçütü kâğıt üstünden çıktı. DW-28'in zaman serisi deposu aynı dosyayı ve aynı bağlantı katmanını kullanacak, ikinci bir mekanizma gerekmiyor. Defter bir denetim izi.

**Zorlaştırdıkları ve kabul edilen kısıtlar:**

- **`tzdata` bağımlılığı — yalnızca Windows'ta.** `zoneinfo` orada sistem tz veritabanı bulamıyor ve `ZoneInfoNotFoundError` fırlatıyor. Platform işaretli (`sys_platform == 'win32'`) eklendi. ADR-0004'ün "dört çalışma zamanı bağımlılığı" disiplini teknik olarak beşe çıktı; bedel bilinçli, çünkü alternatifi DST kurallarını elle yazmak.
- **Depo makineye bağlı.** `veri/` git'e girmiyor ve iki geliştiricinin sayaçları ayrı. Bugün doğru: kota **Google Cloud projesi** bazında ve API çağrılarını tek makine yapıyor. İkinci bir makineden de çağrı yapılırsa bu varsayım kırılır ve muhasebe paylaşılan bir yere taşınmalı.
- **Defter büyüyor, budanmıyor.** Günde ~30 satırda yıllarca sorun değil; gerektiğinde eski günler silinir. Şimdi yazılmayan kod.
- **SQLite tek makinede doğru, ağ üstünde değil.** Zamanlanmış çalışma bir sunucuya taşınırsa (DW-8) bu karar yeniden değerlendirilmeli — ağ dosya sistemleri üzerinde SQLite kilitleme güvenilir değil.
- **`yeter_mi()` artık yalnızca tavsiye.** Dürüst isimlendirme yerine dürüst docstring seçildi: gerçek karar `harca()` içinde veriliyor, `yeter_mi()` kullanıcıya erken bilgi vermek için duruyor.
