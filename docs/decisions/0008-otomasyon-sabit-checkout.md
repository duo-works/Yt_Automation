# 0008 — Zamanlanmış otomasyon geliştirme ağacından ayrılır

- **Durum:** Kabul
- **Tarih:** 2026-07-30
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-47
- **Değiştirdiği karar:** ADR-0007'nin "sessiz başarısızlık riski … bildirim eklemek bugünün ihtiyacı değil" maddesi

## Bağlam

ADR-0007 saatlik taramayı `launchd`'a bağladı ve görev 15:04'te kendiliğinden çalıştı. **Altı saat sonra ölmüştü ve kimse fark etmedi.**

Ölçüm:

| Kanıt | Değer |
|---|---|
| `launchctl list` son çıkış kodu | **127** |
| `veri/gunluk/launchd.hata.log` | 5 × `No such file or directory` |
| `veri/gunluk/tarama-2026-07-30.log` son satır | 15:05 |
| Kaybedilen derin tarama örneği | **5** (16:00–20:00) |

Sebep `git reflog`'da: 15:11'de geliştirme ağacı `feat/DW-32-bolge-zamanlama`'dan `main`'e geçti. `scripts/saatlik-tarama.sh` 16 daldan yalnızca ikisinde var — o dosyayı ekleyen commit (`4e66ec6`) henüz merge edilmemiş bir yığının içinde. Dal değişince dosya ortadan kayboldu, `launchd` her saat başı var olmayan bir betiği çağırmayı denedi.

Asıl kusur betiğin eksikliği değil: **zamanlanmış bir işin, altındaki dosyaları habersizce değiştiren bir dizine çakılı olması.** Geliştirme ağacı doğası gereği dal değiştirir; otomasyonun buna dayanması yanlış varsayım.

İkinci mesele aynı kökten: hata günlüğe yazıldı ama **kimseye ulaşmadı.** ADR-0007 bunu açık risk olarak listelemiş ve "bugünün ihtiyacı değil" demişti. Aynı gün içinde ihtiyaç oldu.

## Değerlendirilen seçenekler

1. **Olduğu gibi bırak, yığını merge et.** Doğru ama yeterli değil: merge sonrası `main` betikleri içerse bile geliştirme ağacı eski bir dala geçtiğinde aynı şey tekrar olur. Ayrıca merge DW-39/DW-40'a bağlı, ikisi de bekliyor.
2. **Betikleri sabit bir dizine kopyala.** Betik hayatta kalır ama `python -m yt_automation.cli` yine geliştirme ağacının paketini çağırır. `main`'de `src/yt_automation/trend/` hiç yok — 127 yerine `ModuleNotFoundError` alırdık. Sorunu taşımak, çözmek değil.
3. **Ayrı bir klon.** İşe yarar ama nesne deposunu ikinci kez indirir ve iki depo arasında ref senkronu elle iş olur.
4. **Ayrı bir git worktree, sabit ref'e iğneli.** Nesne deposu ortak, ref seçimi açık, geliştirme ağacından tamamen bağımsız.
5. **Bulut zamanlayıcı.** ADR-0007'de olduğu gibi doğru uzun vadeli cevap, DW-8'e bağlı, bugünkü ihtiyacın önüne geçiyor.

## Karar

**Zamanlanmış iş kendi worktree'sinden koşar** (seçenek 4), ve üç yol birbirinden ayrılır:

| Ne | Nerede | Neden orada |
|---|---|---|
| **Kod** | `${YT_OTOMASYON_CALISMA:-~/.yt-otomasyon/calisan}` — `--detach` ile sabit ref'e iğnelenmiş worktree | Geliştirme ağacı dal değiştirince etkilenmez |
| **Veri** | Geliştirme ağacının `veri/` dizini, `YT_OTOMASYON_VERI` ile | `.gitignore`'da olduğu için zaten dal değişiminden bağımsız; verinin tek yerde kalması için bilinçli olarak worktree'ye taşınmıyor |
| **Sırlar** | Geliştirme ağacının `.env`'i, `YT_OTOMASYON_ENV` ile | `.gitignore`'da; kopyalamak sırrı çoğaltmak olurdu |

`--detach` bilinçli: dal checkout edilseydi aynı dal iki worktree'de birden açık olamaz ve geliştirme ağacı o dala geçemezdi.

### Tazeleme bilinçli bir eylem

Yeni `scripts/zamanlama-kur.sh tazele [--ref <ref>]` worktree'yi başka bir ref'e taşır. Otomasyonun hangi kodu koştuğu artık **açıkça seçiliyor**; dal değiştirmenin yan etkisi değil. `durum` iğnelenen ref'i ve son commit başlığını basıyor.

### Sessiz ölüm üç katmanda kapatıldı

| Katman | Ne yakalıyor |
|---|---|
| **Önuçuş kontrolü** | venv yok, paket import edilemiyor, `YOUTUBE_API_KEY` boş, veri dizini yazılamıyor — çıplak `127` yerine adı konmuş hata |
| **Nöbet dosyası** (`veri/gunluk/.son-basarili`) | "Yüklü ama hiç koşmuyor" hâli. `durum` 2 saatten eskiyse ❌ veriyor ve **sıfırdan farklı çıkış kodu** döndürüyor, yani betikten kontrol edilebiliyor |
| **macOS bildirimi** | Herhangi bir adım düştüğünde ekrana çıkıyor. Günlüğe yazmak yetmedi; bunu 127 olayı kanıtladı |

### `.env` boş değeri plist'i ezemez

`.env.example` `YT_OTOMASYON_VERI=` satırını **boş** taşıyor. `set -a` ile kaynaklandığında bu boş değer `launchd`'ın verdiği gerçek yolu ezerdi ve depo, geliştirme ağacı yerine worktree'nin içine yazılırdı — iki ayrı veritabanı, hiçbir hata mesajı. `scripts/ortak.sh` ortamdan gelen dolu değerleri kaynaklamadan önce saklayıp sonra geri koyuyor.

## Sonuçları

**Kazanç:** Geliştirme ağacında dal değiştirmek otomasyonu artık etkilemiyor — DW-47'nin kabul ölçütü tam olarak bu senaryo. Otomasyonun koştuğu kod sürümü görünür ve seçilebilir hâle geldi.

**Kabul edilen kısıtlar:**

- **Worktree elle tazeleniyor.** Yeni kod otomatik gitmiyor; bu bilinçli, ama unutulursa otomasyon eski kodu koşmaya devam eder. `durum` iğnelenen ref'i bastığı için görülebiliyor.
- **İkinci bir sanal ortam.** Worktree kendi `.venv`'ini kuruyor (bir kerelik). Geliştirme ağacınınkini paylaşmak denenmedi: editable kurulum `__editable___*_finder` kancasıyla çalışıyor ve `PYTHONPATH`'i ezebiliyor — sessiz ve teşhisi zor bir yanlış-modül riski.
- **Yalnızca macOS.** ADR-0007'deki kısıt aynen duruyor.
- **Bildirim kanalı yerel.** `osascript` bildirimi yalnızca o makinede görünür. Uzaktan izleme DW-8'e bağlı.
