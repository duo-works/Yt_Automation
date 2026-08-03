"""Google Trends RSS kaynağı — gün-içi trend sinyali.

Wikipedia pageviews **günlük** yayımlanıyor; huni bir konunun patladığını en
geç ~30 saat sonra öğreniyor. Google Trends "Trending Now" RSS'i saatlik
tazelikte, ücretsiz ve anahtarsız — Shorts kanalının ihtiyacı olan gün-içi
sinyal buradan geliyor.

## Neden pytrends değil

`pytrends` resmî değil, Google'ın iç uç noktalarını taklit ediyor ve o uçlar
değiştikçe kırılıyor (2024-2025'te iki kez). RSS ise yayımlanmış bir arayüz:
stdlib `xml.etree` ile ayrıştırılıyor, **yeni bağımlılık yok**.

## Tek boru deseni (ADR-0010)

Bu modül kendi kuyruk/skor sistemini KURMAZ. Eşleşen konu mevcut borunun
girişine yazılır — `makale` + `okunma` — ve gerisi zaten var olan hattır:

    RSS terimi → Wikipedia makalesi → Wikidata sınıfı → makale/okunma
    → sıçrama detektörü (DW-54) → sondaj + kapılar (DW-51/52/53) → Notion

Okunma serisi de yazılıyor (son 8 gün, pageviews API, ücretsiz): sıçrama
detektörünün tabanı ve DW-51'in talep kapısı böylece yeni konu için de
çalışıyor. Boru dışı hiçbir kestirme yok — GTrends yalnızca bir **keşif**
kaynağı, karar mercii değil.

Eşleşmeyen terimler sessizce düşmez, sayısı raporlanır: magazin/spor ağırlıklı
bir listede düşük eşleşme normaldir, sıfır eşleşme ise ayrıştırıcının
kırıldığının işareti.

YouTube kotasına dokunmuyor.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .. import depo
from . import bosluk, konu, wikipedia

# Hedef pazar → RSS coğrafyaları. Pazar dili birden çok ülkede konuşuluyor;
# en büyük iki arama pazarı seçildi. Yeni pazar eklenirse buraya satır eklemek
# yeterli — kod geri kalanı `hedef_pazarlar()`'dan türetiyor.
GEO_KODLARI: dict[str, tuple[str, ...]] = {
    "en": ("US", "GB"),
    "es": ("ES", "MX"),
    "tr": ("TR",),
    "de": ("DE",),
}

RSS_TABAN = "https://trends.google.com/trending/rss"
_HT = "{https://trends.google.com/trending/rss}"

# ⚠️ Terim başına bir arama çağrısı yapılıyor ve bu Wikipedia'nın hız sınırına
# giriyor: ilk canlı koşumda 4 coğrafya × 10 terim ardışık istekle **HTTP 429**
# alındı. İki önlem birlikte gerekti:
#
#   1. Wikimedia'nın şart koştuğu tanımlayıcı User-Agent (`wikipedia` modülü
#      bunu zaten doğru yapıyordu; burada tekrar tanımlamak yerine ondan
#      alınıyor — tek yerde durması, iletişim bilgisi değişirse tek yerde
#      değişmesi demek).
#   2. Çağrılar arası bekleme. `list=search` toplu sorgu kabul etmiyor, yani
#      istek sayısı terim sayısı kadar; tek çare hızı düşürmek.
BEKLEME_SN = 0.5

# Coğrafya başına en fazla kaç terim işlensin. RSS zaten ~10-20 terim
# döndürüyor; sınır hem hız sınırına karşı hem de listenin kuyruğundaki
# düşük trafikli terimlerin değeri düşük olduğu için.
GEO_BASINA_TERIM = 12


class GTrendsHatasi(RuntimeError):
    """Trend kaynağından veri alınamadı."""


# Okunma serisi derinliği: sıçrama detektörünün taban penceresi (7 gün) + son
# gün. Daha uzunu bilgi eklemiyor, daha kısası tabanı güvenilmez bırakıyor.
SERI_GUN = 8

ZAMAN_ASIMI = 20


@dataclass
class TrendTerimi:
    terim: str
    geo: str
    trafik: str  # RSS "200+" gibi kaba bir bant veriyor; sayı değil etiket


@dataclass
class IslemeSonucu:
    terim: int = 0
    eslesen: int = 0
    yazilan: int = 0
    siniflar: dict[str, int] = field(default_factory=dict)
    hatalar: list[str] = field(default_factory=list)

    def ozet(self) -> str:
        dagilim = " · ".join(f"{k}:{v}" for k, v in sorted(self.siniflar.items()))
        satir = (
            f"{self.terim} terim · {self.eslesen} Wikipedia eşleşmesi · "
            f"{self.yazilan} yeni konu · {dagilim or 'sınıf yok'}"
        )
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        return satir


def terimleri_cek(geo: str) -> list[TrendTerimi]:
    """Bir coğrafyanın güncel trend terimleri. Ücretsiz, anahtarsız."""
    url = f"{RSS_TABAN}?geo={geo}"
    istek = urllib.request.Request(url, headers={"User-Agent": wikipedia.KULLANICI_AJANI})
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            agac = ET.fromstring(yanit.read())
    except (urllib.error.HTTPError, OSError, ET.ParseError) as hata:
        raise GTrendsHatasi(f"{geo}: {hata}") from None
    cikti = []
    for oge in agac.iter("item"):
        baslik = (oge.findtext("title") or "").strip()
        if baslik:
            cikti.append(
                TrendTerimi(
                    terim=baslik,
                    geo=geo,
                    trafik=(oge.findtext(f"{_HT}approx_traffic") or "").strip(),
                )
            )
    return cikti[:GEO_BASINA_TERIM]


def makale_ara(dil: str, terim: str) -> str | None:
    """Terime karşılık gelen Wikipedia makalesi — yoksa `None`.

    İlk arama sonucu alınıyor ama körlemesine değil: başlık, terimin
    belirteçleriyle örtüşmüyorsa eşleşme sayılmıyor (`bosluk.alakali_mi`,
    sondajın alaka ölçümüyle aynı tanım). "tarek mansour" araması "Kalshi"
    döndürürse o bir eşleşme değil, arama motorunun çağrışımı — çağrışımı
    makale sanmak boruya çöp doldurur.
    """
    url = (
        f"https://{dil}.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={urllib.parse.quote(terim)}&srlimit=1&format=json"
    )
    istek = urllib.request.Request(url, headers={"User-Agent": wikipedia.KULLANICI_AJANI})
    # `list=search` toplu sorgu kabul etmiyor: istek sayısı terim sayısı kadar
    # ve hız sınırına giriyor (ilk canlı koşumda HTTP 429). Bekleme burada,
    # çağrının hemen öncesinde — çağıran unutamaz.
    time.sleep(BEKLEME_SN)
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            veri = json.load(yanit)
    except (urllib.error.HTTPError, OSError, ValueError) as hata:
        raise GTrendsHatasi(f"{dil}/{terim}: {hata}") from None
    sonuclar = veri.get("query", {}).get("search", [])
    if not sonuclar:
        return None
    baslik = sonuclar[0].get("title", "")
    if not baslik or not bosluk.alakali_mi(bosluk.belirtecler(terim), baslik):
        return None
    return baslik.replace(" ", "_")


def _konu_yaz(yol: Path, dil: str, baslik: str, qid: str | None, sinif: str) -> None:
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            """
            INSERT INTO makale (dil, baslik, qid, sinif, sinif_kaynagi, ilk_gorulme)
            VALUES (?, ?, ?, ?, 'gtrends', ?)
            ON CONFLICT(dil, baslik) DO UPDATE SET
                qid = COALESCE(excluded.qid, makale.qid)
            """,
            (dil, baslik, qid, sinif, datetime.now(UTC).isoformat()),
        )


def _seriyi_yaz(yol: Path, dil: str, baslik: str) -> int:
    """Son SERI_GUN günün okunma serisini pageviews API'sinden çeker ve yazar.

    Bu adım süs değil, borunun kendisi: `okunma` satırı olmayan konu ne
    sıçrama detektörüne ne sondaj kuyruğuna ne LLM kuyruğuna girer. GTrends
    keşfi ancak talep kanıtıyla birlikte boruya girerse iş görür.
    """
    bugun = datetime.now(UTC).date()
    seri = wikipedia.makale_serisi(dil, baslik, bugun - timedelta(days=SERI_GUN), bugun)
    if not seri:
        return 0
    with depo.yazma_islemi(yol) as baglanti:
        for o in seri:
            baglanti.execute(
                """
                INSERT INTO okunma (dil, baslik, gun, okunma, sira)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(dil, baslik, gun) DO UPDATE SET okunma = excluded.okunma
                """,
                (dil, baslik, o.gun, o.okunma),
            )
    return len(seri)


def isle(
    yol: Path,
    *,
    pazarlar: tuple[str, ...] | None = None,
    terim_getir=None,
    makale_bul=None,
) -> IslemeSonucu:
    """RSS terimlerini toplar, eşleşenleri boruya yazar.

    Bir coğrafyanın/terimin hatası diğerlerini düşürmez — huninin her
    katmanındaki kararın aynısı (DW-28'den beri).

    `terim_getir` / `makale_bul` testler için enjekte edilebilir.
    """
    pazarlar = pazarlar or bosluk.hedef_pazarlar()
    terim_getir = terim_getir or terimleri_cek
    makale_bul = makale_bul or makale_ara
    sonuc = IslemeSonucu()

    for dil in pazarlar:
        for geo in GEO_KODLARI.get(dil, ()):
            try:
                terimler = terim_getir(geo)
            except Exception as hata:  # noqa: BLE001 — bir coğrafya diğerini düşürmesin
                sonuc.hatalar.append(f"{geo}: {hata}")
                continue
            sonuc.terim += len(terimler)
            for t in terimler:
                try:
                    baslik = makale_bul(dil, t.terim)
                    if not baslik:
                        continue
                    sonuc.eslesen += 1
                    if _konu_taninmiyor(yol, dil, baslik):
                        sinif, qid = _siniflandir(dil, baslik)
                        _konu_yaz(yol, dil, baslik, qid, sinif)
                        # Seri yalnızca hattın ilgilendiği konular için
                        # çekiliyor. Trend listesi magazin/spor/hava durumu
                        # ağırlıklı; hepsine pageviews çağrısı yapmak istek
                        # sayısını dörde katlar ve hiçbir sorunun cevabına
                        # yaklaştırmaz. `belirsiz` dahil çünkü LLM kuyruğuna
                        # girecek ve orada tarih/bilim çıkabilir.
                        if sinif in ("tarih", "bilim", "belirsiz"):
                            _seriyi_yaz(yol, dil, baslik)
                        sonuc.yazilan += 1
                        sonuc.siniflar[sinif] = sonuc.siniflar.get(sinif, 0) + 1
                except Exception as hata:  # noqa: BLE001
                    sonuc.hatalar.append(f"{t.terim}: {hata}")
    return sonuc


def _konu_taninmiyor(yol: Path, dil: str, baslik: str) -> bool:
    """Bilinen konuyu yeniden işlememek: sınıflandırma ve seri çekimi bir kez.

    Konu zaten `makale`'deyse okunması saatlik tarama değil günlük `konu
    topla` tarafından güncelleniyor; burada tekrar yazmak aynı veriyi saatte
    bir çekmek olurdu.
    """
    baglanti = depo.baglan(yol)
    try:
        return (
            baglanti.execute(
                "SELECT 1 FROM makale WHERE dil = ? AND baslik = ?", (dil, baslik)
            ).fetchone()
            is None
        )
    finally:
        baglanti.close()


def _siniflandir(dil: str, baslik: str) -> tuple[str, str | None]:
    """Wikidata kademesi — `konu_toplayici.topla` ile aynı sıra.

    Karar veremezse `belirsiz` döner ve konu LLM kuyruğuna girer (okunma
    satırı yazıldığı için `siniflandirici.bekleyenler` onu görür). Yani
    GTrends konusu, `konu topla`nın bulduğu konuyla aynı muameleyi alıyor —
    ayrıcalık da cezası da yok.
    """
    duz = baslik.replace("_", " ")
    kimlikler = konu.kimlikleri_getir(dil, [duz]) or konu.kimlikleri_getir(dil, [baslik])
    qid = kimlikler.get(duz) or kimlikler.get(baslik)
    if not qid:
        return "belirsiz", None
    varlik = konu.varliklari_getir([qid]).get(qid)
    if not varlik:
        return "belirsiz", qid
    return konu.siniflandir(varlik["tipler"], varlik), qid
