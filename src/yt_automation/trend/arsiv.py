"""Arşiv-önce trend kaynağı: önce ÜRETİLEBİLİR konuyu bul, sonra talebi ölç.

⚠️ NEDEN VAR — ölçüldü (2026-08-14). Üretim iki kez durdu ve ikisinde de
sebep hattın kendisi değil, **beslenmemesiydi**:

    `Seçildi` kuyruğu       1-2 aday
    `Yeni` kuyruğu        100+ aday — 40'ının **40'ı** üretilemez
    yedek çapa havuzu       kalan 0

`huni_besle.py` (MoneyPrinterTurbo) `Yeni` adayları arşiv arzıyla ölçüp
`Seçildi`ye terfi ediyor ve doğru çalışıyor; ama terfi edecek aday yok.
Ölçülen menü boyutları: Rogelio Mortimer 0, Antigua Confederación Suiza 0,
Franz Count of Meran 3, Henry Macandrew 3 — hepsi kişi.

Kök neden mevcut kaynakların **yönünde**: talebi ölçüp arzı VARSAYIYORLAR.
Talep/arz boşluğu büyükse konu genelde az bilinen bir kişidir, az bilinen
kişinin de kamu malı görseli yoktur. Yani huninin en yüksek skorlu adayları
sistematik olarak üretilemeyenler.

Bu kaynak yönü tersine çeviriyor: Commons'ta **arşivi zengin** konuları
bulur, sonra onlara mevcut talep ölçümünü uygular. Üretilebilirlik bir
sonuç değil, **başlangıç koşulu**.

⚠️ YENİ SKORLAMA/KUYRUK YOK (ADR-0010, `oneri.py` ve `tiktok.py` ile aynı
desen): bu modül yalnızca başlık üretir; yazma, sınıflandırma ve skorlama
`gtrends.isle`'den yeniden kullanılır. İki ayrı skorlama, eşiklerin zamanla
birbirinden sapması demektir — bugün tam da o sınıf kusur yaşandı.

Ücretsiz, anahtarsız, **YouTube kotasına dokunmaz**.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import bosluk, gtrends, wikipedia

COMMONS_UCU = "https://commons.wikimedia.org/w/api.php"
ZAMAN_ASIMI_SN = 20
BEKLEME_SN = 0.2
"""İstekler arası bekleme — Commons anahtarsız ama sınırsız değil."""

TOHUM_DEGISKENI = "YT_ARSIV_TOHUM"

ASGARI_DOSYA = 25
"""Bir kategorinin aday sayılması için gereken HAM dosya sayısı.

⚠️ Üretim tarafındaki eşikle AYNI SAYI DEĞİL ve olmamalı. `huni_besle.py`
`ASGARI_MENU = 6 * KARE_YUVASI = 12` istiyor ama o **kullanılabilir** görsel
sayısı: lisans, kadraj ve tekrar elemesinden SONRA kalan. Ham kategori
sayısı her zaman daha yüksektir.

