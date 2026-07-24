# <PROJE ADI>

> <Bir cümlelik proje açıklaması.>

---

## Bu repo nasıl çalışır

| İhtiyacınız | Nereye bakacaksınız |
|---|---|
| Ne yapacağım? Görev listesi? | **Notion → Görevler** — bu repo'da Issues kapalıdır |
| Nasıl çalışıyoruz? Branch, commit, PR kuralları | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Neden böyle yapılmış? Mimari kararlar | [`docs/decisions/`](docs/decisions/) |
| PRD, mimari doküman, API notları | **Notion → Bilgi Bankası** |
| AI ajanı ile çalışırken konvansiyonlar | [`CLAUDE.md`](CLAUDE.md) |

🔗 **Notion çalışma alanı:** `<TEAMSPACE LİNKİ>`

---

## Kurulum

```bash
gh repo clone duo-works/<PROJE>
cd <PROJE>
cp .env.example .env    # gerçek değerleri parola yöneticisinden alın
```

<!-- Stack seçildikten sonra buraya bağımlılık kurulum ve çalıştırma adımları eklenir. -->

---

## Katkı

Kod yazmaya başlamadan önce [`CONTRIBUTING.md`](CONTRIBUTING.md) dosyasını okuyun. Özet:

1. Notion'da görevi **Yapılıyor**'a alın
2. `main`'den branch açın: `feat/DW-42-kisa-aciklama`
3. PR başlığı: `feat(kapsam): açıklama [DW-42]`
4. Onay + yeşil CI → squash merge
5. Notion'da görevi **Bitti**'ye alın

`main`'e doğrudan push kapalıdır.
