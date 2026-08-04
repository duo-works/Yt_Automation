# 0006 — Konu sınıflandırmasının son katmanı LLM'dir

- **Durum:** Kabul
- **Tarih:** 2026-07-29
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-30

## Bağlam

Hat, Wikipedia'da yükselen makalelerden tarih ve bilim adaylarını süzüyor. Sınıflandırma iki ücretsiz kademeyle başlıyor (ADR yok, DW-34): Wikidata `P31` tipleri, sonra kişiler için meslek ve ölüm tarihi. Bu, 600 makalelik günlük listeyi **50 belirsize** indiriyor.

Kalan 50 ücretsiz araçlarla kapanmıyor — canlı koşumda kanıtlandı:

| Makale | Wikidata sonucu | Gerçek | Sebep |
|---|---|---|---|
| Paul Newman | **tarih** ❌ | oyuncu | İspanyolca kaydında `Q189290` (subay) var — askerlik yapmış |
| Frida Kahlo | belirsiz | ressam → kültür | ölmüş, mesleği tarih listesinde değil |
| Graeme Garden | **bilim** ❌ | komedyen | tıp okuduğu için `Q39631` (hekim) taşıyor |

Meslek listesi bir ayar düğmesi ve iki yönü de kötü: genişletirsek yanlış pozitif artıyor (Graeme Garden), daraltırsak belirsiz kuyruğu büyüyor (Frida Kahlo). Ortada doğru bir eşik yok, çünkü sorun eşikte değil — **Wikidata tipleri konunun ne hakkında olduğunu değil, öznenin ne olduğunu söylüyor.**

Bu, YouTube'un Tarih kategorisi olmamasıyla birleşince şu sonuca varıyor: hattın "tarih" yarısı kural tabanlı yöntemlerle kapatılamıyor.

## Değerlendirilen seçenekler

1. **Meslek ve tip listelerini genişletmek** — Bedava ve deterministik. Ama yukarıdaki tablo bunun bir ödünleşme olduğunu gösteriyor, çözüm değil. Her yeni dil ve her yeni kenar vaka listeye bakım borcu ekliyor.
2. **Anahtar kelime kuralları** (başlık ve özet üzerinde) — Dile bağlı; altı dil için altı liste demek. DW-34 aynı gerekçeyle kategori isimlerini reddetmişti.
3. **Yerel bir model** — Bağımlılık ve kurulum yükü büyük (model ağırlıkları, GPU), günde ~50 sınıflandırma için orantısız.
4. **Claude API** — Kuyruk küçük ve sabit, istem doğal dilde yazılıyor, kenar vakalar liste bakımı yerine yönerge cümlesiyle çözülüyor.

## Karar

**Seçenek 4.** `trend/siniflandirici.py` yalnızca `sinif = 'belirsiz'` kuyruğunu LLM'e sorar.

Kararın parçası olan dört detay:

**Yalnızca kuyruk sorulur, tüm liste değil.** Ücretsiz kademeler %92'yi çözüyor; LLM'i baştan çalıştırmak on iki kat maliyet ve aynı sonuç demek. Kademelerin sırası maliyet sırasıdır.

**Kalıcı önbellek zorunlu, isteğe bağlı değil.** Karar bir kez verilir ve `sinif_kaynagi = 'llm'` ile yazılır; sonraki toplamalar onu ezmez (`konu_toplayici._sinifi_yaz`). Aynı makale her gün listede görünse de tek çağrı. Bu, hem maliyeti hem **determinizm kaybını** sınırlıyor — aynı makale iki kez sorulmadığı için iki farklı cevap alma ihtimali de yok.

**İsteme Wikipedia giriş paragrafı eklenir.** Başlık tek başına yetmiyor: "Homer" antik Yunan şairi de olabilir Simpson da. Özet API'si ücretsiz ve ayrımı tek cümlede veriyor.

**Model bir sabit, `siniflandirici.MODEL`.** Bugün `claude-opus-5`. Maliyet/doğruluk dengesini değiştirmek isteyen tek satır değiştirir; kod başka hiçbir yerde model varsaymıyor.

## Sonuçlar

**Kolaylaştırdıkları:** Hattın tarih yarısı çalışır hale geldi. Kenar vakalar artık kod değil **yönerge** düzeltmesiyle çözülüyor — Frida Kahlo, Richard Wagner ve Paul Newman istemde adıyla geçiyor ve testler bunu koruyor.

**Zorlaştırdıkları ve kabul edilen kısıtlar:**

- **Beşinci çalışma zamanı bağımlılığı.** ADR-0004 dört bağımlılıkla başlamıştı (+`tzdata`, yalnızca Windows). `anthropic` beşinci. İçe aktarım fonksiyon içinde: yalnızca `konu siniflandir` çalıştırıldığında yükleniyor, diğer komutlar etkilenmiyor.
- **Yeni bir sır.** `ANTHROPIC_API_KEY`, `.env`'de, `.env.example`'da değersiz (CLAUDE.md kural 6). YouTube kotasından tamamen ayrı bir bütçe — biri bittiğinde diğeri çalışmaya devam eder.
- **Determinizm düştü.** Aynı makale ilkesel olarak farklı koşuda farklı sınıflanabilir. Önbellek bunu pratikte ortadan kaldırıyor ama garanti etmiyor: veritabanı silinirse sonuçlar birebir aynı olmayabilir. Kabul edildi, çünkü alternatif (kural listeleri) yanlış cevabı **tutarlı** vermek.
- **Sınıflandırma doğruluğu ölçülmedi.** Kabul ölçütü 30 makalelik elle etiketlenmiş kümede ≥%85; API anahtarı gelene kadar bu ölçüm yapılamadı. Ölçülmeden görev kapanmıyor.
- **Model kararı gizli kalıyor.** Yalnızca sınıf yazılıyor; `gerekce` alanı isteniyor ama saklanmıyor. Yanlış sınıflandırmaların ayıklanması gerekirse gerekçeyi de saklamak gerekecek.