Bu sayı ham/kullanılabilir dönüşüm oranından geliyor ve ilk canlı koşumda
gözden geçirilmeli. Çok düşük tutmak, kuyruğu terfide elenecek adayla
doldurur — bugün yaşanan kusurun aynısı, yalnızca bir adım öteye taşınmış
hali olurdu.
"""

ALT_KATEGORI_SINIRI = 60
"""Tohum başına taranacak en fazla alt kategori. Tohum sayısı × bu sayı kadar
dosya-sayımı isteği atılıyor; Commons anahtarsız ama sonsuz da değil."""

VARSAYILAN_TOHUMLAR: tuple[str, ...] = (
    # ⚠️ Tohumlar KONUYA ÇAPALI, cümle kalıbı değil. DW-111'de ölçüldü:
    # cümle kalıbı tohumları ("who was", "the mystery of") 24 terimin
    # 0'ında tarih/bilim konusu verdi, konu çapalı tohumlar 6'sında.
    # Buradaki karşılığı: üst kategori seçimi konuyu belirliyor.
    #
    # ⚠️ Hepsi ANIT/YER/NESNE ağırlıklı. Ölçüldü (konu-sinifi-kaliteyi-
    # belirliyor): anıt/yer/nesne konuları hakem kusuru 0-3 alıyor, kişi
    # biyografileri 9-11 — sebebi kişinin kendisi değil ARŞİVİ (portre
    # yığını vs. çeşitli kadrajlar).
    #
    # ⚠️ COĞRAFİ tohumlar ("... by country") bilerek AZ. Ölçüldü
    # (2026-08-14, canlı): "Archaeological sites in Chile" gibi ülke
    # kategorileri Wikidata'da LİSTE makalesine bağlanıyor ve liste bir
    # Short konusu değil. Tekil konu üreten tohumlar (Shipwrecks, Ancient
    # Roman architecture) daha verimli.
    "Category:Ancient Roman architecture",
    "Category:Ancient Greek architecture",
    "Category:Ancient Egyptian architecture",
    "Category:Shipwrecks",
    "Category:Prehistoric sites",
    "Category:Ancient Roman engineering",
    "Category:Megalithic monuments",
    "Category:Ruins",
    "Category:Archaeological artifacts",
    "Category:Historic bridges",
)


class ArsivHatasi(RuntimeError):
    """Commons ucu okunamadı."""


@dataclass(frozen=True)
class KategoriAdayi:
    baslik: str
    """`Category:` öneki atılmış, Wikipedia başlığına en yakın hali."""

    kategori: str
    dosya: int


def dosya_yolu() -> Path | None:
    """`YT_ARSIV_TOHUM` ile gösterilen tohum dosyası — yoksa `None`."""
    ham = os.environ.get(TOHUM_DEGISKENI, "").strip()
    if not ham:
        return None
    yol = Path(ham).expanduser()
    return yol if yol.is_file() else None


def tohumlari_oku(yol: Path | None = None) -> list[str]:
    """Dosyadan tohumlar. Dosya yoksa boş liste — hata değil."""
    yol = yol or dosya_yolu()
    if yol is None:
        return []
    tohumlar = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        temiz = satir.strip()
        if temiz and not temiz.startswith("//"):
            tohumlar.append(temiz)
    return tohumlar


def tohumlar(dil: str) -> tuple[str, ...]:
    """O pazarın tohumları: dosya varsa **onun yerine**, yoksa varsayılan.

    `oneri.tohumlar` ile aynı sözleşme — dosya varsayılanları genişletmiyor,
    değiştiriyor; yarı yapılandırılmış bir kaynak "neden bu terim geldi"
    sorusunu cevaplanamaz kılar.
    """
    if dosyadan := tohumlari_oku():
        return tuple(dosyadan)
    # ⚠️ Dil ayrımı YOK ve bu kasıtlı — ölçüldü (2026-08-14): ilk sürüm
    # tohumları `{"en": (...)}` diye tutuyordu ve `es` pazarı **0 tohum**
    # alıyordu, yani İspanyolca hiç beslenmiyordu.
    #
    # Commons dilden bağımsız TEK bir medya deposu: `Category:Shipwrecks`
    # her pazar için aynı dosyaları taşıyor. Dile bağlı olan tek şey
    # makale bağlantısı ve onu Wikidata köprüsü hallediyor — `es` pazarı
    # aynı kategoriden İspanyolca makaleyi alıyor. Tohumları pazar başına
    # çevirmek, aynı arşivi iki kez adlandırmak olurdu.
    return VARSAYILAN_TOHUMLAR


def _iste(parametreler: dict) -> dict:
    """Commons API çağrısı. `oneri.py` ile aynı desen: `urllib`, `requests` yok.

    ⚠️ `requests` bilerek kullanılmıyor — bu depoda bağımlılık değil ve tek
    bir modül için eklemek, bütün kurulumları bir paket daha ağırlaştırır.
    """
    sorgu = urllib.parse.urlencode({"format": "json", **parametreler})
    istek = urllib.request.Request(
        f"{COMMONS_UCU}?{sorgu}", headers={"User-Agent": wikipedia.KULLANICI_AJANI}
    )
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_SN) as yanit:
            ham = yanit.read()
    except (urllib.error.URLError, OSError, TimeoutError) as hata:
        raise ArsivHatasi(f"Commons okunamadı: {hata}") from hata
    finally:
        time.sleep(BEKLEME_SN)
    try:
        return json.loads(ham.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as hata:
        raise ArsivHatasi(f"Commons JSON vermedi: {hata}") from hata


def alt_kategoriler(tohum: str, sinir: int = ALT_KATEGORI_SINIRI) -> list[str]:
    """Bir üst kategorinin alt kategorileri."""
    veri = _iste(
        {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": tohum,
            "cmtype": "subcat",
            "cmlimit": min(sinir, 500),
        }
    )
    uyeler = veri.get("query", {}).get("categorymembers", []) or []
    return [str(u.get("title", "")) for u in uyeler if u.get("title")]


def dosya_sayisi(kategori: str, tavan: int = 200) -> int:
    """Kategorideki dosya sayısı.

    ⚠️ Tam sayım değil, TAVANLI sayım: eşiği geçip geçmediğini bilmek
    yetiyor ve 500'er sayfa gezmek istek israfı olurdu.
    """
    veri = _iste(
        {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": kategori,
            "cmtype": "file",
            "cmlimit": min(tavan, 500),
        }
    )
    return len(veri.get("query", {}).get("categorymembers", []) or [])


def _basliga_cevir(kategori: str) -> str:
    """`Category:Pompeii` → `Pompeii`."""
    return kategori.split(":", 1)[-1].strip()


WIKIDATA_UCU = "https://www.wikidata.org/w/api.php"


def wikidata_ogesi(kategori: str) -> str | None:
    """Commons kategorisinin Wikidata öğesi (`Q…`) — yoksa `None`."""
    veri = _iste(
        {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "titles": kategori}
    )
    for sayfa in (veri.get("query", {}).get("pages", {}) or {}).values():
        if oge := (sayfa.get("pageprops", {}) or {}).get("wikibase_item"):
            return str(oge)
    return None


def _wikidata_iste(parametreler: dict) -> dict:
    sorgu = urllib.parse.urlencode({"format": "json", **parametreler})
    istek = urllib.request.Request(
        f"{WIKIDATA_UCU}?{sorgu}", headers={"User-Agent": wikipedia.KULLANICI_AJANI}
    )
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_SN) as yanit:
            ham = yanit.read()
    except (urllib.error.URLError, OSError, TimeoutError) as hata:
        raise ArsivHatasi(f"Wikidata okunamadı: {hata}") from hata
    finally:
        time.sleep(BEKLEME_SN)
    try:
        return json.loads(ham.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as hata:
        raise ArsivHatasi(f"Wikidata JSON vermedi: {hata}") from hata


ANA_KONU_OZELLIGI = "P301"
"""`category's main topic` — kategori öğesinden asıl konuya giden bağ.

