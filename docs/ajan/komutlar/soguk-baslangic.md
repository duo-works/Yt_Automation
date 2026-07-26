# /soguk-baslangic

Projeyi sıfırdan öğren ve **kaynaklı** bir özet üret. Yeni bir ajan devreye girdiğinde ilk çalıştırılan komut.

Çıktısı `/denetle` ile denetlenebilir olmalı — bu yüzden biçim zorunlu.

## 1. Oku

`AGENTS.md` → "İlk kez buradaysan — okuma sırası" bölümündeki yedi adımı sırayla uygula. Atlama, sıralamayı değiştirme.

Notion bağlantın yoksa 3, 4 ve 5. adımları okuyamazsın. Bu durumda **uydurma**: hangi alanların eksik kaldığını çıktında açıkça yaz.

## 2. Kaynaklı özet üret

`AGENTS.md` → "Kullanıcıya ne anlatmalısın" başlığındaki altı alanı sırayla cevapla. **Her iddianın altına kaynağını yaz:**

```
Kod henüz yok, yığın seçilmedi.
  └ kaynak: DW-6 (Not started) · README §Bu proje şu an nerede

v1'de AI ile video üretimi YOK — ikinci faz.
  └ kaynak: PRD §Kapsam — ilk sürümde OLMAYACAKLAR

Kota tavanı günde ~5 video.
  └ kaynak: PRD §Kota bütçesi — PRD "güncel dokümandan teyit edin" diyor
```

Geçerli kaynak biçimleri:

| Tür | Örnek |
|---|---|
| Notion sayfası + bölüm | `PRD §Bilinen kısıtlar` |
| Görev | `DW-6 (Not started)` |
| Repo dosyası | `AGENTS.md §Kesin kurallar` · `docs/decisions/0002-...` |
| Sorgu sonucu | `Oturum Kaydı sorgusu: 0 aktif kayıt` |
| Komut çıktısı | `git rev-list --count origin/main → 1` |

## 3. Kurallar

**Kaynağını gösteremediğin şeyi yazma.** Emin değilsen "bilmiyorum" veya "bulamadım" de — bu başarısızlık sayılmaz. **Uydurmak** başarısızlıktır.

Şunları ayrıca işaretle:

- **Karar mı, taslak mı, açık soru mu?** Cevaplanmamış bir soruyu karar gibi sunma. PRD'de açık sorular varsa hepsini listele.
- **Doğrulanması istenen sayılar** — kaynak "teyit edilmeli" diyorsa sen de öyle sun, kesin gerçek gibi değil.
- **Kaynaklar çelişiyorsa** hangi ikisinin çeliştiğini yaz, birini seçip diğerini gizleme.
- **Merge edilmemiş iş** — bir şey PR'da ise `main`'de var gibi anlatma.

## 4. Sonunda

Şunu ekle: hangi kaynaklara erişebildin, hangilerine erişemedin, ve özetinde en az emin olduğun madde hangisi.

Bu son cümle denetimin başlangıç noktası olur.
