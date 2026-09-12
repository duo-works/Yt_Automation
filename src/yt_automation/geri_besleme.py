"""Yayınlanan videoların gerçek performansını huniye geri besler.

NEDEN VAR
---------
Huni bugüne kadar **kapalı devre çalışıyordu**: konu seçiyor, video
üretiliyor, yayınlanıyor — ve sonuç hiçbir yere dönmüyordu. Bütün eşikler
(``ESIK_KALIBRE``, ``ASGARI_TALEP``, skor ağırlıkları) dağılımdan seçilmişti,
gerçek video sonucundan değil. ``bosluk.py`` bunu zaten itiraf ediyor:
"henüz tek video yayınlanmadı".

Artık yayınlandı. Bu modül halkayı kapatıyor: Notion'daki aday (ne tahmin
ettik) ile YouTube'daki video (ne oldu) eşleştirilip karşılaştırılıyor.

İLK ÖLÇÜM (2026-08-12, 4 aday — kanalın ilk üç günü):

    konu                     TALEP    skor   İZLENME
    William Hardham          33862    2.66        31
    Tycho Brahe               5815   -1.03       106
    Second Anglo-Dutch War    2598   -0.09         0   (private)
    Friedrich Hayek           2305   -2.26         3

⚠️ BU TABLOYU İLK OKUYUŞUM YANLIŞTI, kayda geçiyor. En yüksek talepli
adayın (33.862) en az izlenenlerden biri olmasına bakıp "sinyal ters
çalışıyor" demiştim. Sıralama korelasyonu hesaplanınca çıkan sonuç bunun
tersi: **+0,6**. İki uç noktaya bakıp genelleme yapmak, ölçüm yerine
örüntü uydurmaktı — bu modülün var oluş sebebi tam da bunu önlemek.

Doğru ifade: **huninin öngörüsü henüz doğrulanmadı** — ne doğrulandı ne
çürütüldü. n=4, kanal 1 aboneli ve 3 günlük. Modülün işi karar vermek
değil, ölçümü görünür kılmak; karar örneklem büyüdükçe kanal sahibinin.

⚠️ KARIŞTIRICI DEĞİŞKENLER — ölçüme bakarken hatırlanması gereken:
  * Kanal 3 günlük ve 1 aboneli; YouTube henüz dağıtım sinyali biriktirmedi.
    Bu yaşta izlenme farkları konu kalitesinden çok algoritmanın rastgele
    test trafiğini yansıtabilir.
  * Başlık formatı konu seçiminden bağımsız bir değişken: soru formatlı iki
    başlık (416, 546) düz isim formatlı ikisinden (3, 3) çok daha iyi aldı.
    Konu sinyalini suçlamadan önce bu ayrıştırılmalı.
  * Yayın saati de sabit değil.

Yani "huni bozuk" sonucu bu veriden **çıkarılamaz**; çıkarılabilecek olan
"huninin öngörüsü henüz doğrulanmadı, aksine ters yönde bir işaret var".

KAPSAM
------
Bu modül **yalnızca okur ve raporlar**. Notion'a yazmıyor, eşik
değiştirmiyor. Otomatik kalibrasyon, ölçüm birikmeden yapılırsa gürültüye
tepki vermek olur.
"""

from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass, field
from typing import Any

import requests

from yt_automation.trend import notion

YOUTUBE_VIDEO_UCU = "https://www.googleapis.com/youtube/v3/videos"

# Notion'da üretimi tamamlanmış adayın durumu.
URETILDI_DURUMU = "Üretildi"

# YouTube video kimliği hem `shorts/<id>` hem `watch?v=<id>` biçiminde
# geliyor — ikisi de aynı hatta üretildi, biçim farkı yükleme yolundan.
_KIMLIK_KALIBI = re.compile(r"(?:shorts/|v=|youtu\.be/)([\w-]{11})")

# Tek istekte sorulabilecek video sayısı (Data API sınırı).
_YIGIN = 50


class GeriBeslemeHatasi(RuntimeError):
    """Ölçüm yapılamadı — anahtar yok, ağ düştü ya da yanıt beklenmedik."""