⚠️ Bu adım olmadan köprü YANLIŞ sonuç veriyor, ölçüldü (2026-08-14):
`Category:Mastabas` → Wikidata öğesi → enwiki bağlantısı
**`Category:Mastabas`**, yani Wikipedia'nın KATEGORİ sayfası. Commons
kategorilerinin öğesi bir "Wikimedia kategorisi" öğesidir ve sitelink'i
makaleye değil kategoriye gider. Talep ölçümü makale okunmasına dayandığı
için kategori sayfası boruya çöp doldururdu.
"""


def _sitelink(oge: str, dil: str) -> str | None:
    veri = _wikidata_iste(
        {"action": "wbgetentities", "ids": oge, "props": "sitelinks", "sitefilter": f"{dil}wiki"}
    )
    varlik = (veri.get("entities", {}) or {}).get(oge, {})
    baglanti = (varlik.get("sitelinks", {}) or {}).get(f"{dil}wiki", {})
    baslik = str(baglanti.get("title", "")).strip()
    return baslik or None


def ana_konu(oge: str) -> str | None:
    """Kategori öğesinin `P301` ile gösterdiği asıl konu öğesi."""
    veri = _wikidata_iste(
        {"action": "wbgetentities", "ids": oge, "props": "claims", "languages": "en"}
    )
    iddialar = ((veri.get("entities", {}) or {}).get(oge, {}) or {}).get("claims", {}) or {}
    for iddia in iddialar.get(ANA_KONU_OZELLIGI, []) or []:
        deger = (((iddia.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        if kimlik := deger.get("id"):
            return str(kimlik)
    return None


LISTE_ONEKLERI = ("list of", "lists of", "liste ", "index of", "outline of")
"""Video konusu OLMAYAN başlıklar.

