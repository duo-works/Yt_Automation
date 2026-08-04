# 0003 — Koordinasyon kanalının canlılığı kanarya kaydıyla doğrulanır

- **Durum:** Kabul
- **Tarih:** 2026-07-27
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-27

## Bağlam

ADR-0002 koordinasyonu Notion `📓 Oturum Kaydı` üzerine kurdu. Protokolün oturum başındaki adımı şu sorguyu çalıştırır:

```sql
SELECT ... FROM "collection://280e2fd0-..." WHERE "Durum" = 'Devam ediyor'
```

Ajan bu sorgudan boş sonuç alırsa **"kimse çalışmıyor, güvenle başlayabilirim"** diye yorumlar. Yani protokolün tüm güvencesi bir **olumsuz iddiaya** dayanıyor.

Olumsuz iddia, kanal bozukken tehlikelidir. Dört ayrı arıza aynı çıktıyı üretir:

| Arıza | Ajanın gördüğü | Tehlike |
|---|---|---|
| SQL kotası doldu | **hata mesajı** | düşük — gürültülü, fark edilir |
| Yanlış data source ID | boş sonuç | **yüksek** |
| Paylaşım/erişim eksik | boş sonuç | **yüksek** |
| Filtre veya sorgu hatası | boş sonuç | **yüksek** |
| Gerçekten kimse yok | boş sonuç | — |

Son dördü **birbirinden ayırt edilemiyor.** ADR-0002 yalnızca ilk satırı ele almıştı (`AGENTS.md`: *"kota hatasını 'aktif kayıt yok' diye yorumlama"*). Sessizce boş dönen üç durum için hiçbir savunma yoktu.

Bu teorik bir risk değil: kurulumu eksik bir ajan boş sonuç görür, "kimse çalışmıyor" der ve tam da protokolün engellemek için var olduğu şeyi yapar — başkasının dosyasına girer. Üstelik bunu **kural ihlali yapmadan**, protokolü doğru uygulayarak yapar.

## Değerlendirilen seçenekler

1. **Hiçbir şey yapmama** — Boş sonuca güvenmeye devam. Bedeli: protokol en çok ihtiyaç duyulduğu anda (karşı taraf yeni kurulum yaptığında) sessizce çalışmıyor.
2. **Write-then-read** — Ajan önce kendi kaydını yazar, sonra geri okur; kendi kaydını göremezse kanal bozuktur. Kendi kanaryasını üretir, ek kayıt gerektirmez. Ancak protokol sırasını tersine çevirir: çakışma kontrolünden **önce** yazmış olursun, yani yapmayacağın işi ilan edersin ve çakışma çıkarsa kaydı geri almak gerekir.
3. **Ayrı bir sağlık kontrolü çağrısı** — Bağımsız bir "kanal çalışıyor mu" sorgusu. Net ama her oturumda ikinci bir sorgu demek; SQL aracı ücretsiz planda saatlik kotalı, bu kotayı ikiye katlar.
4. **Kalıcı kanarya kaydı** — `Durum = "Devam ediyor"`, `Tür = "Kanarya"` olan, hiç kapatılmayan tek bir satır. Çakışma sorgusunun **kendi sonucunda** gelir; ek çağrı yok, ek kota yok.

## Karar

**Seçenek 4.** `📓 Oturum Kaydı`'nda kalıcı bir kanarya kaydı tutulur:

| Alan | Değer |
|---|---|
| `Kayıt` | `🚦 KANARYA — BU KAYIT SİLİNMEZ, KAPATILMAZ` |
| `Durum` | `Devam ediyor` — sorguda görünmesinin tek sebebi |
| `Tür` | `Kanarya` (bu karar için eklenen yeni seçenek) |
| `Kişi`, `Görev`, `Branch` | boş |

Protokol şuna dönüşür: sorgu sonucunda kanarya **yoksa** kanal doğrulanamamıştır → ajan durur ve kullanıcıya söyler. Kullanıcı tek başına çalıştığını teyit ederse devam edilebilir — bu, `AGENTS.md`'nin kota arızasında izlediği kalıbın aynısı.

Ayırt etme `Tür` alanı üzerinden yapılır, başlık metni üzerinden değil: başlık yazım hatasıyla bozulabilir, select alanı bozulamaz.

Kapsam bilinçli olarak yalnızca `📓 Oturum Kaydı`. `📋 Görevler`'i eksik okumak iş kaybettirmez; güvenlik-kritik olan tek tablo budur.

## Sonuçlar

**Kolaylaştırdıkları:** *"Hiçbir şey görmedim"* ifadesi *"kanaryayı gördüm, başka bir şey yoktu"* ifadesine dönüştü. İkincisi **doğrulanabilir olumlu bir iddia.** Ayrıca kurulum doğrulaması güçlendi: yeni bir ajanın erişimi eksikse ilk sorguda yakalanır, aylar sonra bir çakışmayla değil.

Maliyet sıfır: kanarya aynı sorgunun sonucunda geliyor, `Tür` kolonu `SELECT` listesine eklendi.

**Güvenli tarafa düşüyor:** kanarya kaybolursa ajanlar durur. Yanlış yönde başarısız olmuyor.

**Zorlaştırdıkları ve kabul edilen kısıtlar:**

- **`Dokunulan alanlar` beyanının doğruluğunu kanıtlamaz.** Kanarya kanalın çalıştığını gösterir, karşı tarafın kapsamını dürüst beyan ettiğini değil. Dar beyan eden bir ajan hâlâ görünmez.
- **Sayfalama.** Kanarya birinci sayfada, gerçek çakışma ikinci sayfada olabilir. Bugünkü kayıt sayısında sorun değil; sonsuza kadar geçerli bir varsayım değil.
- **Protokolü hiç uygulamayan ajanı yakalamaz.** Kanarya, sorguyu çalıştıranlar için bir doğrulamadır. Sorguyu atlayan ajan için DW-17'nin git hook'ları kısmi bir ağ kurar.
- **Kullanıcı "devam et" derse risk devredilir.** Bu bilinçli: sessiz bir başarısızlık yerine açık bir karar. Kararı verenin bunu bilerek verdiği varsayılır.
- **Kanaryanın kendisi bakım gerektirir.** Yanlışlıkla `Tamamlandı` yapılırsa tüm ajanlar durur. `AGENTS.md`'nin "kendi açmadığın kaydı kapatma" kuralı bunu koruyor ama kaydın başlığı da uyarıyı taşıyor.
- **DW-19 ile etkileşim.** `/dokuman-denetle`'nin hijyen kontrolü "bugüne ait olmayan açık oturum kaydı" arayacak; kanarya sonsuza kadar açık olduğu için yanlış pozitif üretir. `Tür = "Kanarya"` dışlaması o görevin tanımına eklendi.
