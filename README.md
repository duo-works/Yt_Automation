# Yt_Automation

> Kendi YouTube kanallarımız için yükleme, metadata, thumbnail ve raporlama otomasyonu.

---

## Bu proje şu an nerede

**Henüz kod yok.** Proje planlama aşamasında:

- **Kapsam** — PRD taslak halinde, 6 açık sorusu var (DW-5)
- **Teknoloji yığını** — henüz seçilmedi (DW-6). Bu yüzden CI'ın Node ve Python job'ları atlanıyor.
- **Deploy hedefi** — belirlenmedi (DW-8)

Canlı durum için **[📋 Görevler](https://app.notion.com/p/93190546ef3941c88ab1d2bd0d1fface)**'e bakın — burası hızla eskir, orası eskimez.

İlk sürümde **olmayacaklar** PRD'de yazılı: AI ile video/thumbnail üretimi, SEO araştırması, yorum yönetimi, çoklu kullanıcı, web arayüzü. Kapsam kayması buradan önlenir.

---

## Bu repo nasıl çalışır

| İhtiyacınız | Nereye bakacaksınız |
|---|---|
| Ne yapacağım? Görev listesi? | **[📋 Görevler](https://app.notion.com/p/93190546ef3941c88ab1d2bd0d1fface)** — bu repo'da Issues kapalıdır |
| Nasıl çalışıyoruz? Branch, commit, PR kuralları | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Neden böyle yapılmış? Mimari kararlar | [`docs/decisions/`](docs/decisions/) · **[🧭 Kararlar](https://app.notion.com/p/79735f2d234744bca1c73ebc62d20788)** |
| Proje ne yapacak? Kapsam ne? | **[🎬 Yt_Automation PRD](https://app.notion.com/p/3a79bfc93b2e813087b6c35c78af0ee7)** |
| PRD, mimari doküman, API notları | **[📚 Bilgi Bankası](https://app.notion.com/p/6c92e82ed17c427ba0d515c827fac07e)** |
| AI ajanı ile çalışırken konvansiyonlar | [`AGENTS.md`](AGENTS.md) — Claude Code ve Codex için tek kaynak |
| Kim şu an neye dokunuyor? Devir notları | **[📓 Oturum Kaydı](https://app.notion.com/p/cb1df32162934baba379c8733813893f)** |

🔗 **Notion çalışma alanı:** [🛠️ duo-works](https://app.notion.com/p/3a79bfc93b2e81048f7ddf02d3de4a38)

---

## Yeni katılıyorsanız

1. **[🚪 Onboarding](https://app.notion.com/p/3a79bfc93b2e81b589e6fe2918e64a00)** — 30 dakikada devreye girme rehberi
2. **[🤖 Ajan Kurulumu](https://app.notion.com/p/3a89bfc93b2e8125b9d5e6a99682d706)** — Claude Code ve Codex'i koordinasyon sistemine bağlama

İkinci adımı atlamayın. Ajanınız Notion'a yazamıyorsa karşı tarafın ajanı "aktif kayıt yok" görüp aynı dosyaya girer.

---

## Kurulum

```bash
gh repo clone duo-works/Yt_Automation
cd Yt_Automation
cp .env.example .env    # gerçek değerleri parola yöneticisinden alın
```

<!-- Stack seçildikten sonra (DW-6) buraya bağımlılık kurulum ve çalıştırma adımları eklenir. -->

---

## Katkı

Kod yazmaya başlamadan önce [`CONTRIBUTING.md`](CONTRIBUTING.md) dosyasını okuyun. Özet:

1. Notion'da görevi **Yapılıyor**'a alın
2. `main`'den branch açın: `feat/DW-42-kisa-aciklama`
3. PR başlığı: `feat(kapsam): açıklama [DW-42]`
4. Onay + yeşil CI → squash merge
5. Notion'da görevi **Bitti**'ye alın

`main`'e doğrudan push kapalıdır. Branch adı, commit mesajı ve PR gövdesi CI tarafından doğrulanır.
