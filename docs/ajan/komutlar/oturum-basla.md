# /oturum-basla

`AGENTS.md` → "Oturum BAŞINDA" protokolünü uygula. Kod yazmadan önce çalıştırılır.

## 1. Aktif kayıtları sorgula

Notion `📓 Oturum Kaydı` (`collection://280e2fd0-a14a-4d2d-ac25-24585472348e`):

```sql
SELECT "Kayıt", "Kişi", "Ajan", "Branch", "Dokunulan alanlar"
FROM "collection://280e2fd0-a14a-4d2d-ac25-24585472348e"
WHERE "Durum" = 'Devam ediyor'
```

**Sorgu hata verirse durma noktası burasıdır.** Bu SQL aracı ücretsiz planda saatlik kotalı. Hatayı "aktif kayıt yok" diye yorumlama — protokolün tüm güvencesi bu sorguda.

Kota dolduysa yedek yol: aynı data source'ta arama yap, dönen kayıtları tek tek aç, `Durum` alanına bak. Yavaş ama kotasız. İkisi de başarısızsa kullanıcıya söyle ve **çoklu-ajan işine başlama**.

## 2. Çakışma kontrolü

Dönen her kayıt için `Dokunulan alanlar` ile senin gireceğin dosyaları karşılaştır.

Ölçüt **"başkasına ait" değil, "bu oturuma ait değil"**. Her iki geliştirici de hem Claude Code hem Codex kullanıyor; `Kişi` alanı seninkiyle aynı diye bir kaydı atlarsan kendi kardeş ajanınla çakışırsın — en olası çakışma senaryosu bu, çünkü ikisi çoğu zaman aynı makinede.

Kesişme varsa: **başlama.** Kullanıcıya hangi kayıtla, hangi dosyalarda çakıştığını söyle, ne yapılacağını sor.

## 3. Son 7 günün devirlerini oku

`Tür = "Devir"` veya `Durum = "Devredildi"` olan son kayıtlar. Yarım kalmış iş, sıradaki adım ve dikkat notları orada. Bulduklarını kullanıcıya özetle.

## 4. Kendi kaydını aç

| Alan | Değer |
|---|---|
| `Kayıt` | `<tarih> · <kişi> · <ajan> · <DW-ID>` — ajan adı zorunlu |
| `Tarih` | bugün |
| `Kişi` | kullanıcı |
| `Ajan` | `Claude Code` veya `Codex` |
| `Tür` | `Günlük` |
| `Durum` | `Devam ediyor` |
| `Görev` | ilgili DW görevi (varsa) |
| `Proje` | ilgili proje |
| `Branch` | mevcut branch |
| `Dokunulan alanlar` | gireceğin dosya/dizinler, virgülle ayrık |

Ayrı bir çalışma dizininde (git worktree) çalışıyorsan worktree yolunu da `Dokunulan alanlar`a yaz.

## 5. Raporla

Kullanıcıya kısaca: kaç aktif kayıt vardı, çakışma var mıydı, hangi devir notları bulundu, kaydın açıldı mı.
