"""`chart=mostPopular` toplayıcısı.

Tek çağrı = 1 kota birimi, 50 video. Sayfalama **yok**: her ek sayfa bir birim
daha ve öngörülebilir maliyet, marjinal recall'dan değerli. Bölge başına
`bolge.LISTELER` kadar çağrı yapılır.

API istemcisi dışarıdan geçirilir — testler sahte istemci verir, CI canlı
çağrı yapmaz.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import depo, kota
from . import bolge

ISLEM = "videos.list"

# `HttpError` mesajı çağrılan URL'in tamamını taşıyor ve URL'de `key=<anahtar>`
# var. Bu mesaj hem stderr'e basılıyor hem `kosu.hata` sütununa yazılıyor —
# yani temizlenmezse API anahtarı düz metin olarak diske düşer. Bu, ilk canlı
# koşumda fiilen gerçekleşti.
_ANAHTAR_DESENI = re.compile(r"(key=)[A-Za-z0-9_\-]+")


def gizle(metin: str) -> str:
    """Hata metnindeki API anahtarını maskeler."""
    return _ANAHTAR_DESENI.sub(r"\1<gizlendi>", metin)


@dataclass
class KosuSonucu:
    an: str
    tur: str
    bolge_sayisi: int = 0
    cagri_sayisi: int = 0
    harcanan_kota: int = 0
    video_sayisi: int = 0
    hatalar: list[str] = field(default_factory=list)
    kota_bitti: bool = False

    def ozet(self) -> str:
        satir = (
            f"{self.tur} tarama · {self.bolge_sayisi} bölge · {self.cagri_sayisi} çağrı · "
            f"{self.harcanan_kota} birim · {self.video_sayisi} ölçüm"
        )
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        if self.kota_bitti:
            satir += " · KOTA TAVANINDA DURDU"
        return satir


def _sure_saniye(iso_sure: str | None) -> int | None:
    """ISO 8601 süresini (`PT4M13S`) saniyeye çevirir.

    `contentDetails.duration` bu biçimde geliyor. Canlı yayınlarda `P0D`
    olabiliyor; o durumda 0 döner ve bilgi kaybı olmaz.
    """
    if not iso_sure or not iso_sure.startswith("P"):
        return None
    govde = iso_sure[1:]
    gun, _, zaman = govde.partition("T")
    toplam = 0
    for metin, birimler in ((gun, {"D": 86_400}), (zaman, {"H": 3_600, "M": 60, "S": 1})):
        sayi = ""
        for karakter in metin:
            if karakter.isdigit():
                sayi += karakter
            elif karakter in birimler:
                toplam += int(sayi or 0) * birimler[karakter]
                sayi = ""
            else:
                sayi = ""
    return toplam


def _tam_sayi(deger) -> int | None:
    """`statistics` alanları metin gelir ve gizli videolarda hiç gelmez."""
    try:
        return int(deger)
    except (TypeError, ValueError):
        return None


def _videoyu_yaz(baglanti, oge: dict, simdi: str) -> str:
    snippet = oge.get("snippet") or {}
    icerik = oge.get("contentDetails") or {}
    konu = (oge.get("topicDetails") or {}).get("topicCategories") or []

    video_id = oge["id"]
    kategori = _tam_sayi(snippet.get("categoryId"))

    # Başlık ve istatistik değişebiliyor; sabit alanlar ilk görülmede yazılır.
    # `ilk_gorulme` bilerek korunuyor — videonun yaşını ondan değil
    # `yayin_zamani`'ndan hesaplayacağız ama ikisinin farkı da bilgi.
    baglanti.execute(
        """
        INSERT INTO video (
            video_id, baslik, kanal_id, kanal_adi, yayin_zamani,
            kategori_id, sure_sn, konu_etiketleri, ilk_gorulme
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            baslik      = excluded.baslik,
            kanal_adi   = excluded.kanal_adi,
            kategori_id = COALESCE(excluded.kategori_id, video.kategori_id)
        """,
        (
            video_id,
            snippet.get("title") or "(başlıksız)",
            snippet.get("channelId"),
            snippet.get("channelTitle"),
            snippet.get("publishedAt"),
            kategori,
            _sure_saniye(icerik.get("duration")),
            json.dumps(konu, ensure_ascii=False) if konu else None,
            simdi,
        ),
    )
    return video_id


def _olcumu_yaz(baglanti, video_id: str, *, bolge_kodu: str, an: str, liste: int, sira: int, oge):
    istatistik = oge.get("statistics") or {}
    baglanti.execute(
        """
        INSERT INTO olcum (video_id, bolge, an, liste_kategori, sira, izlenme, begeni, yorum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id, bolge, an) DO UPDATE SET
            sira           = MIN(olcum.sira, excluded.sira),
            liste_kategori = CASE
                WHEN excluded.sira < olcum.sira THEN excluded.liste_kategori
                ELSE olcum.liste_kategori
            END
        """,
        (
            video_id,
            bolge_kodu,
            an,
            liste,
            sira,
            _tam_sayi(istatistik.get("viewCount")),
            _tam_sayi(istatistik.get("likeCount")),
            _tam_sayi(istatistik.get("commentCount")),
        ),
    )


def maliyet_tahmini(bolge_sayisi: int) -> int:
    """Bir koşunun harcayacağı birim — çağrı başına 1, sayfalama yok."""
    return bolge_sayisi * len(bolge.LISTELER) * kota.MALIYET[ISLEM]


def topla(
    istemci,
    sayac: kota.KaliciSayac,
    *,
    tur: str,
    bolgeler: list[str],
    yol: Path,
    an: datetime | None = None,
    trend_tavani: int = bolge.TREND_KOTA_TAVANI,
) -> KosuSonucu:
    """Verilen bölgeler için trend listelerini çeker ve depoya yazar.

    Koşudaki **tüm** çağrılar aynı `an` damgasını taşır. DW-29'un hız hesabı
    iki ölçüm arasındaki gerçek süreye dayanıyor; çağrı başına ayrı zaman
    damgası, tek bir koşuyu dakikalara yayılmış sahte bir seriye çevirirdi.

    Bir bölgenin hatası koşuyu bitirmez — bir ülkenin API hatası yüzünden
    doksan dokuz ülkenin verisini kaybetmek anlamsız. Hatalar sayılır ve
    `kosu` tablosuna yazılır.
    """
    an = an or datetime.now(UTC)
    damga = an.isoformat()
    sonuc = KosuSonucu(an=damga, tur=tur, bolge_sayisi=len(bolgeler))
    rezerve = kota.video_basina_maliyet()

    for bolge_kodu in bolgeler:
        for liste in bolge.LISTELER:
            if sayac.surec_harcamasi + kota.MALIYET[ISLEM] > trend_tavani:
                sonuc.kota_bitti = True
                break

            # Muhasebe istekten ÖNCE: reddedilen istek de birim harcıyor.
            # `rezerve` bir videoluk yükleme payını korur — trend araştırması
            # hiçbir koşulda yayını bloke etmemeli.
            try:
                sayac.harca(ISLEM, rezerve=rezerve)
            except kota.KotaAsimi:
                sonuc.kota_bitti = True
                break
            sonuc.cagri_sayisi += 1
            sonuc.harcanan_kota += kota.MALIYET[ISLEM]

            try:
                ogeler = _cek(istemci, bolge_kodu, liste)
            except Exception as hata:  # noqa: BLE001 — tek bölge koşuyu bitirmemeli
                sonuc.hatalar.append(gizle(f"{bolge_kodu}/{liste}: {hata}"))
                continue

            if not ogeler:
                continue  # Çoğu bölge/kategori bileşimi boş döner — hata değil.

            with depo.yazma_islemi(yol) as baglanti:
                for sira, oge in enumerate(ogeler, start=1):
                    video_id = _videoyu_yaz(baglanti, oge, damga)
                    _olcumu_yaz(
                        baglanti,
                        video_id,
                        bolge_kodu=bolge_kodu,
                        an=damga,
                        liste=liste,
                        sira=sira,
                        oge=oge,
                    )
                    sonuc.video_sayisi += 1

        if sonuc.kota_bitti:
            break

    _kosuyu_yaz(yol, sonuc)
    return sonuc


def _cek(istemci, bolge_kodu: str, liste: int) -> list[dict]:
    parametreler = {
        "part": "snippet,statistics,contentDetails,topicDetails",
        "chart": "mostPopular",
        "regionCode": bolge_kodu,
        "maxResults": 50,
    }
    if liste:  # 0 = kısıtsız; parametreyi hiç göndermiyoruz
        parametreler["videoCategoryId"] = str(liste)
    return istemci.videos().list(**parametreler).execute().get("items", [])


def _kosuyu_yaz(yol: Path, sonuc: KosuSonucu) -> None:
    hata_metni = None
    if sonuc.hatalar:
        hata_metni = f"{len(sonuc.hatalar)} bölge: {sonuc.hatalar[0]}"
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            """
            INSERT INTO kosu (an, tur, bolge_sayisi, cagri_sayisi, harcanan_kota, hata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(an) DO UPDATE SET
                cagri_sayisi  = excluded.cagri_sayisi,
                harcanan_kota = excluded.harcanan_kota,
                hata          = excluded.hata
            """,
            (
                sonuc.an,
                sonuc.tur,
                sonuc.bolge_sayisi,
                sonuc.cagri_sayisi,
                sonuc.harcanan_kota,
                hata_metni,
            ),
        )
