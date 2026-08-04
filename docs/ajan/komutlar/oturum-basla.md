# /oturum-basla

`AGENTS.md` → "Oturum BAŞINDA" protokolünü uygula. Kod yazmadan önce çalıştırılır.

## 1. Kimliğini belirle

Notion hesabı ortak kullanılıyor — kimin çalıştığını **bilmiyor**. Kaynak git kimliğidir:

```bash
git config user.name
```

| Değer | `Kişi` |
|---|---|
| `Mirza Sarıbıyık` | `Mirza` |
| `Ömer Faruk Güleç` · `ofgworks` | `Ömer` |

**Aksansız yazımlar da geçerli.** `Omer Faruk Gulec` ile `Ömer Faruk Güleç` aynı kişidir; karşılaştırmayı aksana duyarlı yapma. Ölçüldü: Ömer'in makinesinde değer `Omer Faruk Gulec` olarak duruyordu ve aksana duyarlı bir kontrol bunu "tabloda yok" sayıyordu. Windows kurulumları bu değeri tekrar üretebiliyor, yani tabloya ASCII satırı eklemek kalıcı çözüm değil.

Boşsa veya tabloda yoksa **kullanıcıya sor** — tahmin etme. Yanlış atfedilen kayıt sessizce yanlış kalır.

> `scripts/ajan-kurulum.py` bu eşleştirmeyi aksana duyarsız yapıyor ve hangi `Kişi` değerine düştüğünü yazdırıyor; emin değilsen onu çalıştır.

## 2. Aktif kayıtları sorgula

Notion `📓 Oturum Kaydı` (`collection://280e2fd0-a14a-4d2d-ac25-24585472348e`):

```sql
SELECT "Kayıt", "Kişi", "Ajan", "Tür", "Branch", "Dokunulan alanlar"
FROM "collection://280e2fd0-a14a-4d2d-ac25-24585472348e"
WHERE "Durum" = 'Devam ediyor'
```

**Sorgu hata verirse durma noktası burasıdır.** Bu SQL aracı ücretsiz planda saatlik kotalı. Hatayı "aktif kayıt yok" diye yorumlama — protokolün tüm güvencesi bu sorguda.

> Kota bütçesi: SQL yalnızca bu sorgu için harcanır. Raporlama ve listeleme `fetch`/`search` ile yapılır — onlar kotasız.

### Yedek yol — MCP yoksa ya da kota dolduysa

```bash
python3 scripts/oturum-sorgula.py
```

MCP'ye hiç dokunmaz; `NOTION_TOKEN` ile doğrudan API'ye gider. Token `.env`'de zaten var (trend hattı Notion'a yazıyor), yani **ek kurulum istemez**. Ayrı bir çalışma dizininde (worktree) çalışıyorsan `.env` orada olmaz — betik ana çalışma dizinindekini bulur.

Çıkış kodu doğrudan ne yapacağını söyler:

| Kod | Anlamı | Ne yap |
|---|---|---|
| `0` | sorgu çalıştı, kanarya göründü | 4. adıma geç (3. adım karşılandı) |
| `2` | sorgu çalıştı, **kanarya yok** | kanal bozuk — kullanıcıya söyle, **başlama** |
| `1` | sorgu hiç çalışmadı | "kayıt yok" diye yorumlama — kullanıcıya söyle, **başlama** |

Bu yol **gerçekten gerekiyor**: yazıldığı gün Notion MCP `Needs authentication` durumundaydı ve MCP tarafı hiç sorgulanamıyordu. İkisi de başarısızsa kullanıcıya söyle ve **çoklu-ajan işine başlama**.

⚠️ `Durum` alanı Notion'da **select**, `status` değil. Elle API sorgusu yazarsan `{"select": {...}}` kullan; `status` filtresi `validation_error` döndürür.

## 3. 🚦 Kanaryayı doğrula

Sonuçta `Tür = "Kanarya"` satırı var mı?

- **Var** → sonuç güvenilir, devam et
- **Yok** → kanal bozuk. Sorgu çalışmış gibi görünüp boş dönmüş olabilir: yanlış data source ID'si, eksik paylaşım, bozuk filtre. Kullanıcıya söyle ve **çoklu-ajan işine başlama.** Tek başına çalıştığını kullanıcı teyit ederse devam edilebilir.

Boş sonucun "kimse çalışmıyor" mu yoksa "göremiyorum" mu olduğunu ayıran tek şey budur.

## 4. Çakışma kontrolü

Dönen her kayıt için `Dokunulan alanlar` ile senin gireceğin dosyaları karşılaştır. **Kanaryayı karşılaştırmaya katma** (`Tür = "Kanarya"`) — hiçbir dosyayla çakışmaz.

Ölçüt **"başkasına ait" değil, "bu oturuma ait değil"**. Her iki geliştirici de hem Claude Code hem Codex kullanıyor; `Kişi` alanı seninkiyle aynı diye bir kaydı atlarsan kendi kardeş ajanınla çakışırsın — en olası çakışma senaryosu bu, çünkü ikisi çoğu zaman aynı makinede.

Kesişme varsa: **başlama.** Kullanıcıya hangi kayıtla, hangi dosyalarda çakıştığını söyle, ne yapılacağını sor.

## 5. Son 7 günün devirlerini oku

`Tür = "Devir"` veya `Durum = "Devredildi"` olan son kayıtlar. Yarım kalmış iş, sıradaki adım ve dikkat notları orada. Bulduklarını kullanıcıya özetle.

## 6. Kendi kaydını aç

| Alan | Değer |
|---|---|
| `Kayıt` | `<tarih> · <kişi> · <ajan> · <DW-ID>` — ajan adı zorunlu |
| `Tarih` | bugün |
| `Kişi` | 1. adımda belirlenen: `Mirza` veya `Ömer` |
| `Ajan` | `Claude Code` veya `Codex` |
| `Tür` | `Günlük` |
| `Durum` | `Devam ediyor` |
| `Görev` | ilgili DW görevi (varsa) |
| `Proje` | ilgili proje |
| `Branch` | mevcut branch |
| `Dokunulan alanlar` | gireceğin dosya/dizinler, virgülle ayrık |

Ayrı bir çalışma dizininde (git worktree) çalışıyorsan worktree yolunu da `Dokunulan alanlar`a yaz.

## 7. Raporla

Kullanıcıya kısaca: kimlik ne belirlendi, kanarya göründü mü, kaç aktif kayıt vardı, çakışma var mıydı, hangi devir notları bulundu, kaydın açıldı mı.

## Sonrası — kontrol bir kerelik değil

Buradaki sonuç **o anki kapsam için** geçerlidir. `Dokunulan alanlar`da yazmayan bir dosyaya ilk kez dokunmadan önce alanı güncelle ve çakışma sorgusunu tekrarla (`AGENTS.md` → "Oturum SIRASINDA").

Gerçek çakışmaların çoğu oturum ortasında doğar: iş büyür, ortak bir dosyaya uzanırsın, ama kaydın hâlâ eski kapsamı gösterir ve karşı taraf seni orada göremez.
