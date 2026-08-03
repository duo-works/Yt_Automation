# 0009 — Huni reddedebilir: boşluk skoru dile göre kalibre edilir

- **Durum:** Kabul
- **Tarih:** 2026-08-03
- **Karar verenler:** Mirza
- **İlgili görev:** DW-51

## Bağlam

Günlük huni 30 Temmuz'dan beri insansız koşuyor (ADR-0008) ve `trend aktar`
her koşumda skora göre sıralanmış **ilk N adayı** Notion'a yazıyor. Eşik yok;
yani liste ne kadar kötü olursa olsun her gün bir şey düşüyor.

PRD'nin faz 2 için pazarlık dışı saydığı dört karşı önlemden dördüncüsü bunu
doğrudan yasaklıyor: *"Reddedebilen bir hat — üretilen her çıktıyı koşulsuz
yayınlayan sistem slop üretir. O gün hiçbir şey yayınlamayan bir otomasyon, her
gün vasat bir şey yayınlayandan değerlidir."* Bu, YouTube'un 16 Temmuz 2026'da
güncellediği "inauthentic content" 1. kategorisine karşı bir mimari kısıt,
sonradan takılacak bir filtre değil.

DW-47 eşiği bilerek kapsam dışı bıraktı: o gün elde **3** ölçüm vardı ve
üçü de negatifti; bir eşik uydurmak veriden değil histen olurdu. Bugün **73**
ölçüm var.

### Ölçüm — 2026-08-03, 73 sondajlanmış aday

Ham skor: min −6,53 · medyan −3,98 · maks +0,59. Yalnızca 3'ü pozitif.

Tek bir küresel eşik **dil seçiyor, aday değil**:

| Eşik | Geçen | Dil dağılımı |
|---|---|---|
| 0,0 | 3 / 73 | **de 3** — başka dil yok |
| −1,0 | 5 / 73 | de 4, tr 1 |
| −2,0 | 10 / 73 | de 5, es 2, tr 1, en 1, hi 1 |

Sebep, skorun mutlak seviyesinin fırsatı değil **pazar büyüklüğünü** kodlaması:

| Dil | n | Skor medyanı | Talep medyanı | Arz medyan izlenme |
|---|---|---|---|---|
| tr | 20 | −3,97 | 1.031 | 55.512 |
| ar | 17 | −4,44 | 719 | 200.669 |
| de | 15 | −3,17 | 4.775 | 58.040 |
| es | 9 | −3,28 | 2.598 | 19.382 |
| hi | 8 | −4,71 | 292 | 201.856 |
| en | 4 | −3,95 | 24.484 | 1.296.193 |

İngilizce arz medyanı Almanca'nın 22 katı; Hintçe talep medyanı Almanca'nın
1/16'sı. `skorla()`'nın kendi docstring'i bunu zaten yazmıştı: *"talep tarafına
bir ölçek katsayısı gerekiyor ve o katsayı veriyle kalibre edilmeli."*

## Değerlendirilen seçenekler

1. **Tek küresel eşik.** En basit, tek sabit. Ama yukarıdaki tabloya göre
   huniyi fiilen "Almanca hunisi"ne çevirir — Türkçe birincil hedef dil olduğu
   hâlde (`bosluk.py`, `nis.py`) tr adaylarının hiçbiri geçmez.
2. **Ağırlıkları yeniden ayarlamak.** `IZLENME_AGIRLIGI` vb. oynatılarak
   dağılım sıfır etrafına çekilebilir. Ama sorun ağırlıkların yanlış olması
   değil, **iki farklı ölçeğin** (Wikipedia günlük okunması ↔ YouTube ömür boyu
   izlenmesi) karşılaştırılması. Ağırlık oynatmak bunu bir dil için düzeltip
   diğerleri için bozar.
3. **Dil başına ayrı sabit eşik.** Doğru yöne bakıyor ama altı sabit demek ve
   yeni bir dil eklendiğinde elle bakım gerektirir.
4. **Dile göre normalize skor + mutlak talep tabanı.** Seçilen.

## Karar

Kapı **iki katmanlı**:

1. **Göreli — `kalibre = (skor − dil_medyanı) / dil_MAD ≥ 2,0`.** Aday kendi
   pazarının olağanıyla kıyaslanıyor, küresel bir sabitle değil. Medyan + MAD
   tercihi `nis._taban`'ın gerekçesiyle aynı: tek uç değer ortalamayı sürükler,
   aradığımız şey ise tam olarak "bu dilde olağandışı olan". Bir dilin örneklemi
   `ASGARI_TABAN_ORNEK`'ten azsa taban güvenilmez sayılıyor ve o dil
   sıralanmıyor — yine `nis.py` idiyomu: *"Yanlış taban, yanlış zirve demek."*

