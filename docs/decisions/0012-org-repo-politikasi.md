# ADR-0012 — Org repo politikası: squash-only, gizli tarama, zorunlu kontroller

- **Durum:** Kabul edildi
- **Tarih:** 2026-08-04
- **Görev:** DW-75

## Bağlam

`duo-works` altında beş repo var ve **ikisi iki farklı rejimde çalışıyordu.** Ölçüldü (2026-08-04, ADR yazılmadan hemen önce):

| Repo | Koruma | Squash-only | Gizli tarama | Zorunlu kontrol |
|---|---|---|---|---|
| `Yt_Automation` | ✅ | ✅ | ✅ | `ci-ok` + `pr-title-ok` |
| `project-template` | ✅ | ✅ | ✅ | `ci-ok` + `pr-title-ok` |
| `tablo_studio` | kısmi | ❌ üçü de açık | ❌ | **hiç** |
| `notion-yedek` | ❌ yok | ✅ | — (özel repo) | — |
| `MoneyPrinterTurbo` | ❌ yok | ❌ üçü de açık | ❌ | — |

Somut sonucu: `tablo_studio`'da **1.096 satırlık PR #1** tek bir check taşımadan açık duruyordu. Yani ilk repoda bir PR beş kuraldan geçmeden merge edilemezken, ikincisinde hiçbir şey kayda geçmiyordu.

Bu ADR farkı politika olarak kapatıyor — ve daha önemlisi, **kapsam dışında bırakılan repoların neden dışarıda olduğunu** yazıyor. Yazılmayan istisna, unutulmuş eksik ile bilinçli karar arasındaki farkı yok eder.

## Kapsam

**Politikaya tabi:** ekibin kendi ürettiği kod repoları — `Yt_Automation`, `project-template`, `tablo_studio`.

**Bilinçli olarak dışarıda:**

- **`MoneyPrinterTurbo`** — bu bir çalışma kopyası; upstream `harry0703/MoneyPrinterTurbo` ile hizada kalması gerekiyor. Bizim commit/branch konvansiyonumuzu dayatmak upstream'den alım yapmayı zorlaştırır. ADR-0011'in "MPT'ye dokunulmaz" değişmezinin repo düzeyindeki karşılığı.
- **`notion-yedek`** — özel, üretilmiş dökümden ibaret (Markdown + CSV). İnsan yazdığı kod yok, review edilecek bir şey yok.

## Karar

### 1 · Squash-only bir mekaniktir, politika değil

Üç repoda da `allow_merge_commit=false`, `allow_rebase_merge=false`, `allow_squash_merge=true`, `delete_branch_on_merge=true`.

Gerekçe: "squash merge zorunlu" cümlesi `AGENTS.md`'de zaten yazıyordu ama arayüzde diğer iki düğme duruyordu. Yazılı kural + açık düğme, kuralın er geç çiğneneceği anlamına gelir. `required_linear_history=true` bunu ikinci katmandan da bağlar.

### 2 · Gizli tarama ve push koruması her yerde açık

`secret_scanning` + `secret_scanning_push_protection`.

Push koruması özellikle `tablo_studio` için gerekliydi: repo'nun `.gitignore`'unda **`.env` deseni hiç yoktu** ve o repoya `NOTION_TOKEN` girmek üzereydi. Desen PR #1'de eklendi, ama `.gitignore` yalnızca dikkatsizliğe karşı korur — push koruması yanlışlıkla commit edilmiş bir anahtarı sunucu tarafında durdurur.

### 3 · Zorunlu kontroller: iki ayrı kapı

| Kapı | Ne doğrular | Bağımlılık |
|---|---|---|
| `pr-title-ok` | PR başlığı, branch adı, PR gövdesindeki Notion linki, commit mesajları, `AGENTS.md`/`CLAUDE.md` bütünlüğü | **yok** — saf shell |
| `ci-ok` | lint (`ruff check` + `ruff format --check`), testler | dil yığını + manifest |

