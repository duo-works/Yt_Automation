# Mimari Karar Kayıtları (ADR)

ADR = **A**rchitecture **D**ecision **R**ecord. Kısa, tarihli, değiştirilemez bir belge: "şu tarihte, şu nedenle, şunu seçtik."

## Ne zaman ADR yazılır

Şu sorulardan **birine** evet diyorsanız yazın:

- Bu karardan dönmek pahalı mı? (veritabanı seçimi, auth stratejisi, deploy hedefi)
- Altı ay sonra biri "bu neden böyle?" diye sorar mı?
- İki alternatif arasında bilinçli bir tercih mi yaptık?

Şunlar için **yazmayın:** kütüphane sürüm yükseltmesi, klasör yeniden adlandırma, stil tercihi.

## Nasıl yazılır

1. Bir sonraki numarayı al (`0002`, `0003`…). Numaralar tekrar kullanılmaz.
2. `NNNN-kisa-baslik.md` adıyla dosya oluştur, aşağıdaki şablonu doldur.
3. Aynı PR içinde commit et — karar, onu uygulayan kodla birlikte gelir.
4. Notion → **Kararlar** database'ine aynı başlıkla bir kayıt aç, bu dosyanın GitHub linkini ekle.

## Karar değişirse

Eski dosyayı **silme ve düzenleme.** Durumunu `Değiştirildi — bkz. 0007` yap ve yeni bir ADR yaz. ADR'lerin değeri değişmez olmalarından gelir.

---

## Şablon

```markdown
# NNNN — <Karar başlığı>

- **Durum:** Önerildi | Kabul | Reddedildi | Değiştirildi (bkz. NNNN)
- **Tarih:** YYYY-AA-GG
- **Karar verenler:** <isimler>
- **İlgili görev:** DW-<numara>

## Bağlam

Hangi problemi çözüyoruz? Hangi kısıtlar var? Karar anında bilinenler neydi?

## Değerlendirilen seçenekler

1. **<Seçenek A>** — artıları / eksileri
2. **<Seçenek B>** — artıları / eksileri

## Karar

Neyi seçtik ve neden. Tek paragraf yeterli.

## Sonuçlar

Bu karar neyi kolaylaştırdı, neyi zorlaştırdı? Hangi yeni kısıtı kabul ettik?
```