2. **Mutlak — `talep ≥ 1.000 okunma/gün`.** Göreli kapı tek başına yetmiyor ve
   sebebi yapısal: her dilin en iyisi tanım gereği kendi medyanının üstünde,
   yani salt göreli bir kapı **hiçbir günü boş geçiremez** — çözmesi istenen
   sorunun ta kendisi. Ölçümde göreli kapıyı geçen üç aday mutlak olarak
   kötüydü: günde 328, 419 ve 596 okunma, üçü de 50/50 alakalı (YouTube'un
   döndürdüğü her sonuç konu üzerinde, yani boşluk yok). Bu ikinci eşik skor
   değil **yorumlanabilir birim**: günde 1.000 kişinin okumadığı bir konu için
   video yapılmaz, dilinin tabanı ne olursa olsun.

Birlikte, aynı 73 aday üzerinde:

| Kapı | Geçen | Dil dağılımı |
|---|---|---|
| bugün (kapı yok) | **73 / 73** | hepsi |
| yalnızca göreli | 12 / 69 | de 5, tr 2, es 2, hi 2, ar 1 |
| **göreli + mutlak** | **9 / 73** | de 5, tr 2, es 2 |

## Sonuçlar

**Kolaylaşan:** Huni artık boş gün geçirebiliyor ve bu bir hata değil —
`trend aktar` 0 ile dönüyor, `gunluk-huni.sh` metni "boş gün" sayıyor (DW-47
sözleşmesi korundu). Diller arası kıyas anlamlı hâle geldi: küçük pazarın iyi
adayı, büyük pazarın vasatına artık yenilmiyor.

**Zorlaşan / kabul edilen kısıtlar:**

- **Eşikler sonuçla kalibre edilmedi ve bugün edilemez.** Henüz tek video
  yayınlanmadı, yani "bu aday tuttu mu" diye sorulabilecek bir gerçek yok. 2,0
  MAD ve 1.000 okunma **gözlenen dağılımdan** seçildi. `bosluk.py`'deki
  ağırlıklar gibi bunlar da değişmesi beklenen yerler ve ilk yayın sonuçları
  geldiğinde revize edilmeli. Bu ADR o revizyonla değiştirilecek.
- **Taban örneklemle birlikte kayıyor.** Ölçüm biriktikçe bir dilin medyanı ve
  MAD'i değişir, yani dün geçen bir aday bugün geçmeyebilir. Bilinçli: taban
  "bu pazarda olağan olan" demek ve o gerçekten değişiyor. Skor zaten diske
  yazılmıyor (`bosluk.py`), kalibre değer de yazılmıyor.
- **Yeni bir dil ilk 5 ölçümünde hiç aday veremez.** Sessiz değil: eleme sayısı
  ve gerekçesi CLI'da basılıyor.
- **Eleme raporlanmazsa eşik revize edilemez.** Bu yüzden `trend aktar` hem dolu
  hem boş günde kaç adayın hangi kapıdan düştüğünü yazıyor.

**Kapsam dışı — huninin hangi dillerde aday arayacağı.** Sondaj bütçesinin
%34'ü (73 adayın 25'i) `ar` + `hi` dillerine gidiyor ve iki dil de yapısal
olarak kazanamıyor. Bu bir eşik sorusu değil kapsam sorusu: "Almanca'da yükselen
konu Türkçe yapılmaya değer mi?" cevabına bağlı. Ayrı karar.
→ **Kapandı: DW-53.** Sondaj hedef pazarlara (en+es) çevrildi, radar korundu,
başka dilde yükselen konu QID köprüsüyle hedef pazarda ölçülüyor.

## Güncelleme — kalibre kapısı format başına çalışıyor (DW-58, 2026-08-03)

Yukarıdaki göreli kapı **birleşik** arz üzerinden kuruluydu; DW-52 arzı Shorts
ve uzun olarak ayırınca bu bir kaçırma kaynağına dönüştü: uzun tarafı doymuş
ama Shorts tarafı bomboş bir konu, iki raf tek potada eritildiği için "orta
arz" görünüp eleniyordu. Yanlış atama değil — konu öneri aşamasına bile
varamıyordu.

Kapı artık format başına ölçüyor ve **en az bir format** eşiği geçiyorsa aday
geçiyor. Kritik ayrıntı: her formatın taban çizgisi **ayrı** tutuluyor. Sebebi
bu ADR'nin kendi gerekçesinin tekrarı — Shorts sistematik olarak uzun videodan
çok daha fazla izlenme alıyor, yani iki format aynı potaya konsaydı Shorts
tarafı topluca "kötü" görünür ve kapı neredeyse hep uzunu seçerdi. Dil
yanlılığı için verilen kararın birebir aynısı, bir eksen aşağıda.

Kabul edilen yeni kısıt: örneklem artık **dil × format** olarak bölünüyor, yani
`ASGARI_TABAN_ORNEK` daha geç doluyor. Dolmadığı sürece format kalibresi
üretilmiyor ve karar birleşik skora düşüyor — kaba ama doğru; yetersiz
örneklemden format skoru uydurmak yanlış olurdu.

Talep kapısı (`ASGARI_TALEP`) **formata bölünmedi** ve bölünemez: Wikipedia
okunması konu seviyesinde, "kaçı 60 saniyelik ister" bilgisini taşımıyor.