İkiye ayrılmalarının sebebi bu ADR'nin çekirdeği: **`pr-title-ok` her repoda bugün kurulabilir, `ci-ok` kurulamaz.** İkisini tek kapıya bağlamak, kurulabilir olanı kurulamayana rehin verirdi.

### 4 · `tablo_studio`'da `ci-ok` — tarihli istisna

**Bugün eklenmiyor.** Sebep ölçülü, tercih değil:

- Repo'da `requirements.txt` ya da `pyproject.toml` **yok** — runner neyi kuracağını bilemez
- Testler `tablo/mpt_bridge.py` üzerinden MoneyPrinterTurbo'ya bağımlı; MPT bir geliştirici makinesinde duruyor, runner'da yok

Çalışmayan bir test adımını yeşil saymak bu ekipte **üç kez tekrarlamış** bir hatanın dördüncüsü olurdu:

| | Ne yeşil görünüyordu | Gerçekte |
|---|---|---|
| DW-33 | yığılmış PR'da tüm CI | dal filtresi yüzünden CI hiç koşmuyordu |
| DW-48 | yeniden hedeflenen PR'da CI | `edited` tipi eksik, tetiklenmiyordu |
| DW-73 | 25 PR'lık zincir | `ruff format` hiç kontrol edilmiyordu |

Her üçünde de "yeşil tik" ile "kontrol edildi" arasındaki fark, yalnızca birileri ölçtüğü için görüldü.

**İstisnayı kapatacak koşul:** `tablo_studio`'ya (a) bir bağımlılık manifesti ve (b) MPT olmadan koşabilen bir test alt kümesi geldiğinde `ci-ok` zorunlu kontrol olarak eklenir. İş Ömer'de.

### 5 · İnsan onayı merge ön koşulu değil

Üç repoda da `required_pull_request_reviews: null`. Yalnızca `required_approving_review_count: 0` yetmiyor — `CHANGES_REQUESTED` durumu bağımsız olarak merge'i bloke ediyor; şartın tümüyle kaldırılması gerekiyor.

Gerekçe: iki kişilik ekipte karşılıklı onay şartı, 28 PR'lık bir yığında kilitlenmeye dönüştü (DW-70). Review kaldırılmadı — **zorunluluğu** kaldırıldı.

Bunun karşılığında CI pazarlık dışı: `enforce_admins=true`, force-push ve dal silme kapalı.

## Tuzak: workflow'suz zorunlu context kalıcı kilittir

Bir context'i `required_status_checks`'e yazmak, o adı üreten bir workflow `main`'de yoksa **her PR'ı sonsuza kadar bloke eder.** Check hiç bildirilmez, GitHub da "bekleniyor" der ve orada kalır.

Bu hata bu org'da bir kez yapıldı (`tablo_studio`'ya `ci-ok` yazıldı, repo'da hiç workflow yoktu) ve geri alındı.

**Doğru sıra:** workflow'u bir PR ile ekle → kontrollerin o PR üzerinde gerçekten koştuğunu ve yeşile döndüğünü gör → ancak ondan sonra protection'a yaz.

## Sonuçlar

- Yeni bir repo `project-template`'ten türetildiğinde bu politika hazır gelir
- `tablo_studio` PR'ları artık gerçek bir kapıdan geçiyor; `ci-ok` gelene kadar lint/test kapsanmıyor ve bu **bilinerek** böyle
- `MoneyPrinterTurbo` ile `notion-yedek` korumasız kalmaya devam ediyor; ikisi de burada gerekçesiyle yazılı

## Bağlantılar

- Köprü sözleşmesi: [ADR-0011](0011-trend-video-koprusu.md)
- Ajan kuralları tek kaynağı: [ADR-0002](0002-ajan-koordinasyonu.md)
- `tablo_studio` PR: <https://github.com/duo-works/tablo_studio/pull/1>
