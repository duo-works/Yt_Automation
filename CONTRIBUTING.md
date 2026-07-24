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

`.github/workflows/pr-title.yml` bu formatı doğrular. Uymayan PR **kırmızı** olur ve merge edilemez.

### Kurallar

- **PR başına tek görev.** İki görevi bir PR'a sıkıştırmayın.
- **~400 satır değişim hedefi.** Daha büyükse görevi Notion'da bölün.
- **Squash merge zorunlu.** Geçmiş lineer ve okunabilir kalır.
- Merge sonrası branch otomatik silinir.
- Onay olmadan ve CI yeşil olmadan merge yapılmaz.

---

## 5. Bir görevin baştan sona akışı

1. **Notion** → görevi **Yapılıyor**'a al, kendine ata
2. `main`'i güncelle, branch aç:
   ```bash
   git switch main && git pull
   git switch -c feat/DW-42-kullanici-girisi
   ```
3. Küçük commit'lerle çalış
4. Push et ve PR aç:
   ```bash
   git push -u origin HEAD
   gh pr create --title "feat(auth): e-posta ile giriş akışı [DW-42]" --fill
   ```
5. **Notion** → görevi **İncelemede**'ye al, PR linkini `GitHub PR` alanına yapıştır
6. Diğerinin onayı + CI yeşil → **squash merge**
7. **Notion** → görevi **Bitti**'ye al
8. Yerelde temizle:
   ```bash
   git switch main && git pull && git branch -d feat/DW-42-kullanici-girisi
   ```

---

## 6. Çakışmayı önleyen tek kural

**Bir görev aynı anda tek kişide olur.**

İkiniz de aynı dosyaya gireceksiniz diye endişeleniyorsanız, çözüm kod tarafında değil: önce Notion'da görevi bölün. Kod üstünde değil, **görev üstünde** koordine olun.

Uzun süren bir branch'te çalışıyorsanız günde bir kez `main`'i içine alın:

```bash
git switch main && git pull
git switch feat/DW-42-kullanici-girisi
git merge main
```

---

## 7. Review beklentileri

Gözden geçiren kişi şunlara bakar:

- Kod, PR'ın bağlı olduğu Notion görevinin kapsamında mı? (kapsam kayması var mı)
- İsimlendirme ve desenler repo'nun geri kalanıyla tutarlı mı?
- Sır/anahtar sızmış mı?
- Kalıcı bir mimari karar alınmışsa `docs/decisions/` altına ADR eklenmiş mi?

**Onay verirken "LGTM" yeterli değildir.** En az bir cümle ile neye baktığınızı yazın. Yorum yapmadan onaylanan PR, review sayılmaz.

---

## 8. Sırlar

- Gerçek `.env` dosyası **asla** commit edilmez. `.gitignore` bunu engeller ama son sorumluluk sizde.
- Yeni bir ortam değişkeni eklediğinizde `.env.example` dosyasına **değersiz** olarak ekleyin.
- Gerçek değerler parola yöneticisinde paylaşılır — Notion'da, WhatsApp'ta veya PR yorumunda değil.
- Yanlışlıkla sır commit'lediyseniz: anahtarı **hemen iptal edin**, sonra geçmişi temizleyin. Sıra bu şekildedir.
