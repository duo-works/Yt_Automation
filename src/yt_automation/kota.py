"""YouTube Data API kota muhasebesi.

Kota projenin en sert kısıtı: günlük **10.000 birim** ve tek bir yükleme
1.600 birim. Uçtan uca maliyet video başına 1.651 birim (insert + thumbnail
+ doğrulama), yani tavan **günde 6 video** — altıncıdan sonra 94 birim kalır.
Kota kanal bazında değil **proje bazında** — iki kanal aynı bütçeyi paylaşır.

⚠️ Reddedilen istek de birim harcar. Bu yüzden doğrulama yüklemeden önce
yapılır ve bütçe aşılacaksa istek hiç gönderilmez.

Birim değerleri yıllardır sabit ama Google değiştirebiliyor — PRD bunu
"teyit edilmeli" diye işaretliyor.

İki sayaç var. `Sayac` bellekte çalışır: tek çalıştırmalık işler ve kuru
koşum için. `KaliciSayac` harcamayı SQLite'a yazar ve **süreçler arasında**
paylaşılır — yükleme hattı ile trend hattı aynı günlük bütçeden içtiği için
gerçek muhasebe odur.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import depo

GUNLUK_BUTCE = 10_000

# Kota Pasifik saatiyle gece yarısı sıfırlanır — "bugün" bu takvime göre.
# Windows'ta `zoneinfo`nun sistem tz veritabanı yok; `pyproject.toml` bu
# yüzden orada `tzdata` paketini şart koşuyor.
KOTA_BOLGESI = ZoneInfo("America/Los_Angeles")

# Birim maliyetler — https://developers.google.com/youtube/v3/determine_quota_cost
MALIYET = {
    "videos.insert": 1_600,
    "videos.update": 50,
    "thumbnails.set": 50,
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.insert": 50,
    "videoCategories.list": 1,
    "i18nRegions.list": 1,
}


class KotaAsimi(RuntimeError):
    """İstek gönderilse günlük bütçe aşılacaktı."""


def maliyet(islem: str) -> int:
    try:
        return MALIYET[islem]
    except KeyError:
        raise KeyError(f"bilinmeyen işlem: {islem!r} — maliyeti kota.MALIYET'e ekleyin") from None


def kota_gunu(an: datetime | None = None) -> str:
    """Bir anın hangi kota gününe düştüğü (`YYYY-AA-GG`, Pasifik takvimi).

    Sınır UTC gece yarısı **değil**. Örneğin 3 Ocak 05:00 UTC, Pasifik'te
    hâlâ 2 Ocak'tır ve o günün bütçesinden harcar. Bunu karıştırmak günde
    bir kez ya bütçeyi ikiye katlar ya da sekiz saat erken kapatır.
    """
    an = an or datetime.now(UTC)
    return an.astimezone(KOTA_BOLGESI).date().isoformat()


@dataclass
class Sayac:
    """Tek çalıştırmalık kota muhasebesi — bellekte.

    Kuru koşum ve testler için. Gerçek muhasebe `KaliciSayac`'ta: iki süreç
    aynı bütçeden içtiği için bellekteki sayaç ikisinin toplamını göremez.
    """

    butce: int = GUNLUK_BUTCE
    harcanan: int = 0
    kayit: list[tuple[str, int]] = field(default_factory=list)

    @property
    def kalan(self) -> int:
        return self.butce - self.harcanan

    def maliyet(self, islem: str) -> int:
        return maliyet(islem)

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


def _gun_toplami(baglanti: sqlite3.Connection, gun: str, surec: str | None = None) -> int:
    """Bir günün toplam harcaması; `surec` verilirse yalnızca o sürecinki.

    Süreç kırılımı, DW-24'te eklenen `surec` sütununun asıl kazancı: trend
    hattının kendi günlük tavanını bilmesi gerekiyor. Toplam bütçe ortak
    olduğu için "kalan"a bakmak yetmez — trend, yükleme için ayrılmış payı
    yemeden kendi payını bitirmeli.
    """
    if surec is None:
        satir = baglanti.execute(
            "SELECT COALESCE(SUM(birim), 0) AS toplam FROM kota_harcama WHERE gun = ?", (gun,)
        ).fetchone()
    else:
        satir = baglanti.execute(
            "SELECT COALESCE(SUM(birim), 0) AS toplam FROM kota_harcama "
            "WHERE gun = ? AND surec = ?",
            (gun, surec),
        ).fetchone()
    return int(satir["toplam"])


@dataclass
class KaliciSayac:
    """Süreçler arasında paylaşılan kota muhasebesi.

    Harcama SQLite'ta bir **ekle-only defterde** durur; günün toplamı her
    seferinde oradan okunur, bellekte tutulmaz. Sebebi: iki süreç aynı anda
    çalışıyor ve önbelleğe alınmış bir "kalan" değeri anında bayatlıyor.

    `surec` alanı defterde kimin harcadığını işaretler ("yukleme", "trend")
    — bütçe beklenmedik biçimde bittiğinde tek cevap kaynağı bu.
    """

    yol: Path = field(default_factory=depo.varsayilan_yol)
    butce: int = GUNLUK_BUTCE
    surec: str | None = None

    @property
    def gun(self) -> str:
        return kota_gunu()

    @property
    def harcanan(self) -> int:
        baglanti = depo.baglan(self.yol)
        try:
            return _gun_toplami(baglanti, self.gun)
        finally:
            baglanti.close()

    @property
    def surec_harcamasi(self) -> int:
        """Bugün **bu sürecin** harcadığı birim.

        Trend hattı buna bakarak kendi günlük tavanında durur; ortak bütçenin
        kalanına bakmak yeterli değil, çünkü yükleme payını yemeden durmalı.
        """
        baglanti = depo.baglan(self.yol)
        try:
            return _gun_toplami(baglanti, self.gun, self.surec)
        finally:
            baglanti.close()

    @property
    def kalan(self) -> int:
        return self.butce - self.harcanan

    def maliyet(self, islem: str) -> int:
        return maliyet(islem)

    def yeter_mi(self, islem: str, *, rezerve: int = 0) -> bool:
        """Tavsiye niteliğinde — karar anı ile harcama anı arasında yarış var.

        Gerçek kontrol `harca()` içinde, yazma işleminin **içinde** yapılır.
        Burası yalnızca kullanıcıya erkenden bilgi vermek için.
        """
        return self.maliyet(islem) <= self.kalan - rezerve

    def harca(self, islem: str, *, rezerve: int = 0) -> int:
        """Maliyeti deftere yazar ve kalanı döndürür.

        `rezerve`, bu harcamanın dokunamayacağı birim sayısıdır: trend
        toplayıcı buraya bir videoluk yükleme maliyetini geçer, böylece
        araştırma hiçbir koşulda yayını bloke etmez.

        Kontrol ve yazma **tek bir `BEGIN IMMEDIATE` işlemi içinde** olur.
        Ayrılsalardı iki süreç aynı "kalan" değerini okuyup ikisi de
        harcayabilirdi — bütçe sessizce aşılırdı.
        """
        tutar = self.maliyet(islem)  # bilinmeyen işlem: kilit almadan patla
        gun = self.gun
        with depo.yazma_islemi(self.yol) as baglanti:
            kalan = self.butce - _gun_toplami(baglanti, gun)
            if tutar > kalan - rezerve:
                rezerve_notu = f", {rezerve} birim rezerve" if rezerve else ""
                raise KotaAsimi(
                    f"{islem} {tutar} birim istiyor, kalan {kalan}{rezerve_notu}. "
                    f"Kota Pasifik saatiyle gece yarısı sıfırlanır ({gun} günü sayılıyor)."
                )
            baglanti.execute(
                "INSERT INTO kota_harcama (gun, an, islem, birim, surec) VALUES (?, ?, ?, ?, ?)",
                (gun, datetime.now(UTC).isoformat(), islem, tutar, self.surec),
            )
        return kalan - tutar

    def ozet(self) -> str:
        harcanan = self.harcanan
        yuzde = round(100 * harcanan / self.butce) if self.butce else 0
        return (
            f"{harcanan}/{self.butce} birim (%{yuzde}), "
            f"kalan {self.butce - harcanan} — {self.gun} (Pasifik)"
        )


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
