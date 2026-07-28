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

Boşsa veya tabloda yoksa **kullanıcıya sor** — tahmin etme. Yanlış atfedilen kayıt sessizce yanlış kalır.

## 2. Aktif kayıtları sorgula

Notion `📓 Oturum Kaydı` (`collection://280e2fd0-a14a-4d2d-ac25-24585472348e`):

```sql
SELECT "Kayıt", "Kişi", "Ajan", "Tür", "Branch", "Dokunulan alanlar"
FROM "collection://280e2fd0-a14a-4d2d-ac25-24585472348e"
WHERE "Durum" = 'Devam ediyor'
```

**Sorgu hata verirse durma noktası burasıdır.** Bu SQL aracı ücretsiz planda saatlik kotalı. Hatayı "aktif kayıt yok" diye yorumlama — protokolün tüm güvencesi bu sorguda.

Kota dolduysa yedek yol: aynı data source'ta arama yap, dönen kayıtları tek tek aç, `Durum` alanına bak. Yavaş ama kotasız. İkisi de başarısızsa kullanıcıya söyle ve **çoklu-ajan işine başlama**.

> Kota bütçesi: SQL yalnızca bu sorgu için harcanır. Raporlama ve listeleme `fetch`/`search` ile yapılır — onlar kotasız.

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
