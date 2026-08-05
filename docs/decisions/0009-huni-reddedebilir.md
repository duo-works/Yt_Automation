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

### İlk canlı ölçüm — 2026-08-04, 114 sondajlanmış aday

Otomasyon DW-58 ucuna taşındıktan (ADR-0008, `tazele`) sonraki ilk koşum. 20
yeni sondajın hepsi kırılımlı geldi ve en+es'in format tabanı tek koşumda doldu
(en 13, es 8 aday — `ASGARI_TABAN_ORNEK`'in iki katı).

| Kapı | Geçen |
|---|---|
| birleşik (DW-58 öncesi) | 4 / 114 |
| **format başına (DW-58 sonrası)** | **5 / 114** |
| yalnız format kapısıyla geçen | **1** |
| yalnız birleşik kapıyla geçen | 0 |

Asıl bulgu sayının kendisi değil, **yönü**. Format kalibresi üretilebilen üç
adayın üçünde de öneri Shorts ve uzun kalibresi eşiğin altında:

| Aday | birleşik | shorts | uzun |
|---|---|---|---|
| Fritz Gerlich (es) | 2,22 | **3,06** | 1,95 |
| Ernst Hanfstaengl (es) | 2,09 | **2,58** | 1,47 |
| Fritz Gerlich (en) | 1,50 | **2,26** | 1,50 |

Üçünün de uzun rafı doymuş, Shorts rafı boş. Birleşik kapı bu ikisini tek
potada eritince Fritz Gerlich'in İngilizce ölçümü 1,50 ile eşiğin altında kalıp
**eleniyordu** — yukarıdaki gerekçenin ta kendisi, artık varsayım değil ölçüm.
Diğer ikisi geçiyordu ama hangi formatla girileceği bilgisi yoktu.

#### Aynı koşumda bulunan kusur: sıfır gözlem ≠ boş raf

İlk ölçüm turunda kazanan aday `Lise Lesèvre` (en) görünüyordu: birleşik 1,09,
Shorts kalibresi 3,30. İncelenince sebebi çıktı — o sondajda **hiç Shorts
gözlemi yoktu** (50 sonuçtan yalnızca 2'si alakalı, 0'ı Shorts).
`bicim_skorla` arz terimlerini gözlemden kuruyor; gözlem yoksa arz sıfır
çıkıyor ve konu sahte bir zirveye oturuyor.

Bu, `ArzOlcumu.gecerli`'nin birleşik ölçüm için zaten yazdığı ilkenin format
seviyesinde uygulanmamış hâliydi: *"hiç sonuç dönmedi" ≠ "hiçbiri alakalı
değil"; ikisini karıştırmak bize var olmayan bir fırsat gösterir.* Etki
sistematik ve yön olarak en kötüsü: arama ne kadar cılızsa bir formatın gözlemi
o kadar sıfıra yakın, skoru o kadar yüksek — yani huni, YouTube'un zar zor
indekslediği konuları tercihen zirveye taşıyordu.

`ASGARI_FORMAT_GOZLEM` ile kapatıldı. Düzeltmenin ikinci ve daha önemli etkisi
tekil adayda değil **taban çizgisinde**: sahte ölçüm `en × shorts` tabanını da
kirletiyordu; çıkarılınca o dildeki diğer adayların kalibresi düzeldi ve
gerçek bir aday (Fritz Gerlich en) eşiği geçti. Yukarıdaki tablo düzeltme
sonrasıdır.

Kabul edilen kısıt netleşti: DW-53 sondajı en+es'e daralttığı için hedef dışı
dillerdeki eski adaylar (bugün 2 `tr` aday) format kalibresi **hiç**
üretemeyecek ve birleşik skora düşmeye devam edecek. Onlar için format önerisi
boş kalıyor — yanlış öneri üretmektense boş bırakmak doğru, ama Notion'da
"önerisiz aday" diye bir sınıf oluşuyor.

Örneklem küçük (21 kalibre edilebilir aday, tek koşum) ve bu bir **geri çağırma**
ölçümü, değer ölçümü değil: Fritz Gerlich'in iyi bir video olup olmadığını
bilmiyoruz, yalnızca huninin onu insan bakmadan atmayı bıraktığını biliyoruz.

#### Aynı gün, 81 kalibre edilebilir aday — yukarıdaki sayılar oynadı

Eski ölçümler yeniden sondalanıp (`bosluk tazele`) örneklem 21'den 81'e
çıkınca tablo değişti:

| | 21 aday | 81 aday |
|---|---|---|
| yalnız format kapısıyla geçen | 1 | **2** |
| yalnız birleşik kapıyla geçen | 0 | **1** |

**İki ders var ve ikincisi daha önemli.**

Birincisi: kapı tek yönlü değil. `es Fritz Gerlich` birleşik 2,03 ile eşiği
geçiyordu ama iki rafın **hiçbirinde** yeterli değil (shorts 1,81, uzun 1,58) —
harmanlanmış ortalama onu kayırıyormuş. Format kapısı bunu doğru şekilde
eliyor. "Daha çok aday geçirir" değil, "iki yönde de daha keskin ölçer".

İkincisi: **ince taban çizgisi kalibreyi oynatıyor.** Aynı `es Fritz Gerlich`
8 adaylık es tabanında shorts 3,06 iken, taban 17 adaya çıkınca 1,81'e düştü.
Yani yukarıdaki üç satırlık kanıt tablosu ince bir tabandan okunmuştu.
`ASGARI_TABAN_ORNEK = 5` istatistiksel güven için değil, **hiç yoktan iyi**
olduğu için seçilmişti; bu ölçüm o eşiğin gerçekte ne kadar gevşek olduğunu
gösteriyor. Eşiğin yükseltilmesi ayrı bir karar ve daha çok veri istiyor —
ama bugünden bilinen şu: **5 örneklemli bir tabandan okunan kalibre
raporlanabilir bir sayı değil, geçici bir tahmindir.**

Ölçüm hâlâ tamamlanmadı: 114 adayın 33'ü kırılımsız (günlük sondaj tavanı).
Tamamlandığında bu bölüm son kez güncellenecek.

#### Tam ölçüm — 2026-08-05, 114/114 aday · **kazanç sıfır**

Geri doldurma bitti; altı dilin hepsinde iki formatın taban çizgisi dolu
(en 18/19, es 22/22, de 26/27, tr 20/21, ar 17/17, hi 8/8 — shorts/uzun).

| Örneklem | birleşik geçen | format geçen | kazanılan | elenen |
|---|---|---|---|---|
| 21 kalibre edilebilir | 4 | 5 | 1 | 0 |
| 81 kalibre edilebilir | 4 | 5 | 2 | 1 |
| **114 (tam)** | **2** | **2** | **0** | **0** |

**Tam veride format kapısı ile birleşik kapı aynı iki adayı seçiyor.** Bu
ADR'nin yukarıda yayımladığı ara sayılar (+1, sonra +2/−1) ince taban
çizgisinden doğan **artefakt**tı. Bölüm kendi uyarısını taşıyordu —
*"5 örneklemli bir tabandan okunan kalibre raporlanabilir bir sayı değil"* —
ama sayı yine de sonuç olarak sunuldu. Tam veri o uyarıyı beklenenden sert
doğruladı ve uyarı artık bu ADR'nin kendi geçmişiyle kanıtlı.

**Bu, DW-58'i geçersiz kılmıyor — ölçtüğü şeyi düzeltiyor.** Kapı aynı adayları
seçiyor ama artık **hangi rafta** yapılacaklarını söylüyor:

| Aday | shorts | uzun | öneri |
|---|---|---|---|
| III. Murad (tr) | 1,17 | **2,47** | uzun |
| Fritz Gerlich (es) | **2,08** | 1,88 | shorts |

İki kanal ayrımının (uzun + Shorts) girdisi tam olarak bu ve DW-58 öncesinde
**hiç yoktu**. Havuzun tamamında dağılım 66 uzun / 31 shorts; yani kapı bir
formata yatmıyor. 21 adaylık örneklemde kurulan "geçenlerin üçü de Shorts"
yönsel iddiası da böylece düşüyor.

**Kalıcı ders — ölçüm bölümü olan ADR'ler için:** ara ölçüm yayımlamak, o
ölçümün istikrarlı olduğunu iddia etmektir. Bu bölümde üç kez sayı yayımlandı
ve ilk ikisi yanlıştı. Örneklem doymadan çıkan sayı kayıt altına alınacaksa
**yanında hangi örneklemden geldiği ve neyle değişebileceği** yazılmalı;
yoksa okuyan onu karar sanır.
