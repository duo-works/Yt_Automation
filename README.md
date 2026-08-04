# Yt_Automation

> Kendi YouTube kanallarımız için yükleme, metadata, thumbnail ve raporlama otomasyonu.

> ### 🤖 AI ajanıysan buradan başla
>
> **Bu repoda herhangi bir iş yapmadan önce [`AGENTS.md`](AGENTS.md) dosyasını oku — zorunludur.**
>
> İçinde: oturum protokolü (çakışma kontrolü, devir kayıtları), kesin kurallar, hazır komutlar ve Notion referansları. Projeyi tanımak için oradaki **"İlk kez buradaysan — okuma sırası"** bölümünü izle; repo ve Notion'u birlikte kapsıyor.
>
> Bu repoda iki geliştirici **dört ayrı ajanla** çalışıyor. Protokolü atlarsan başkasının açık işinin üzerine yazabilirsin.

---

## Bu proje şu an nerede

**İskelet `main`'de çalışıyor, yükleme hattı henüz yok.**

- **Teknoloji yığını** — seçildi (DW-6): Python 3.13, resmî Google istemcileri, dosya tabanlı girdi. Gerekçe: [`docs/decisions/0004-teknoloji-yigini.md`](docs/decisions/0004-teknoloji-yigini.md)
- **`main`'de ne var** — `ytoto` CLI'ı, metadata doğrulama ve kota muhasebesi (`src/yt_automation/`)
- **Kapsam** — PRD'de kesinleşti; v1'i bloke eden açık soru kalmadı
- **Yükleme hattı** — OAuth (DW-21), `videos.insert` (DW-22) ve thumbnail (DW-23) inceleme aşamasında, henüz `main`'de değil
- **Deploy hedefi** — belirlenmedi (DW-8). v1 yerelde elle çalışıyor.

> CI'da bir dilin job'ı **atlanmış** görünüyorsa sebebi yığının seçilmemiş olması değil, o branch'te o dile ait dosyanın değişmemesidir — `Stack tespiti` job'ı değişen dosyalara bakarak karar veriyor.

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

Python 3.13 gerekiyor.

```bash
gh repo clone duo-works/Yt_Automation
cd Yt_Automation
cp .env.example .env    # gerçek değerleri parola yöneticisinden alın

python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Doğrulama:

```bash
.venv/bin/pytest          # testler
.venv/bin/ruff check .    # lint
.venv/bin/ytoto --help    # CLI
```

---

## Katkı

Kod yazmaya başlamadan önce [`CONTRIBUTING.md`](CONTRIBUTING.md) dosyasını okuyun. Özet:

1. Notion'da görevi **Yapılıyor**'a alın
2. `main`'den branch açın: `feat/DW-42-kisa-aciklama`
3. PR başlığı: `feat(kapsam): açıklama [DW-42]`
4. Yeşil CI → squash merge (insan onayı ön koşul değil)
5. Notion'da görevi **Bitti**'ye alın

`main`'e doğrudan push kapalıdır — ve bu **iddia değil, doğrulanmış bir gerçek**:
koruma kuralları DW-1'de uçtan uca sınandı. Kasten yanlış yazılmış bir PR başlığı
reddedildi, doğru başlık geçti, korumasız bir push `GH006` ile durduruldu.

Branch adı, commit mesajı ve PR gövdesi CI tarafından doğrulanır; `ci-ok` ve
`pr-title-ok` zorunlu kontrollerdir ve yönetici hesaplara da uygulanır.
