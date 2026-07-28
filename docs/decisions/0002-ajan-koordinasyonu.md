# 0002 — Ajan koordinasyonu Notion Oturum Kaydı üzerinden yapılır

- **Durum:** Kabul
- **Tarih:** 2026-07-25
- **Karar verenler:** Mirza Sarıbıyık
- **İlgili görev:** DW-11

## Bağlam

İki kişilik ekibin **her iki üyesi de kendi AI ajanıyla** (Claude Code, Codex) aynı repo üzerinde çalışıyor. Mevcut koordinasyon mekanizması yalnızca görev seviyesinde: `CONTRIBUTING.md` §6 "bir görev aynı anda tek kişide olur" diyor ve gerisini Notion görev durumuna bırakıyor.

Bu, insan hızında çalışırken yeterliydi. Ajanlarla üç boşluk açıldı:

1. **Görünürlük yok.** Bir ajan, diğer kişinin ajanının o an hangi dosyalara dokunduğunu bilemiyor. Görev durumu "Yapılıyor" demek, hangi dosyaların risk altında olduğunu söylemiyor.
2. **Oturum hafızası yok.** Bir oturum bittiğinde ne yapıldığı ve neyin yarım kaldığı hiçbir yere yazılmıyor. Sonraki oturum — kendi ajanınız veya arkadaşınızın ajanı — sıfırdan başlıyor.
3. **Codex kuralsız çalışıyor.** Repo'da yalnızca `CLAUDE.md` vardı. Codex bu dosyayı okumaz; dolayısıyla branch adı, DW-ID zorunluluğu ve sır politikası Codex için fiilen mevcut değildi.

ADR-0001 "görev takibinin tek kaynağı Notion" derken otomasyon yerine konvansiyonu seçmişti. Bu karar aynı çizgiyi izler.

## Değerlendirilen seçenekler

1. **Repo içinde handoff dizini** (`docs/handoff/*.md`) — Git ile senkron, ekstra servis yok. Ancak: handoff dosyalarının kendisi merge conflict üretir (çakışmayı önlemek için kurulan sistem çakışma kaynağı olur), yalnızca push sonrası görünür olur (eşzamanlı çalışmada işe yaramaz) ve `CONTRIBUTING.md` §1'in "uzun form Notion'a gider" kuralını deler.
2. **Notion'da tek `📓 Oturum Kaydı` database'i** — Her iki ajanın da MCP bağlantısı var, anlık okunur/yazılır, merge conflict üretmez, insanlar için de okunabilir. Bedeli: Notion MCP bağlantısına bağımlılık.
3. **Üç ayrı database** (günlük / proje notu / devir) — Kavramsal olarak daha net, ama ajanın üç yere yazması gerekir; unutma yüzeyi üçe katlanır ve okuma maliyeti artar.
4. **CI zorlaması** — PR'da oturum kaydı linki yoksa build kırmızı. Gerçek garanti sağlar ama yanlış pozitif üretir ve PR akışını yavaşlatır.

## Karar

**Seçenek 2.** Notion'da tek bir `📓 Oturum Kaydı` database'i kurulur; günlük kayıt, devir notu ve "şu an kim neye dokunuyor" bildirimi aynı tabloda `Tür` ve `Durum` alanlarıyla ayrışır. Ayrı bir kilit tablosuna gerek yoktur: `Durum = "Devam ediyor"` olan satırlar zaten kilit tablosudur ve `🔴 Aktif` görünümü bunu gösterir.

Ajan kuralları `AGENTS.md` içinde **tek kaynak** olarak toplanır; `CLAUDE.md` bu dosyaya yönlendiren kısa bir işaretçiye indirgenir. İki ajan dosyasının zamanla birbirinden sapması, çözmeye çalıştığımız problemin ta kendisi olurdu.

Zorlama tarafında dokümantasyon + Claude `SessionStart` / `Stop` hook'ları seçildi; CI kontrolü (seçenek 4) bilinçli olarak kapsam dışı bırakıldı.

## Sonuçlar

**Kolaylaştırdıkları:** İki ajan birbirinin aktif çalışma alanını görebiliyor. Yarım kalan iş `Devredildi` kaydıyla sonraki oturuma taşınıyor. Codex artık `AGENTS.md` üzerinden aynı kural setine tabi.

**Zorlaştırdıkları ve kabul edilen kısıtlar:**

- **Notion MCP bağımlılığı.** Bir tarafta bağlantı yoksa sistem tek taraflı çalışır ve yanlış güven duygusu yaratır — "aktif kayıt yok" ile "kayıt açamayan bir ajan çalışıyor" ayırt edilemez. `AGENTS.md` bu durumda ajanın kullanıcıyı uyarmasını şart koşar.
- **`Dokunulan alanlar` teknik bir kilit değil, bir bildirimdir.** Zorlayıcı kilit git'te zaten yok; asıl çözüm yeri görev bölmesidir (`CONTRIBUTING.md` §6).
- **Hook'lar Notion'u kendileri çağıramaz.** MCP'ye erişimleri yok; doğrudan API çağrısı Notion token'ı gerektirir ve bu, sır yönetimi kuralını (`CONTRIBUTING.md` §8) ihlal ederdi. Hook yalnızca ajana metin enjekte eder — sorguyu ajan yapar. Codex tarafında hook karşılığı yoktur; orada garanti `AGENTS.md` disiplinindedir.
- **`CLAUDE.md` artık bir ekstra okuma gerektiriyor.** Claude Code `CLAUDE.md`'yi otomatik yükler ama `AGENTS.md`'yi Read ile okur. Sapma riskini sıfırlamak için ödenen bedel budur.
- **Notion tek bir hesap üzerinden ortak kullanılıyor.** Workspace bir edu hesabında kuruldu ve mevcut paket ikinci bir *member* eklemeye izin vermiyor. Guest denendi ve yetmedi: guest hesaplar sayfaları görebiliyor ama **Notion MCP'ye hiç bağlanamıyor.** Bu, sayfa izinlerinden ayrı bir kapı — yani ikinci kişinin ajanı protokolü hiç uygulayamıyordu. Çözüm olarak iki geliştirici de aynı hesabı kullanıyor.

  Bunun bedeli **atıf kaybı:** Notion artık o an kimin çalıştığını bilmiyor. Kimlik `git config user.name`'den okunur (`AGENTS.md` → *Oturum BAŞINDA* 1. adım) ve `Kişi` alanı bu yüzden `person` değil `select` tipindedir — kişi başına ayrı *depolama* değil, ayrı *görünüm* üretir. Kişi başına ayrı sayfa tutmak reddedildi: tek sorgu garantisini bozar, çoklu data source SQL'i Enterprise gerektirir ve her sayfaya ayrı kanarya (ADR-0003) koymak gerekirdi.

  Ortak hesabın ikinci bedeli **tek arıza noktası:** hesap askıya alınırsa PRD, görevler, kararlar ve oturum geçmişi hep birden gider. Karşılığı aylık workspace dökümüdür (`notion-yedek/`) — tam bir geri yükleme aracı değil, felaket yedeği.

  `AGENTS.md` kural 8 (tüm yeni Notion içeriği `duo-works` hub'ı altında oluşturulur) korunuyor; gerekçesi artık guest görünürlüğü değil, ağacın dağılmaması ve dökümün eksiksiz olması.