def video_kimligi(url: str) -> str | None:
    """Video URL'sinden 11 karakterlik kimliği çıkarır.

    Kimlik çıkmazsa ``None`` — çağıran taraf bunu "eşleşmedi" sayar, hata
    değil: adayda elle girilmiş bozuk bir bağlantı olabilir ve bu tek satır
    yüzünden bütün ölçüm durmamalı.
    """
    if not url:
        return None
    eslesme = _KIMLIK_KALIBI.search(url)
    return eslesme.group(1) if eslesme else None


@dataclass(frozen=True)
class Olcum:
    """Bir adayın tahmini ile gerçekleşen sonucunun yan yana hâli."""

    baslik: str
    video_kimligi: str
    video_url: str
    # Huninin TAHMİNİ
    talep: float | None
    bosluk_skoru: float | None
    sinif: str | None
    kaynak: str | None
    # GERÇEKLEŞEN
    izlenme: int
    begeni: int
    yorum: int
    yayin_tarihi: str
    video_basligi: str

    @property
    def etkilesim_orani(self) -> float:
        return (self.begeni + self.yorum) / self.izlenme if self.izlenme else 0.0

    def sozluk(self) -> dict[str, Any]:
        return {
            "baslik": self.baslik,
            "video_kimligi": self.video_kimligi,
            "video_url": self.video_url,
            "talep": self.talep,
            "bosluk_skoru": self.bosluk_skoru,
            "sinif": self.sinif,
            "kaynak": self.kaynak,
            "izlenme": self.izlenme,
            "begeni": self.begeni,
            "yorum": self.yorum,
            "etkilesim_orani": self.etkilesim_orani,
            "yayin_tarihi": self.yayin_tarihi,
            "video_basligi": self.video_basligi,
        }


@dataclass
class Rapor:
    """Ölçümler + yorumlanabilirlik uyarıları."""

    olcumler: list[Olcum] = field(default_factory=list)
    eslesmeyen: list[str] = field(default_factory=list)

    @property
    def guven(self) -> str:
        """Örneklem bu sonucu ne kadar taşıyor?

        Eşikler bilinçli olarak yüksek: n=4'te "orta" demek, olmayan bir
        kesinliği ima etmek olurdu.
        """
        n = len(self.olcumler)
        if n < 8:
            return "yok"
        if n < 25:
            return "zayif"
        return "orta"

    def sirala(self) -> list[Olcum]:
        return sorted(self.olcumler, key=lambda o: o.izlenme, reverse=True)

    def talep_izlenme_uyumu(self) -> float | None:
        """Talep sıralaması ile izlenme sıralaması arasındaki Spearman katsayısı.

        ⚠️ Pearson değil Spearman: ölçekler karşılaştırılamaz (Wikipedia
        okunması binler, izlenme onlar) ve ilişkinin doğrusal olması için
        hiçbir sebep yok. Sorulan soru "talep iki katına çıkınca izlenme ne
        olur" değil, **"daha talepli konu daha çok mu izlendi"**.

        En az 3 ölçüm ister; altında ``None`` döner çünkü iki noktadan geçen
        her sıralama mükemmel uyumlu görünür.
        """
        uygun = [o for o in self.olcumler if o.talep is not None]
        if len(uygun) < 3:
            return None
        talepler = [float(o.talep) for o in uygun]
        izlenmeler = [float(o.izlenme) for o in uygun]
        # Sabit dizide sıralama korelasyonu tanımsız (varyans sıfır).
        if len(set(talepler)) < 2 or len(set(izlenmeler)) < 2:
            return None
        return statistics.correlation(_sira(talepler), _sira(izlenmeler), method="linear")

    def ozet(self) -> dict[str, Any]:
        izlenmeler = [o.izlenme for o in self.olcumler]
        return {
            "olculen_video": len(self.olcumler),
            "eslesmeyen_aday": len(self.eslesmeyen),
            "guven": self.guven,
            "toplam_izlenme": sum(izlenmeler),
            "ortanca_izlenme": statistics.median(izlenmeler) if izlenmeler else 0,
            "talep_izlenme_uyumu": self.talep_izlenme_uyumu(),
            "olcumler": [o.sozluk() for o in self.sirala()],
        }


def _sira(degerler: list[float]) -> list[float]:
    """Sıralama numaraları; beraberlikte ortalama sıra (Spearman'ın istediği)."""
    sirali = sorted(range(len(degerler)), key=lambda i: degerler[i])
    siralar = [0.0] * len(degerler)
    i = 0
    while i < len(sirali):
        j = i
        while j + 1 < len(sirali) and degerler[sirali[j + 1]] == degerler[sirali[i]]:
            j += 1
        ortalama = (i + j) / 2 + 1
        for k in range(i, j + 1):
            siralar[sirali[k]] = ortalama
        i = j + 1
    return siralar


