# docs/

Bu klasörde **sadece** mimari kararlar (ADR) bulunur.

## Buraya ne yazılır

- `decisions/` → Alınmış kalıcı teknik kararlar. Geri dönülemez ya da geri dönmesi pahalı olan seçimler.

## Buraya ne YAZILMAZ

| İçerik | Doğru yeri |
|---|---|
| PRD, ürün gereksinimi | Notion → Bilgi Bankası |
| Mimari genel bakış, sistem şeması | Notion → Bilgi Bankası |
| Yapılacaklar listesi, faz planı | Notion → Görevler |
| Toplantı notu | Notion → Toplantı Notları |
| Araştırma / karşılaştırma notu | Notion → Bilgi Bankası |
| Geçici çalışma notu | Hiçbir yere commit etmeyin |

**Neden bu ayrım?** Kod ile birlikte versiyonlanması gereken tek doküman türü mimari kararlardır — bir kararın hangi commit'te alındığını görmek değerlidir. Geri kalan her şey yaşayan dokümandır ve Notion'da güncel kalır. İkisi karışırsa hangisinin güncel olduğu belirsizleşir; asıl karışıklık kaynağı budur.