⚠️ Ölçüldü (2026-08-14, canlı kuru koşum): üretilen 35 adayın büyük kısmı
liste makalesine düşüyordu — "List_of_archaeological_sites_in_Chile",
"List_of_archaeological_sites_by_country". Bunlar dizin sayfaları: bir
Short'un anlatacağı tekil bir konu değiller ve arşiv menüleri de dağınık.

Sebep yapısal: coğrafi Commons kategorileri ("Archaeological sites in
Chile") Wikidata'da liste makalesine bağlanıyor, tekil bir konuya değil.
"""


def _liste_makalesi_mi(baslik: str) -> bool:
    sade = baslik.replace("_", " ").strip().lower()
    return any(sade.startswith(o) for o in LISTE_ONEKLERI)


def makale_baglantisi(oge: str, dil: str) -> str | None:
    """Öğenin o dildeki Wikipedia MAKALESİ — kategori ya da liste değil.

    Önce `P301` ile asıl konuya geçiliyor; o yoksa öğenin kendi bağlantısı
    kullanılıyor ama kategori sayfaları elenir.
    """
    baslik = None
    if (konu_ogesi := ana_konu(oge)) and (bulunan := _sitelink(konu_ogesi, dil)):
        baslik = bulunan
    else:
        bulunan = _sitelink(oge, dil)
        # ⚠️ "Category:"/"Kategori:" ile başlayan başlık MAKALE DEĞİL.
        if bulunan and ":" not in bulunan.split("_")[0]:
            baslik = bulunan
    if baslik and _liste_makalesi_mi(baslik):
        return None
    return baslik


def makale_bul(dil: str, terim: str) -> str | None:
    """`gtrends.isle`nin `makale_bul` sözleşmesi — Wikidata köprüsüyle.

    ⚠️ NEDEN ARAMA DEĞİL KÖPRÜ — ölçüldü (2026-08-14). Varsayılan
    `gtrends.makale_ara` bu kaynağın adaylarının **yarısından çoğunu**
    kaybediyordu (11 adayın 6'sı):

        "Mastabas"                 -> None   (makale: "Mastaba")
        "Ancient Roman aqueducts"  -> None   (makale: "Roman aqueduct")
        "Ancient Roman palaestras" -> None   (makale: "Palaestra")

    Sebep yapısal: Commons kategorileri ÇOĞUL, Wikipedia makaleleri TEKİL.
    `bosluk.alakali_mi` tam belirteç örtüşmesi istiyor ve "mastabas" ile
    "mastaba" örtüşmüyor. Arama gevşetilse bu kez çağrışım gelir — o
    kapının var oluş sebebi tam olarak budur (`makale_ara` docstring'i).

    Wikidata köprüsü ikisini de aşıyor: kategori → öğe → o dilin makalesi,
    kesin eşleşme. Türkçe pazarda da çalışıyor; arama yalnızca İngilizce
    başlıkta işe yarardı.

    Köprü kurulamazsa aramaya düşülüyor: kayıp, sessiz kayıptan iyidir.
    """
    kategori = _TERIM_KATEGORI.get(terim)
    if kategori:
        try:
            if (oge := wikidata_ogesi(kategori)) and (
                baslik := makale_baglantisi(oge, dil)
            ):
                return baslik
        except ArsivHatasi:
            pass
    return gtrends.makale_ara(dil, terim)


_TERIM_KATEGORI: dict[str, str] = {}
"""Üretilen başlık → geldiği Commons kategorisi.

`gtrends.isle` sözleşmesi `makale_bul(dil, terim)` — kategoriyi taşımıyor.
Eşleme burada tutuluyor ki köprü hangi kategoriye bakacağını bilsin."""


def adaylari_bul(dil: str, *, asgari: int = ASGARI_DOSYA) -> list[KategoriAdayi]:
    """Tohumların alt kategorilerinden eşiği geçenler.

    Bir tohumun hatası diğerlerini düşürmez — huninin her katmanındaki
    kararın aynısı (DW-28'den beri).
    """
    adaylar: list[KategoriAdayi] = []
    gorulen: set[str] = set()
    for tohum in tohumlar(dil):
        try:
            altlar = alt_kategoriler(tohum)
        except ArsivHatasi:
            continue
        for kategori in altlar:
            if kategori in gorulen:
                continue
            gorulen.add(kategori)
            try:
                adet = dosya_sayisi(kategori)
            except ArsivHatasi:
                continue
            if adet >= asgari:
                adaylar.append(
                    KategoriAdayi(
                        baslik=_basliga_cevir(kategori), kategori=kategori, dosya=adet
                    )
                )
    return adaylar


def terimleri_cek(geo: str) -> list[gtrends.TrendTerimi]:
    """`gtrends.isle`nin beklediği biçim — arşivi zengin konu başlıkları.

    ⚠️ `geo` yalnızca DİL için kullanılıyor: Commons dilden bağımsız tek bir
    medya deposu, ülkeye göre farklı sonuç vermiyor. Aynı konunun farklı
    pazarlarda ayrı makalesi ve ayrı talebi var, o yüzden pazar ayrımı
    boruda korunuyor; tekrarlanan Commons isteğini `_ONBELLEK` kesiyor.
    """
    dil = geo.partition("-")[0] or geo
    if dil not in _ONBELLEK:
        _ONBELLEK[dil] = adaylari_bul(dil)
    for a in _ONBELLEK[dil]:
        _TERIM_KATEGORI[a.baslik] = a.kategori
    return [
        gtrends.TrendTerimi(terim=a.baslik, geo=geo, trafik=f"{a.dosya}+ dosya")
        for a in _ONBELLEK[dil]
    ]


_ONBELLEK: dict[str, list[KategoriAdayi]] = {}


def onbellegi_temizle() -> None:
    """Koşumlar arası durum taşımasın (testler ve uzun süreçler için)."""
    _ONBELLEK.clear()
    _TERIM_KATEGORI.clear()


def gunluk_nobet(dizin: Path, gun: str | None = None) -> Path:
    """O günün nöbet dosyası — tarama günde bir kez koşsun diye."""
    from datetime import date

    return dizin / f".arsiv-{gun or date.today().isoformat()}"


def isle(yol: Path, *, pazarlar: tuple[str, ...] | None = None) -> gtrends.IslemeSonucu:
    """Arşivi zengin konuları boruya yazar.

    `tiktok.isle` ve `oneri.isle` ile aynı desen (ADR-0010): yazma ve
    sınıflandırma kodu kopyalanmıyor, `gtrends.isle` kendi terim
    getiricisiyle yeniden kullanılıyor.
    """
    onbellegi_temizle()
    return gtrends.isle(
        yol,
        pazarlar=pazarlar,
        terim_getir=terimleri_cek,
        makale_bul=makale_bul,
        # ⚠️ Coğrafya listesi tek elemanlı: Commons ülkeye göre değişmiyor,
        # her ülke için tekrar taramak aynı başlıkları yeniden getirirdi.
        geo_kodlari={dil: (dil,) for dil in (pazarlar or bosluk.hedef_pazarlar())},
    )