def _anahtar() -> str:
    deger = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not deger:
        raise GeriBeslemeHatasi("YOUTUBE_API_KEY tanımlı değil — .env dosyanızda ayarlayın.")
    return deger


def video_istatistikleri(
    kimlikler: list[str], *, anahtar: str | None = None
) -> dict[str, dict[str, Any]]:
    """Video kimliklerinin herkese açık istatistiklerini getirir.

    ⚠️ Data API anahtarı yeterli, OAuth gerekmiyor: yalnızca **herkese açık**
    sayılar okunuyor. Analytics (izlenme süresi, tutma, trafik kaynağı) OAuth
    ister ve ayrı bir kapsamdır — o iş DW-25'te, PR #12'de duruyor.

    ⚠️ Private/unlisted videolar burada BOŞ döner. Hattın videoları private
    yükleniyor (kanal sahibinin kararı), yani ölçüm yalnızca public'e
    çekilmiş videoları görebilir. Eksik gelmesi hata değil.
    """
    if not kimlikler:
        return {}
    anahtar = anahtar or _anahtar()
    sonuc: dict[str, dict[str, Any]] = {}
    for baslangic in range(0, len(kimlikler), _YIGIN):
        yigin = kimlikler[baslangic : baslangic + _YIGIN]
        try:
            yanit = requests.get(
                YOUTUBE_VIDEO_UCU,
                params={
                    "part": "snippet,statistics",
                    "id": ",".join(yigin),
                    "key": anahtar,
                },
                timeout=30,
            )
            yanit.raise_for_status()
        except requests.RequestException as hata:
            raise GeriBeslemeHatasi(f"YouTube isteği başarısız: {hata}") from hata
        for oge in yanit.json().get("items", []):
            sonuc[oge["id"]] = oge
    return sonuc


def _tam_sayi(deger: Any) -> int:
    try:
        return int(deger or 0)
    except (TypeError, ValueError):
        return 0


def olc(*, token: str | None = None, anahtar: str | None = None) -> Rapor:
    """`Üretildi` adaylarını gerçek YouTube sonuçlarıyla eşleştirir."""
    token = token or notion.token_al()
    adaylar = notion.adaylari_getir(token=token, durum=URETILDI_DURUMU, adet=notion.SAYFA_SINIRI)

    kimlik_haritasi: dict[str, Any] = {}
    eslesmeyen: list[str] = []
    for aday in adaylar:
        # ⚠️ `video_url`, `baglanti` DEĞİL: `baglanti` konunun kaynağı
        # (Wikipedia makalesi). İlk yazımda `baglanti` okunuyordu ve dört
        # adayın dördü de "eşleşmedi" sayıldı — hata vermeden, boş rapor
        # üreterek. Sessiz sıfır, bozuk ölçümün en tehlikeli hâli.
        kimlik = video_kimligi(aday.video_url or "")
        if kimlik is None:
            eslesmeyen.append(aday.baslik)
            continue
        kimlik_haritasi[kimlik] = aday

    istatistikler = video_istatistikleri(list(kimlik_haritasi), anahtar=anahtar)

    olcumler: list[Olcum] = []
    for kimlik, aday in kimlik_haritasi.items():
        video = istatistikler.get(kimlik)
        if video is None:
            # Private/silinmiş video ya da yanlış kimlik — ölçülemez.
            eslesmeyen.append(aday.baslik)
            continue
        istatistik = video.get("statistics", {})
        snippet = video.get("snippet", {})
        olcumler.append(
            Olcum(
                baslik=aday.baslik,
                video_kimligi=kimlik,
                video_url=aday.video_url or "",
                talep=aday.talep,
                bosluk_skoru=aday.bosluk_skoru,
                sinif=aday.sinif,
                kaynak=None,
                izlenme=_tam_sayi(istatistik.get("viewCount")),
                begeni=_tam_sayi(istatistik.get("likeCount")),
                yorum=_tam_sayi(istatistik.get("commentCount")),
                yayin_tarihi=snippet.get("publishedAt", ""),
                video_basligi=snippet.get("title", ""),
            )
        )

    return Rapor(olcumler=olcumler, eslesmeyen=eslesmeyen)
