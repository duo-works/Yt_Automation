# AI Ajanı Konvansiyonları

Bu dosya Claude Code, Codex ve benzeri ajanların bu repo'da çalışırken uyması gereken kuralları içerir — **ajan kuralları için tek kaynak burasıdır.** `CLAUDE.md` bu dosyaya yönlendirir. İnsan kuralları için [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Bağlam

Bu repo `duo-works` organizasyonuna ait, iki kişilik bir ekip tarafından geliştiriliyor. **Her iki geliştirici de kendi AI ajanlarıyla aynı repo üzerinde çalışıyor.** Görev takibi **Notion**'da, kod review **GitHub PR**'da yapılır. GitHub Issues kapalıdır.

---

## İlk kez buradaysan — okuma sırası

Kullanıcı sana *"projeyi oku ve anlat"* gibi bir şey dediyse başlangıç noktası burasıdır. Projenin durumu **repo'da değil, Notion'da** yaşıyor; yalnızca dosyaları okuyarak eksik bir tablo çıkarırsın.

Sırayla:

| # | Nereye | Ne öğrenirsin |
|---|---|---|
| 1 | Bu dosyanın tamamı | Kurallar, oturum protokolü, komutlar |
| 2 | [`README.md`](README.md) | Proje ne yapıyor, hangi aşamada |
| 3 | Notion → [🎬 Yt_Automation PRD](https://app.notion.com/p/3a79bfc93b2e813087b6c35c78af0ee7) | Kapsam, ilk sürümde **olmayacaklar**, kota kısıtları, açık sorular |
| 4 | Notion → [📋 Görevler](https://app.notion.com/p/93190546ef3941c88ab1d2bd0d1fface) | Sıradaki iş, DW-ID'ler, kim neyi almış |
| 5 | Notion → [📓 Oturum Kaydı](https://app.notion.com/p/cb1df32162934baba379c8733813893f) → `🔴 Aktif` | Kim şu an neye dokunuyor |
| 6 | [`CONTRIBUTING.md`](CONTRIBUTING.md) | İnsan tarafı süreç |
| 7 | [`docs/decisions/`](docs/decisions/) | Neden böyle yapılmış |

Notion bağlantın yoksa 3, 4 ve 5'i okuyamazsın — bu durumda **eksik bilgiyle konuştuğunu açıkça söyle**, tahmin etme.

### Kullanıcıya ne anlatmalısın

Özetin şunları içermeli:

- **Proje ne yapıyor ve hangi aşamada** — kod var mı, yığın seçildi mi
- **Kapsamda olmayanlar** — kapsam kayması buradan önlenir, PRD'nin en önemli bölümü
- **Sıradaki iş ve neyin bloke ettiği**
- **Aktif oturum var mı**, çakışma riski taşıyor mu
- **Bilinen kısıtlar** — API kotası, politika riski
- **Neyin hâlâ belirsiz olduğu**

Son madde en kritiği: PRD'de cevaplanmamış açık sorular var. Bunları **karar verilmiş gibi sunma.** Kullanıcı yanlış varsayımla işe başlarsa hatanın kaynağı sensin. Neyin karar, neyin taslak, neyin açık soru olduğunu ayır.

---

## Oturum protokolü (zorunlu)

İki kişinin ajanları birbirinden habersiz çalışırsa aynı dosyaya girer, birbirinin işini tekrar eder veya çelişen kararlar alır. Bunun panzehiri Notion'daki **📓 Oturum Kaydı** database'idir: kim, hangi ajanla, hangi göreve, hangi dosyalara dokunuyor — hepsi orada.

🔗 https://app.notion.com/p/cb1df32162934baba379c8733813893f

### İLK oturum — bu repo'da ilk kez çalışıyorsan

Protokol Notion'a bağlı. Bağlantı yoksa protokol sessizce çalışmaz: "aktif kayıt yok" ile "kayıt açamayan bir ajan çalışıyor" aynı görünür. Bu yüzden ilk oturumda **önce dört doğrulama yap, sonuçlarını kullanıcıya raporla**:

1. **Notion MCP bağlantısı var mı?** `📓 Oturum Kaydı` data source'una bir sorgu at (aşağıdaki SQL). Hata alıyorsan bağlantı yok.
2. **Kullanıcı workspace üyesi mi?** Notion kullanıcı listesini çek; kullanıcının adı orada mı bak. Değilse `Kişi` alanı doldurulamaz.
3. **`📋 Görevler`'e erişim var mı?** DW-ID okuyabiliyor musun? Okuyamıyorsan branch adı kuralı uygulanamaz.
4. **`main` güncel mi?** `git switch main && git pull`.

Herhangi biri başarısızsa **çoklu-ajan işine başlama.** Kullanıcıya hangisinin eksik olduğunu söyle ve kurulum rehberine yönlendir: Notion → 📚 Bilgi Bankası → **Ajan Kurulumu**.

Doğrulama geçtiyse bunu bir kez `Tür = "Not"` kaydıyla Notion'a yaz — diğer kişi senin devrede olduğunu böyle görür.

### Oturum BAŞINDA — kod yazmadan önce

1. **Kimliğini belirle.** Notion hesabı ortak kullanılıyor — kimin çalıştığını *bilmiyor*. Kaynak git kimliğidir:

   ```bash
   git config user.name
   ```

   | Değer | `Kişi` |
   |---|---|
   | `Mirza Sarıbıyık` | `Mirza` |
   | `Ömer Faruk Güleç` · `ofgworks` | `Ömer` |

   Değer boşsa veya tabloda yoksa **kullanıcıya sor** — tahmin etme. Yanlış atfedilen bir kayıt sessizce yanlış kalır.

2. **Aktif kayıtları sorgula.** `📓 Oturum Kaydı` → `Durum = "Devam ediyor"` olan tüm satırlar.
3. **🚦 Kanaryayı doğrula.** Sonuçta `Tür = "Kanarya"` satırı **yoksa** kanal bozuktur: sorgu çalışmış gibi görünüp boş dönmüş olabilir. Kullanıcıya söyle ve **çoklu-ajan işine başlama.** Tek başına çalıştığını kullanıcı teyit ederse devam edilebilir.
4. **Çakışma kontrolü.** **Bu oturuma ait olmayan** her aktif kayıt kontrol edilir — `Dokunulan alanlar` senin gireceğin dosyalarla kesişiyorsa: **başlama.** Kullanıcıya çakışmayı bildir, ne yapılacağını sor. Kanaryayı bu karşılaştırmaya **katma** (`Tür = "Kanarya"`).

   ⚠️ Ölçüt "başkasına ait" **değil**, "bu oturuma ait değil". Her iki geliştirici de hem Claude Code hem Codex kullanıyor; aynı kişinin iki ajanı aynı anda çalışabilir. `Kişi` alanı seninkiyle aynı diye bir kaydı atlarsan, kendi diğer ajanınla çakışırsın — bu en olası çakışma senaryosu, çünkü ikisi çoğu zaman aynı makinede ve aynı çalışma dizinindedir.
5. **Son 7 günü oku.** Özellikle `Tür = "Devir"` olanları — yarım kalmış iş ve dikkat notları orada.
6. **Kendi kaydını aç.** `Durum = "Devam ediyor"`, `Kişi`, `Görev`, `Branch` ve `Dokunulan alanlar` dolu olacak. Başlık formatı `<tarih> · <kişi> · <ajan> · <DW-ID>` — ajan adı zorunlu, aynı kişinin iki kaydı ancak böyle ayırt edilir.

```sql
-- Aktif kayıtlar (çakışma kontrolü + kanarya doğrulaması)
SELECT "Kayıt", "Kişi", "Ajan", "Tür", "Branch", "Dokunulan alanlar"
FROM "collection://280e2fd0-a14a-4d2d-ac25-24585472348e"
WHERE "Durum" = 'Devam ediyor'
```

> 🚦 **Kanarya neden var.** Protokol olumsuz bir iddiaya dayanıyor: *"aktif kayıt yok, başlayabilirim."* Ama yanlış data source ID'si, eksik paylaşım ve bozuk filtre — üçü de **boş sonuç** döndürür ve "gerçekten kimse yok" ile ayırt edilemez. Kanarya her zaman orada olduğu için, onu görmek sonucun güvenilir olduğunu kanıtlar.

> ⚠️ **Bu SQL aracı ücretsiz planda saatlik kotalı.** Kota dolarsa sorgu hata döner — bunu "aktif kayıt yok" diye **yorumlama**, protokolün tüm güvencesi bu sorguda.
>
> Kota dolduğunda yedek yol: `📓 Oturum Kaydı` data source'una **arama** yap (`data_source_url` parametresiyle), dönen kayıtları tek tek `fetch` ile aç ve `Durum` alanına bak. Daha yavaş ama kotasız. İkisi de başarısızsa kullanıcıya söyle ve çoklu-ajan işine başlama.
>
> **Kota bütçesi:** SQL yalnızca bu çakışma sorgusu için harcanır. Raporlama, listeleme, ID kontrolü gibi işler `fetch`/`search` ile yapılır — onlar kotasız. Kolaylık işleriyle tüketilen kota, gerçekten gerektiği anda dolu olur.

### Oturum SIRASINDA — kapsam büyürse

Oturum başındaki çakışma kontrolü, o an bildiğin dosyalara göre yapılır. **Gerçek çakışmaların çoğu sonradan doğar:** işe `src/report/` için başlarsın, kırk dakika sonra ortak bir dosyayı değiştirmen gerektiğini fark edersin. O anda kaydın hâlâ eski kapsamı gösteriyordur ve karşı tarafın ajanı seni orada görmez.

Bu yüzden: **`Dokunulan alanlar`da yazmayan bir dosyaya ilk kez dokunmadan önce**

1. Kaydındaki `Dokunulan alanlar` alanını yeni dosya/dizinle güncelle
2. Çakışma sorgusunu **tekrarla** — oturum başındaki sonuç artık geçersiz
3. Yeni bir kesişme çıktıysa dur, kullanıcıya bildir, sorma

Özellikle şunlara dokunurken tetikle: paylaşılan config, tip tanımları, ortak istemci/yardımcı modüller, `package.json` benzeri manifest dosyaları, migration'lar. Bunlar iki görevin en sık kesiştiği yerlerdir.

Kapsam büyümesi normaldir; **bildirilmemesi** sorundur.

### Oturum SONUNDA

1. Kendi kaydını güncelle: `## Ne yapıldı` ve `## Sıradaki adım` bölümlerini doldur.
2. Durumu ayarla:
   - İş bitti → `Tamamlandı`
   - Yarım kaldı, devrediliyor → `Devredildi` **ve** `Tür = "Devir"`
   - Tıkandın → `Bloke`, nedeni `## Dikkat` altına
3. PR açıldıysa `GitHub PR` alanını doldur.

### Asla

- **Kendi açmadığın** hiçbir aktif kaydı değiştirme veya kapatma — aynı kişiye ait olsa bile. Onu senin kardeş ajanın açmış olabilir.
- Kaydı açmadan kod yazmaya başlama.
- Oturumu kaydı güncellemeden bitirme.

### Aynı kişinin iki ajanı aynı anda çalışıyorsa

Her iki geliştirici de hem Claude Code hem Codex kullanıyor. İki ajanın **aynı çalışma dizininde** paralel çalışması Notion protokolüyle çözülemez: ikisi de aynı dosyalara yazar, git indeksini paylaşır, birbirinin düzenlemesini üzerine yazar. Oturum kaydı bunu *raporlar* ama *engelleyemez*.

Kural: **iki ajan aynı anda çalışacaksa ayrı çalışma dizini kullanılır.**

```bash
# Aynı repo, ayrı çalışma dizini — git worktree
git worktree add ../Yt_Automation-codex feat/DW-42-bir-is
```

Her worktree kendi branch'inde olur ve `Dokunulan alanlar` alanına worktree yolunu da yaz. Ayrı dizin yoksa ikinci ajanı **başlatma**.

---

## Komutlar

Protokolün tekrarlayan adımları komut haline getirildi. Gövdeleri `docs/ajan/komutlar/` altında **tek kaynakta** durur; `.claude/commands/` altındakiler oraya yönlendiren ince sarmalayıcılardır.

| Komut | Ne yapar |
|---|---|
| `/oturum-basla` | Çakışma sorgusu (kota yedeğiyle) → son 7 günün devirleri → kendi kaydını aç |
| `/oturum-kapat` | Ne yapıldı + sıradaki adım + `Tamamlandı`, PR linkini işle |
| `/gorev DW-42` | Görevi üstlen → doğru formatta branch aç → oturum kaydını başlat |
| `/pr-ac` | PR aç, Notion'daki görev ve oturum kaydını senkronla |
| `/devir` | Yarım kalan işi devret: `Devredildi` + `Tür = Devir` |
| `/soguk-baslangic` | Projeyi sıfırdan öğren, **kaynaklı** özet üret — yeni ajan devreye girerken |
| `/denetle` | Bir soğuk başlangıç özetini kaynaklara karşı denetle (farklı oturumda) |

**Codex kullanıyorsan** — repo bazında slash komut desteği yok, aynı dosyalar kişisel prompt dizinine kopyalanır:

```bash
cp docs/ajan/komutlar/*.md ~/.codex/prompts/
```

Dosya adı komut adı olur (`oturum-basla.md` → `/oturum-basla`). Gövdeler bu yüzden araç-bağımsız dille yazılmıştır; MCP araç adı geçmez.

⚠️ Kanonik dosyalar değiştiğinde kopyayı tazelemek gerekir. Komut davranışı beklenmedik geliyorsa önce kopyanın güncel olduğunu kontrol et.

---

## Kesin kurallar

1. **`main`'e doğrudan commit veya push yapma.** Her zaman branch aç.
2. **Branch adı:** `<tür>/DW-<numara>-<kisa-aciklama>` — Notion görev ID'si zorunlu. Kullanıcı ID vermediyse sor, uydurma.
3. **Commit mesajı:** Conventional Commits, açıklama Türkçe, gövdede `Notion: DW-<numara>` satırı.
4. **PR başlığı:** `<tür>(<kapsam>): <açıklama> [DW-<numara>]` — CI bu formatı zorunlu tutar.
5. **Repo köküne plan/rapor/analiz dosyası yazma.** Uzun form dokümantasyon Notion'a gider. Repo'da izin verilen doküman: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `AGENTS.md`, `docs/` altı.
6. **Sır yazma.** `.env` dosyasına dokunma; yeni değişken gerekiyorsa `.env.example`'a değersiz olarak ekle.
7. **Kalıcı mimari karar alındığında** `docs/decisions/` altına ADR ekle (şablon: `docs/decisions/README.md`).
   > ⚙️ **2, 3 ve 4 CI tarafından zorunlu tutulur** (`.github/workflows/pr-kurallari.yml`). Branch adını, her commit mesajını ve PR gövdesindeki Notion bağını kontrol eder. Beşi de `pr-title-ok` kapısına bağlı; o kapı branch protection'ın beklediği tek check.
   >
   > Bu, hata yapmanı engellemez ama **sessizce** hata yapmanı engeller. Uymayan PR kırmızı olur ve merge edilemez.

8. **Notion'da yeni database veya üst seviye sayfa oluştururken parent'ı her zaman `duo-works` hub sayfası olsun** (`3a79bfc9-3b2e-8104-8f7d-df02d3de4a38`). Hub ağacının dışına açılan sayfalar dağınık kalır ve keşfedilemez; çalışma alanının tamamı tek ağaçta durur.

## Kod tarzı

- Çevredeki kodun stiline uy: isimlendirme, yorum yoğunluğu, dosya düzeni.
- Yeni bir bağımlılık eklemeden önce mevcut bağımlılıklarla çözülüp çözülmediğine bak.
- Kullanıcı istemediği sürece kapsamı genişletme; istenen işi eksiksiz yap.

## Commit ve push

- Kullanıcı açıkça istemedikçe commit veya push yapma.
- Commit yapılacaksa önce `git status` ve `git diff` ile ne değiştiğini doğrula.

---

## Notion referansı

| Database | Ne için | Data source |
|---|---|---|
| 📋 Görevler | Görev, durum, öncelik, DW-ID | `collection://887316e7-61e2-4fd6-815e-282afbbd9e54` |
| 📓 Oturum Kaydı | Oturum günlüğü, devir, aktif çalışma | `collection://280e2fd0-a14a-4d2d-ac25-24585472348e` |
| 🚀 Projeler | Proje kayıtları | `collection://41ef304c-212e-418f-b097-f2205ed4d5ff` |
| 📚 Bilgi Bankası | PRD, mimari, API notu | `collection://1f188db7-0bc4-4a4b-8e7e-08d10ebe86da` |
| 🧭 Kararlar | ADR aynası | `collection://bcb2b316-c088-440b-8f6c-56805f654f73` |
| 🗓 Sprintler | Sprint hedefleri | `collection://d57e2544-bb3b-4e8d-9f33-01ab3e1f042d` |
| 📝 Toplantı Notları | Toplantı kayıtları | `collection://fcad56c0-701c-444f-b29b-00d57899a88a` |

Notion MCP bağlantısı yoksa oturum protokolü uygulanamaz. Bu durumda kullanıcıyı **uyar** ve bağlantı kurulmadan çoklu-ajan işine başlama.
