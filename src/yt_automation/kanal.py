"""Kanal profilleri — kategoriye özel her değer burada toplanır.

Yükleme hattı kategoriden bağımsız kalacak. Bunu sağlamanın yolu bir soyutlama
katmanı değil, **tek bir yer**: kategoriye göre değişen ne varsa bu dosyada
durur, koda serpilmez. İkinci kanal geldiğinde buraya bir satır eklenir.

⚠️ **Kanal ID'si burada YOK ve gerekmiyor.** `videos.insert` videoyu
yetkilendirilmiş hesabın kanalına yüklüyor; hangi kanala gideceğini OAuth
belirliyor, bu profil değil. Buradaki `kimlik` yalnızca bir CLI argümanı ve
klasör adı. Yanlış kanala yükleme riski varsa çözümü buraya bir ID eklemek
değil, doğru hesapla yetkilendirmektir.

## Strateji geçmişi

Bu dosya "önce çocuk kanalı, sonra eğitim" planına göre yazılmıştı. O plan iki
kez değişti:

- **2026-08-03** — çocuk (MFK) + eğitim ayrımı rafa kalktı; yerine format bazlı
  iki kanal (uzun + Shorts) geldi.
- **2026-08-05** — çocuk içeriği tamamen bırakıldı ve `cocuk` profili silindi.
  Sadece rafa kaldırmak yetmezdi: profil CLI'da iki komutun **varsayılanıydı**,
  yani argüman verilmeyen bir yükleme `selfDeclaredMadeForKids=True` ile
  giderdi. Aşağıdaki alanın kendi uyarısı bunun bedelini yazıyor.

⚠️ **Bugün kayıtlı tek kanal bir DENEME kanalı.** Üretim kanalları (uzun +
Shorts) henüz açılmadı. `muezza` hattı uçtan uca sınamak için var: 1 abone,
3 video. Buradaki sayılar ve strateji bir deneyin parametreleri, kanıtlanmış
bir düzen değil — üretim kanalı açıldığında bu profil kopyalanmamalı, kendi
ölçümüyle yeniden kurulmalı.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Kanal:
    """Bir YouTube kanalının değişmez profili."""

    kimlik: str
    """Kısa anahtar — klasör adı ve CLI argümanı olarak kullanılır."""

    ad: str

    cocuk_icerigi: bool
    """`status.selfDeclaredMadeForKids` alanına gider.

    ⚠️ Yanlış işaretleme FTC yaptırımına giriyor (ihlal başına $53.088).
    Kanal seviyesinde de bir ayar var ve video bazındaki bu değer onu ezer;
    ikisinin aynı olduğundan emin olun.
    """

    varsayilan_etiketler: tuple[str, ...] = field(default_factory=tuple)
    """Her videoya eklenen etiketler. Video kendi etiketlerini de ekler."""

    varsayilan_dil: str = "tr"

    youtube_kanal_id: str | None = None
    """Beklenen YouTube kanal kimliği (`UC…`) — **yönlendirme değil, doğrulama.**

    `videos.insert` videoyu zaten token'ın bağlı olduğu kanala yüklüyor; bu alan
    onu değiştirmiyor. İşi, yüklemeden önce "gerçekten doğru kanalda mıyız"
    sorusunu sorulabilir kılmak.

    ⚠️ Ölçüldü (2026-08-05): ilk yetkilendirmede token beklenen kanal yerine
    kişisel bir kanala bağlandı — kullanıcı kendi Google hesabıyla giriş yaptı,
    Google da doğal olarak onun kanalını seçti. Kod bunu göremedi çünkü hangi
    kanalda olduğunu hiç sormuyordu. Elle bir `channels.list?mine=true` çağrısı
    yakaladı.

    DW-81'de "kanal ID'si gerekmiyor" diye yazılmıştı; yükleme açısından doğru
    ama madalyonun diğer yüzü kaçırılmıştı. Yanlış kanala giden videoyu geri
    almak YouTube tarafında elle iş.

    `None` ise doğrulama **atlanır ve uyarılır** — profil ID'siz de kullanılsın
    diye, ama sessizce değil.
    """

    def __post_init__(self) -> None:
        if not self.kimlik:
            raise ValueError("kanal kimliği boş olamaz")


# Kayıtlı kanallar. Üretim kanalları (uzun + Shorts) açıldığında buraya eklenir.
KANALLAR: dict[str, Kanal] = {
    "deneme": Kanal(
        kimlik="deneme",
        ad="Mirza Sarıbıyık (kişisel — hat provası)",
        # Kanalda çocuklara yönelik içerik yok. Bu alan `selfDeclaredMadeForKids`
        # olarak gidiyor; yanlış işaretlemenin bedeli yukarıda yazılı.
        cocuk_icerigi=False,
        # İngilizce Shorts — MoneyPrinterTurbo `CHANNEL_ANALYSIS.md`: 35-50
        # saniye, 80-120 İngilizce kelime. Varsayılan `tr` olsaydı her videoya
        # yanlış `defaultLanguage` giderdi.
        varsayilan_dil="en",
        varsayilan_etiketler=("history", "shorts"),
        # `channels.list?mine=true` ile ölçüldü (2026-08-05): token bu kanala
        # bağlı. 0 abone, 0 video — yani hat provası burada yapılıyor.
        youtube_kanal_id="UCcwguAj4haJDAEHOUixHrSA",
    ),
}

# ⚠️ `muezza` profili BİLEREK yok. Kanal Ömer'de ve token onunla değil kişisel
# hesapla alındı; ID'si hiç ölçülmedi. ID'siz bir `muezza` profili eklemek,
# doğrulamayı sessizce atlayan bir profil eklemek olurdu — DW-83'ün kapattığı
# kusurun aynısı. muezza'ya yükleme yapılacaksa önce o hesapla yetkilendirilip
# kanal ID'si ölçülmeli, sonra profil eklenmeli.


def getir(kimlik: str) -> Kanal:
    """Kanal profilini getirir; tanınmayan kimlikte anlaşılır hata verir."""
    try:
        return KANALLAR[kimlik]
    except KeyError:
        tanimli = ", ".join(sorted(KANALLAR)) or "(hiç kanal tanımlı değil)"
        raise KeyError(f"bilinmeyen kanal: {kimlik!r} — tanımlı olanlar: {tanimli}") from None
