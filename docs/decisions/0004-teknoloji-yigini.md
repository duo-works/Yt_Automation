# 0004 — Teknoloji yığını: Python 3.13, resmi Google istemcileri, dosya tabanlı durum

- **Durum:** Kabul
- **Tarih:** 2026-07-28
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-6

## Bağlam

v1'in yapacağı iş dar ve iyi tanımlı (PRD → *Kapsam*): hazır bir video dosyasını metadata'sıyla birlikte YouTube'a yükle, beyan bayraklarını doğru işaretle, thumbnail ayarla, yüklendiğini doğrula. Tetikleme elle; zamanlanmış çalışma ve AI ile video üretimi ikinci faz.

Kararı şekillendiren üç kısıt:

1. **Kota, projenin en sert duvarı.** Günlük 10.000 birim, tek `videos.insert` 1.600 birim, uçtan uca 1.651 → tavan günde 6 video. Kota **proje bazında**, kanal bazında değil; iki kanal aynı bütçeyi paylaşacak. Reddedilen istek de birim harcıyor, yani doğrulama yüklemeden **önce** yapılmalı.
2. **Beyan hataları pahalı.** `selfDeclaredMadeForKids` yanlış işaretlenirse FTC yaptırımı ihlal başına $53.088. Bu, "çalışıyor gibi görünen" koda tolerans bırakmıyor.
3. **İki kanal, tek hat.** Önce çocuk içeriği, sonra eğitim/tarih/bilim. Yükleme hattının kategoriden bağımsız kalması gerekiyor — ama ikinci kanal henüz yok, yani neyin gerçekten değiştiği bilinmiyor.

Ekip iki kişi ve dört ajan (her ikisinde Claude Code + Codex). Yığının okunabilir ve tahmin edilebilir olması, "güçlü" olmasından önemli.

## Değerlendirilen seçenekler

1. **Node.js / TypeScript** — `googleapis` paketi resmi ve olgun; tip güvenliği metadata doğrulamasında işe yarar. Ancak ikinci faz (AI ile video üretimi, ses sentezi, ffmpeg zincirleri) ağırlıklı olarak Python ekosisteminde yaşıyor; v1'i Node'da yazmak faz 2'de ya bir dil sınırı ya da tam bir yeniden yazım demek.
2. **Go** — Tek binary dağıtım, hızlı. Resmi YouTube istemcisi var ama örnekler ve topluluk çözümleri seyrek; medya/AI tarafında ekosistem yok. İki kişilik bir ekip için yanlış yerde harcanmış bütçe.
3. **Python 3.13 + resmi Google istemcileri** — YouTube Data API'nin en çok örneklenen dili; `google-api-python-client` yeniden başlatılabilir yüklemeyi (`MediaFileUpload(..., resumable=True)`) doğrudan veriyor, ki 1.600 birimlik bir yüklemenin ortada kopması durumunda tek koruma budur. Faz 2'nin araçlarıyla aynı ekosistem.
4. **Hazır otomasyon platformu** (n8n, Zapier vb.) — Hızlı başlangıç. Ama kota muhasebesi, beyan bayrağı doğrulaması ve "yüklemeden önce reddet" mantığı bu araçlarda ya yok ya da kırılgan; hata durumunda ne olduğunu göremiyorsun. Kısıt 1 ve 2 bunu eliyor.

## Karar

**Seçenek 3.** Python 3.13, `src/` düzeni, setuptools ile paketlenen `ytoto` adlı CLI.

Bağımlılıklar bilinçli olarak dört tane: `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `pyyaml`. Geliştirme tarafında `ruff` (lint + import sırası + biçim) ve `pytest`.

Onun dışında **standart kütüphane**. Somut olarak reddedilenler:

- **CLI için `click`/`typer` değil `argparse`** — iki alt komutluk bir arayüz için bağımlılık gerekmiyor.
- **Doğrulama için `pydantic` değil `dataclass`** — şemamız sabit ve küçük; hata mesajlarını kendimiz yazınca kullanıcıya ne söylediğimizi kontrol edebiliyoruz (`video.py` → `MetadataHatasi`).
- **Veritabanı yok.** Video başına bir `.yaml` metadata dosyası; kuyruk = dizin. Günde 6 videoluk bir tavanda veritabanının çözeceği bir problem yok, ekleyeceği kurulum yükü var.
- **Kanallar için soyutlama katmanı yok.** Kategoriye göre değişen her değer `kanal.py`'deki tek bir sözlükte (`KANALLAR`) toplanır. İkinci kanal geldiğinde oraya bir satır eklenir; gerçekten neyin değiştiği o zaman görülür ve soyutlama gerekiyorsa **o noktada** çıkarılır, tahminle değil.

Kota muhasebesi ayrı bir modülde (`kota.py`) ve harcama **istek gönderilmeden önce** düşülür — reddedilen istek de birim harcadığı için sonradan saymak gerçeği eksik gösterir. Sayacın kalıcılığı bilinçli olarak dışarıda bırakıldı (DW-24): v1 elle tetikleniyor, tek çalıştırma tek oturum.

## Sonuçlar

**Kolaylaştırdıkları:** Yeniden başlatılabilir yükleme hazır geliyor. Faz 2'nin AI araçları aynı dilde. Bağımlılık yüzeyi dört paket olduğu için `pip install` dışında kurulum ritüeli yok. Metadata dosyaları düz metin — git ile izlenebiliyor, ajanlar okuyup yazabiliyor.

**Zorlaştırdıkları ve kabul edilen kısıtlar:**

- **Tip güvenliği yok.** `dataclass` + `ruff` yazım hatalarını yakalar, tip hatalarını yakalamaz. Karşılığında metadata doğrulaması testlerle kapatıldı; bu testler PRD'nin kota tavanı sayısındaki bir hatayı zaten yakaladı (5 sanılıyordu, 6 çıktı).
- **Python 3.13 zorunlu.** `requires-python = ">=3.13"`. Ekip iki kişi ve ikisi de kurabiliyor, ama dağıtım hedefi seçilirken (DW-8) bu sürümün orada bulunduğu doğrulanmalı.
- **Kilit dosyası yok.** `pyproject.toml` alt sınır veriyor, sürümleri sabitlemiyor — iki makinede farklı sürümler kurulabilir. Ekip küçükken kabul edilebilir; CI kırılmaya başlarsa `uv.lock` eklenir (CI zaten `uv.lock` varsa `uv sync --frozen` kullanacak şekilde yazıldı).
- **Dosya tabanlı durum ölçeklenmiyor.** Kuyruk bir dizin olduğu için eşzamanlı iki çalıştırma aynı videoyu iki kez yükleyebilir. Günlük tek tetiklemede sorun değil; zamanlanmış çalışmaya geçildiğinde (faz 2) hem kota sayacı hem kuyruk durumu kalıcı hale getirilmeli — DW-24 bunun ilk parçası.
- **`ytoto dogrula` dışında henüz çalışan komut yok.** Yükleme, OAuth görevine (DW-21) bağlı. Yani bu ADR bir yığın seçimini kaydediyor, çalışan bir hattı değil.
