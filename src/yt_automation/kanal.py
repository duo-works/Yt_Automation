"""Kanal profilleri — kategoriye özel her değer burada toplanır.

Yükleme hattı kategoriden bağımsız kalacak. Bunu sağlamanın yolu bir soyutlama
katmanı değil, **tek bir yer**: kategoriye göre değişen ne varsa bu dosyada
durur, koda serpilmez. İkinci kanal geldiğinde buraya bir satır eklenir.

⚠️ **Kanal ID'si yönlendirmez, DOĞRULAR.** `videos.insert` videoyu zaten
token'ın bağlı olduğu kanala yüklüyor; hangi kanala gideceğini OAuth belirliyor,
bu profil değil. Ama ID olmadan "doğru kanalda mıyız" sorusu sorulamıyor —
DW-83 bunu ölçtü ve `youtube_kanal_id` o yüzden var. Buradaki `kimlik` ise
yalnızca bir CLI argümanı ve klasör adı.

## Strateji geçmişi

Bu dosya "önce çocuk kanalı, sonra eğitim" planına göre yazılmıştı. O plan iki
kez değişti:

- **2026-08-03** — çocuk (MFK) + eğitim ayrımı rafa kalktı; yerine format bazlı
  iki kanal (uzun + Shorts) geldi.
- **2026-08-05** — çocuk içeriği tamamen bırakıldı ve `cocuk` profili silindi.
  Sadece rafa kaldırmak yetmezdi: profil CLI'da iki komutun **varsayılanıydı**,
  yani argüman verilmeyen bir yükleme `selfDeclaredMadeForKids=True` ile
  giderdi. Aşağıdaki alanın kendi uyarısı bunun bedelini yazıyor.

⚠️ **Kayıtlı tek kanal `Shemz`** (2026-08-05'te açıldı, 0 abone / 0 video).
İkinci kanal (uzun video) henüz açılmadı. Buradaki `varsayilan_dil` ve
etiketler MoneyPrinterTurbo `CHANNEL_ANALYSIS.md`'deki Shorts stratejisinden
geliyor; o ölçümler BAŞKA bir kanalda (muezza, 3 video) yapıldı, yani
kanıtlanmış değil devralınmış varsayımlar. Shemz kendi verisini üretince
gözden geçirilmeli.
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
    "shemz": Kanal(
        kimlik="shemz",
        ad="Shemz",
        # Kanalda çocuklara yönelik içerik yok. Bu alan `selfDeclaredMadeForKids`
        # olarak gidiyor; yanlış işaretlemenin bedeli yukarıda yazılı.
        cocuk_icerigi=False,
        # İngilizce Shorts — MoneyPrinterTurbo `CHANNEL_ANALYSIS.md`: 35-50
        # saniye, 80-120 İngilizce kelime. Varsayılan `tr` olsaydı her videoya
        # yanlış `defaultLanguage` giderdi.
        varsayilan_dil="en",
        varsayilan_etiketler=("history", "shorts"),
        # `channels.list?mine=true` ile ölçüldü (2026-08-05): token bu kanala
        # bağlı. 0 abone, 0 video — yayın hattı buraya kuruluyor.
        youtube_kanal_id="UC9pRuiA5I7KOCjYP_cjfl2g",
    ),
}

# ⚠️ Yeni profil eklemeden önce kanal ID'si ÖLÇÜLMELİ:
# `channels.list?mine=true` ile o hesapta yetkilendirilip kimlik alınır. ID'siz
# profil, doğrulamayı sessizce atlayan profildir — DW-83'ün kapattığı kusurun
# aynısı. `test_her_kayitli_kanalin_dogrulanabilir_kimligi_var` bunu kilitliyor.


def getir(kimlik: str) -> Kanal:
    """Kanal profilini getirir; tanınmayan kimlikte anlaşılır hata verir."""
    try:
        return KANALLAR[kimlik]
    except KeyError:
        tanimli = ", ".join(sorted(KANALLAR)) or "(hiç kanal tanımlı değil)"
        raise KeyError(f"bilinmeyen kanal: {kimlik!r} — tanımlı olanlar: {tanimli}") from None
