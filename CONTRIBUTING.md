# Katkı Kuralları

Bu dosya `duo-works` altındaki **tüm** projeler için tek otoritedir. Bir konuda tereddüt varsa burası geçerlidir.

---

## 1. Ne nerede yaşar

Karışıklığın tek panzehiri, her bilgi türünün tek bir adresi olmasıdır.

| Bilgi türü | Tek adres | Kesinlikle olmayacağı yer |
|---|---|---|
| Görev, hata, durum, öncelik, kime ait | **Notion → Görevler** | GitHub Issues (kapalı) |
| Kod, diff, teknik tartışma, review | **GitHub PR** | Notion yorumları |
| Uzun form doküman (PRD, mimari, API notu) | **Notion → Bilgi Bankası** | Repo kökünde `*_PLAN.md` |
| Kalıcı mimari kararlar | **`docs/decisions/` + Notion → Kararlar** | Dağınık not |
| Sırlar, API anahtarları | Parola yöneticisi | Repo, Notion, commit'lenmiş `.env` |
| Sprint hedefi, toplantı notu | **Notion** | — |
| Oturum günlüğü, devir notu, kim neye dokunuyor | **Notion → 📓 Oturum Kaydı** | Repo içi handoff dosyası |

> **Repo kökünde plan/rapor dosyası açmayın.** Uzun form her şey Notion'a gider. Repo'da sadece `README`, `CONTRIBUTING`, `CLAUDE.md` ve `docs/decisions/` altındaki ADR'ler bulunur.

Bağlayıcı iplik: her görevin Notion'da `DW-42` gibi bir ID'si vardır. Branch adı, PR başlığı ve commit gövdesi hep bu ID'yi taşır — böylece PR'dan göreve, görevden PR'a tek tıkla gidilir.

---

## 2. Branch modeli

**GitHub Flow.** `main` her an deploy edilebilir durumdadır. `develop` branch'i yoktur — iki kişilik ekipte gereksiz karmaşadır.

`main`'e **doğrudan push yapılmaz.** Her değişiklik bir PR üzerinden geçer.

### Branch adı

```
<tür>/<NOTION-ID>-<kisa-aciklama>
```

```
feat/DW-42-kullanici-girisi
fix/DW-57-tarih-formati-hatasi
refactor/DW-60-siparis-servisi
docs/DW-61-api-dokumantasyonu
chore/DW-63-bagimlilik-guncelleme
```

Açıklama kısmı Türkçe, küçük harf, kelimeler tire ile ayrılır, Türkçe karakter kullanılmaz (`ş`→`s`, `ı`→`i`, `ğ`→`g`, `ü`→`u`, `ö`→`o`, `ç`→`c`).

> ⚙️ **CI bunu zorunlu tutar.** `.github/workflows/pr-kurallari.yml` → `branch-adi`. Uymayan branch'in PR'ı kırmızı olur.

---

## 3. Commit mesajları

