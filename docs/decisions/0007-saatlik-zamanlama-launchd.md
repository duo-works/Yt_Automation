# 0007 — Saatlik trend taraması `launchd` ile zamanlanır

- **Durum:** Kabul
- **Tarih:** 2026-07-30
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-32

## Bağlam

Trend hattı zaman serisine dayanıyor: hız iki ölçüm arasındaki farktan, ivme üç ölçümden hesaplanıyor (DW-29). Elle çalıştırılan bir hat seri üretemiyor — ilk üç koşumu elle tetiklemek zorunda kaldım ve aralarında 16 ve 25 dakika bekledim.

`chart=mostPopular` yaklaşık saatlik tazeleniyor, yani saatlikten sık örneklemenin bilgi getirisi yok, sadece kota yiyor.

Kalıcı bir host (DW-8, deploy hedefi) henüz seçilmedi. O gelene kadar hat Mirza'nın makinesinde çalışacak ve makine kapalıyken boşluk oluşacak — DW-29 tam olarak buna dayanıklı olacak şekilde yazıldı.

## Değerlendirilen seçenekler

1. **Elle çalıştırma (mevcut durum)** — Hiçbir şey kurmak gerekmiyor ama seri oluşmuyor. İvme üç ölçüm istiyor; günde bir kez elle çalıştırılan bir hat üç günde bir ivme veriyor.
2. **`cron`** — macOS'ta hâlâ çalışıyor ama kaçırılan koşumu telafi etmiyor: laptop 03:00'te kapalıysa o koşum kaybediliyor. Ayrıca `cron` ortam devralmıyor ve `PATH` sorunları sessiz başarısızlık üretiyor.
3. **`launchd` + `StartCalendarInterval`** — Takvim tabanlı; laptop kapalıysa o saati atlıyor ve bir sonraki saati bekliyor.
4. **`launchd` + `StartInterval`** — Aralık tabanlı; uyanışta kaçırılan koşumu hemen çalıştırıyor.
5. **Bulut zamanlayıcı** (GitHub Actions cron, Cloud Scheduler) — Doğru uzun vadeli cevap ama DW-8'e bağlı ve API anahtarının bir sırlar deposuna taşınmasını gerektiriyor. Bugünkü ihtiyacın önüne geçiyor.

## Karar

**`launchd` + `StartInterval: 3600`**, macOS'ta kullanıcı düzeyinde bir LaunchAgent olarak.

`StartInterval` seçildi çünkü laptop kapalıyken kaçırılan koşumu uyanışta telafi ediyor. DW-29 düzensiz örneklemeye dayanıklı ama hiç örnek almamak yine de veri kaybı — telafi etmek boşluğu kısaltıyor.

Görev üç parçadan oluşuyor ve hepsi repo'da:

| Dosya | Ne yapıyor |
|---|---|
| `scripts/works.duo.yt-trend.plist` | `launchd` tanımı, yer tutucularla (commit edilebilir) |
| `scripts/saatlik-tarama.sh` | Ortamı kuruyor, koşumları sırayla yapıyor, günlüğe yazıyor |
| `scripts/zamanlama-kur.sh` | `kur` / `durum` / `kaldir` (ADR-0008 `tazele`'yi ekledi) |

### Geniş tarama günde bir, derin tarama saat başı

| Koşum | Sıklık | Maliyet | Ne besliyor |
|---|---|---|---|
| Geniş (111 bölge) | günde 1 | 222 birim | bölge sıralaması |
| Derin (20 bölge) | saat başı | 40 birim | zaman serisi |

Geniş taramayı saat başı yapmak günde 5.328 birim eder — günlük bütçenin yarısı, yükleme hattının payını yer. Derin tarama 24 × 40 = 960 birim ve `TREND_KOTA_TAVANI` (2.500) içinde kalıyor.

### plist mutlak yol içermiyor

Şablonda `__PROJE__` ve `__BETIK__` yer tutucuları var; `zamanlama-kur.sh` bunları kurulum anında dolduruyor. Böylece plist commit edilebiliyor ve iki farklı makinede de çalışıyor.

> ADR-0008 yer tutucu setini `__CALISMA__` / `__BETIK__` / `__VERI__` / `__ENV__` olarak değiştirdi: kod, veri ve sırlar artık ayrı yollarda.

## Sonuçları

**Kazanç:** İvme gerçekten hesaplanabiliyor. Kurulumun kendisi doğrulandı — görev 15:04'te kendiliğinden çalıştı, geniş taramayı (9.583 ölçüm) ve derin taramayı (1.980 ölçüm) yaptı, sınıflandırmayı koştu.

**Kabul edilen kısıtlar:**

- **Yalnızca macOS.** Ömer Windows'ta çalışıyor; oradaki karşılığı Görev Zamanlayıcı ve yazılmadı. Trend hattı Mirza'nın makinesinde çalıştığı için bugün engel değil, ama iş bölümü değişirse ayrı görev gerekiyor.
- **Laptop kapalıyken boşluk oluşuyor.** Kalıcı host DW-8'e bağlı. Boşluklar hız hesabını bozmuyor, çözünürlüğü düşürüyor.
- ~~**Sessiz başarısızlık riski.** Betik hataları günlüğe yazıyor ama kimseye bildirmiyor. `zamanlama-kur.sh durum` son koşumun çıkış kodunu gösteriyor; düzenli bakılması gereken bir şey. Bildirim eklemek bugünün ihtiyacı değil.~~
  > **Bu değerlendirme aynı gün yanlışlandı.** Görev 15:11'de dal değişimi yüzünden öldü, beş saat boyunca çıkış kodu 127 verdi ve hiç kimse fark etmedi; beş derin tarama örneği kayboldu. ADR-0008 hem kök nedeni (otomasyonun geliştirme ağacına çakılı olması) hem bildirim eksikliğini kapatıyor.

### Kurulum sırasında bulunan hata

`durum` komutu ilk hâlinde `launchctl list | grep -q "$ETIKET"` kullanıyordu ve **yüklü bir görev için "yüklü değil" diyordu.** Sebep: `grep -q` ilk eşleşmede çıkıyor, `launchctl list` SIGPIPE alıyor, `set -o pipefail` yüzünden boru başarısız sayılıyor.

Bu tam olarak `cron`'un reddedilme gerekçesindeki sessiz başarısızlık sınıfı — kabuk betiklerinde `pipefail` + erken çıkan tüketici birleşimi her yerde aynı tuzağı üretiyor. Çıktı artık değişkene alınıyor, boru yok.
