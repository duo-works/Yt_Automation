"""Kanal profilleri — kategoriye özel her değer burada toplanır.

PRD kararı: iki kanal olacak (önce çocuk, sonra eğitim/tarih/bilim) ve
yükleme hattı kategoriden bağımsız kalacak. Bunu sağlamanın yolu bir
soyutlama katmanı değil, **tek bir yer**: kategoriye göre değişen ne varsa
bu dosyada durur, koda serpilmez.

İkinci kanal geldiğinde buraya bir satır eklenir. Gerçekten neyin değiştiği
o zaman görülür ve gerekiyorsa soyutlama o noktada çıkarılır — tahminle değil.
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

    def __post_init__(self) -> None:
        if not self.kimlik:
            raise ValueError("kanal kimliği boş olamaz")


# Kayıtlı kanallar. İkinci kanal (eğitim/tarih/bilim) v1 çalıştıktan sonra eklenir.
KANALLAR: dict[str, Kanal] = {
    "cocuk": Kanal(
        kimlik="cocuk",
        ad="Çocuk içeriği",
        cocuk_icerigi=True,
        varsayilan_etiketler=("çocuk", "çizgi film"),
    ),
}


def getir(kimlik: str) -> Kanal:
    """Kanal profilini getirir; tanınmayan kimlikte anlaşılır hata verir."""
    try:
        return KANALLAR[kimlik]
    except KeyError:
        tanimli = ", ".join(sorted(KANALLAR)) or "(hiç kanal tanımlı değil)"
        raise KeyError(f"bilinmeyen kanal: {kimlik!r} — tanımlı olanlar: {tanimli}") from None