[Conventional Commits](https://www.conventionalcommits.org/), açıklama Türkçe:

```
feat(auth): e-posta ile giriş akışı

Notion: DW-42
```

**Türler:**

| Tür | Ne zaman |
|---|---|
| `feat` | Yeni özellik |
| `fix` | Hata düzeltme |
| `refactor` | Davranışı değiştirmeyen kod düzenlemesi |
| `docs` | Dokümantasyon |
| `test` | Test ekleme/düzeltme |
| `chore` | Bağımlılık, config, araç işleri |
| `perf` | Performans iyileştirme |

Kapsam (`(auth)`, `(orders)`) opsiyoneldir ama tavsiye edilir. Gövdeye `Notion: DW-42` satırını ekleyin.

> ⚙️ **CI bunu zorunlu tutar.** `pr-kurallari.yml` → `commit-mesaji`, branch'teki her commit'i tek tek kontrol eder (merge commit'leri hariç).
>
> Squash merge nedeniyle bu mesajların ömrü branch kadar — `main`'e giden tek commit'in mesajı PR başlığı ve gövdesinden oluşur. Yine de zorunlu: mesajlar squash gövdesinde toplanıyor ve çalışırken "hangi commit hangi göreve ait" izini koruyor.

---

## 4. Pull Request

### Başlık formatı — CI bunu zorunlu tutar

```
<tür>(<kapsam>): <açıklama> [DW-<numara>]
```

```
feat(auth): e-posta ile giriş akışı [DW-42]
fix(orders): tarih formatı hatası [DW-57]
```

`.github/workflows/pr-kurallari.yml` bu formatı doğrular. Uymayan PR **kırmızı** olur ve merge edilemez.

### PR gövdesi

Şablonun ilk bölümü (`## Notion görevi`) doldurulmalı: DW numarası **ve** görevin Notion linki.

> ⚙️ **CI bunu zorunlu tutar.** `pr-kurallari.yml` → `pr-govdesi`. Şablondaki `Link:` satırı yorum olarak bırakılırsa kontrol düşer.

### Hangi kontrol neyi bakar

| Job | Kural |
|---|---|
| `baslik` | §4 — PR başlığı formatı |
| `branch-adi` | §2 — branch adı formatı |
| `commit-mesaji` | §3 — Conventional Commits + `Notion: DW-<n>` |
| `pr-govdesi` | §4 — PR gövdesindeki Notion bağı |
| `ajan-dosyalari` | ADR-0002 — `AGENTS.md` bütünlüğü, `CLAUDE.md` bağı |

Beşi de `pr-title-ok` adlı kapı job'ına bağlı. Branch protection **yalnızca o adı** zorunlu tutuyor; bu yüzden kapı job'ının adı değiştirilmemeli — değişirse koruma kuralı sessizce devre dışı kalır.

### Kurallar

- **PR başına tek görev.** İki görevi bir PR'a sıkıştırmayın. Bölme kararının
  asıl ölçütü budur, satır sayısı değil.
- **~1.200 satır değişim hedefi.** Daha büyükse görevi Notion'da bölmeyi
  değerlendirin.

  > Eşik 2026-08-04'te 400'den yükseltildi. Bu repoda hiçbir PR 400'ü tutmadı:
  > bir özellik kod + test + ADR ile birlikte geliyor ve testler çoğu zaman
  > kodun kendisinden uzun (DW-58 PR'ı 1.214 satırdı, 519'u test). Her PR'da
  > çıkan bir uyarıya kimse bakmaz; tutulmayan kural, tutulan kuralların da
  > ciddiyetini aşındırır.
- **Squash merge zorunlu.** Geçmiş lineer ve okunabilir kalır.
- Merge sonrası branch otomatik silinir.
- **CI yeşil olmadan merge yapılmaz.** İnsan onayı ön koşul değildir (ADR-0012).

---

## 5. Bir görevin baştan sona akışı

1. **Notion** → görevi **In progress**'e al; `Sorumlu` alanında `Mirza` veya `Ömer` seç. Ortak hesap nedeniyle `Sahip` person alanı ekip kişisini ayıramaz.
2. `main`'i güncelle, branch aç:
   ```bash
   git switch main
   git pull
   git switch -c feat/DW-42-kullanici-girisi
   ```
3. Küçük commit'lerle çalış
4. Push et ve PR aç:
   ```bash
   git push -u origin HEAD
   gh pr create --title "feat(auth): e-posta ile giriş akışı [DW-42]" --fill
   ```
5. **Notion** → görevi **İncelemede**'ye al, PR linkini `GitHub PR` alanına yapıştır
6. CI yeşil → **squash merge** (kimsenin onayını beklemezsiniz)
7. **Notion** → görevi **Bitti**'ye al
8. Yerelde temizle:
   ```bash
   git switch main
   git pull
   git branch -d feat/DW-42-kullanici-girisi
   ```

> 💻 **Ekip iki farklı platformda:** macOS/zsh ve Windows/PowerShell 5.1. Dokümanlardaki komutlar bu yüzden **her kabukta çalışacak biçimde** yazılır: komutları `&&` ile zincirlemeyin, ayrı satıra alın (`&&` PowerShell 5.1'de sözdizimi hatası). Karşılığı olmayan bir komut gerekiyorsa (`mkdir -p` gibi) iki blok yazın.

---

## 6. Çakışmayı önleyen tek kural

**Bir görev aynı anda tek kişide olur.** `Sorumlu` alanı mutlaka `Mirza` veya `Ömer` olmalıdır.

İkiniz de aynı dosyaya gireceksiniz diye endişeleniyorsanız, çözüm kod tarafında değil: önce Notion'da görevi bölün. Kod üstünde değil, **görev üstünde** koordine olun.

### AI ajanlarıyla çalışırken

İkiniz de kendi ajanınızla (Claude Code, Codex) aynı repo üzerinde çalışıyorsunuz. Ajanlar birbirini göremez — bu yüzden **Notion → 📓 Oturum Kaydı** zorunludur:

- **Oturum başında** ajan, `Durum = Devam ediyor` olan kayıtları sorgular. Sizin gireceğiniz dosyalar başkasının aktif kaydındaki `Dokunulan alanlar` ile kesişiyorsa ajan **durur** ve size sorar.
- **Oturum sonunda** ajan kendi kaydını günceller: ne yapıldı, sıradaki adım, durum.
- Yarım bırakılan iş `Devredildi` olarak işaretlenir; diğerinin ajanı bir sonraki oturumda bunu okur.

Protokolün tam hali [`AGENTS.md`](AGENTS.md) içindedir — Claude Code ve Codex aynı dosyayı okur.

Uzun süren bir branch'te çalışıyorsanız günde bir kez `main`'i içine alın:

```bash
git switch main
git pull
git switch feat/DW-42-kullanici-girisi
git merge main
```

---

## 7. Review — isteğe bağlı

**İnsan review'ı merge ön koşulu değildir.** Onay şartı 2026-08-04'te kaldırıldı: iki kişilik bir ekipte karşılıklı onay beklemek, 28 PR'lık bir yığında kilitlenmeye dönüştü. Gerekçe ve korunanlar: [ADR-0012](docs/decisions/0012-org-repo-politikasi.md).

Kaldırılan şey **zorunluluk**, review'ın kendisi değil. Yığından öğrenilen kusurların çoğu — WAL yarışı, kontrol edilmeyen `ruff format`, zincirde koşmayan CI — review'la değil **ölçümle** bulundu. Kapıyı CI tutuyor.

Review bırakıyorsanız şunlara bakın:

- Kod, PR'ın bağlı olduğu Notion görevinin kapsamında mı? (kapsam kayması var mı)
- İsimlendirme ve desenler repo'nun geri kalanıyla tutarlı mı?
- Sır/anahtar sızmış mı?
- Kalıcı bir mimari karar alınmışsa `docs/decisions/` altına ADR eklenmiş mi?

Yorum yazarken "LGTM" yerine neye baktığınızı bir cümleyle belirtin — altı ay sonra o cümle, tikten fazlasını anlatır.

---

## 8. Sırlar

- Gerçek `.env` dosyası **asla** commit edilmez. `.gitignore` bunu engeller ama son sorumluluk sizde.
- Yeni bir ortam değişkeni eklediğinizde `.env.example` dosyasına **değersiz** olarak ekleyin.
- Gerçek değerler parola yöneticisinde paylaşılır — Notion'da, WhatsApp'ta veya PR yorumunda değil.
- Yanlışlıkla sır commit'lediyseniz: anahtarı **hemen iptal edin**, sonra geçmişi temizleyin. Sıra bu şekildedir.
