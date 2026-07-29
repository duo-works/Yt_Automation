"""YouTube Data API kota muhasebesi.

Kota projenin en sert kısıtı: günlük **10.000 birim** ve tek bir yükleme
1.600 birim. Uçtan uca maliyet video başına 1.651 birim (insert + thumbnail
+ doğrulama), yani tavan **günde 6 video** — altıncıdan sonra 94 birim kalır.
Kota kanal bazında değil **proje bazında** — iki kanal aynı bütçeyi paylaşır.

⚠️ Reddedilen istek de birim harcar. Bu yüzden doğrulama yüklemeden önce
yapılır ve bütçe aşılacaksa istek hiç gönderilmez.

Birim değerleri yıllardır sabit ama Google değiştirebiliyor — PRD bunu
"teyit edilmeli" diye işaretliyor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GUNLUK_BUTCE = 10_000

# Birim maliyetler — https://developers.google.com/youtube/v3/determine_quota_cost
MALIYET = {
    "videos.insert": 1_600,
    "videos.update": 50,
    "thumbnails.set": 50,
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.insert": 50,
}


class KotaAsimi(RuntimeError):
    """İstek gönderilse günlük bütçe aşılacaktı."""


@dataclass
class Sayac:
    """Bir günün kota harcamasını takip eder.

    Kalıcılık bilerek dışarıda: v1 elle tetikleniyor ve tek çalıştırma tek
    oturum. Zamanlanmış çalışmaya geçildiğinde (faz 2) harcama diske veya
    Notion'a yazılmalı, yoksa gün içindeki ikinci çalıştırma sıfırdan sayar.
    """

    butce: int = GUNLUK_BUTCE
    harcanan: int = 0
    kayit: list[tuple[str, int]] = field(default_factory=list)

    @property
    def kalan(self) -> int:
        return self.butce - self.harcanan

    def maliyet(self, islem: str) -> int:
        try:
            return MALIYET[islem]
        except KeyError:
            raise KeyError(
                f"bilinmeyen işlem: {islem!r} — maliyeti kota.MALIYET'e ekleyin"
            ) from None

    def yeter_mi(self, islem: str) -> bool:
        return self.maliyet(islem) <= self.kalan

    def harca(self, islem: str) -> int:
        """İşlemin maliyetini düşer ve kalanı döndürür.

        İstek **gönderilmeden önce** çağrılır — çünkü reddedilen istek de
        birim harcar, yani sonradan saymak gerçeği eksik gösterir.
        """
        tutar = self.maliyet(islem)
        if tutar > self.kalan:
            raise KotaAsimi(
                f"{islem} {tutar} birim istiyor, kalan {self.kalan}. "
                f"Kota Pasifik saatiyle gece yarısı sıfırlanır."
            )
        self.harcanan += tutar
        self.kayit.append((islem, tutar))
        return self.kalan

    def ozet(self) -> str:
        yuzde = round(100 * self.harcanan / self.butce) if self.butce else 0
        return f"{self.harcanan}/{self.butce} birim (%{yuzde}), kalan {self.kalan}"


def video_basina_maliyet(*, thumbnail: bool = True, dogrulama: bool = True) -> int:
    """Tek bir videonun uçtan uca kota maliyeti.

    `dogrulama`, yükleme sonrası `videos.list` ile beyan bayraklarının
    gerçekten yazıldığını kontrol etmeyi kapsar — PRD'nin 5. başarı ölçütü.
    """
    toplam = MALIYET["videos.insert"]
    if thumbnail:
        toplam += MALIYET["thumbnails.set"]
    if dogrulama:
        toplam += MALIYET["videos.list"]
    return toplam
