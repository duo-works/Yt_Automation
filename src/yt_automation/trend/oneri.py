"""YouTube arama önerileri — talep sinyalinin platformun kendisinden gelmesi.

Huninin talep tarafı bugün **Wikipedia okunması**. Bu bir vekil ölçü ve
zayıflığını `bosluk.skorla()` kendi docstring'inde zaten yazıyor: Wikipedia
okunması ile YouTube izlenmesi iki ayrı ölçek, "işaretin anlamlı olması için
talep tarafına bir ölçek katsayısı gerekiyor". Sorun yalnızca ölçek de değil —
**ansiklopedi okumak ile YouTube'da video aramak farklı niyetler.** Bir konu
Wikipedia'da patlayıp YouTube'da hiç aranmıyor olabilir.

Bu modül talebi kaynağından okuyor: insanların YouTube arama kutusuna gerçekte
ne yazdığını.

## Neden Studio'nun Research sekmesi değil

YouTube'un TikTok'taki "Creator Search Insights" karşılığı **var**: Studio →
Analytics → **Research**. Arama hacmini (Low/Medium/High) ve *"content gap"*
etiketiyle filtresini veriyor — kavram ve isim birebir aynı. YouTube content
gap'i "az sonuç dönen, ya da mevcut içeriğin eski/düşük kaliteli olduğu"
aramalar diye tanımlıyor; bu huninin `bosluk.py`'de elle ölçtüğü şeyin ta
kendisi.

⚠️ **Ama hiçbir resmî API'den verilmiyor** (ölçüldü 2026-08-09). YouTube arama
hacmini Data API'de yayımlamıyor; Research sekmesi yalnızca Studio arayüzünde.
Üçüncü parti araçların (vidIQ, Ahrefs) verdiği hacimler kendi tahmin modelleri,
YouTube'un verisi değil. Otomatik hat için kalan tek ücretsiz yol öneri ucu.

## Gayriresmî uç — bilinçli ve tartışmalı bir taviz

`gtrends.py` `pytrends`'i reddederken gerekçesi şuydu: *"resmî değil, Google'ın
iç uç noktalarını taklit ediyor ve o uçlar değiştikçe kırılıyor"*. Öneri ucu
(`suggestqueries.google.com/complete/search`) **tam olarak o sınıfa giriyor.**
Bunu gizlemenin anlamı yok.

İki fark kararı yine de bu yöne çeviriyor:

1. **Alternatifi yok.** Trends'te RSS gibi yayımlanmış bir arayüz vardı, yani
   seçim "resmî vs gayriresmî"ydi. Arama önerisinde seçim "gayriresmî vs hiç".
2. **Kırılması hattı düşürmüyor.** ADR-0010'un kaynak deseni kaynağı izole
   ediyor: uç kırılırsa bu modül boş döner, huni Wikipedia + Trends ile
   çalışmaya devam eder. Sessiz bozulma riski de yok — CLI terim sayısını basar,
   sıfır terim görünür bir sinyal.

Yeniden değerlendirilmesi gereken bir karar; kalıcı bir taahhüt değil.

## Ölçülmüş davranış (2026-08-09)

    GET /complete/search?client=firefox&ds=yt&hl=en&gl=US&q=ancient+rome
    → 200, ["ancient rome",["ancient rome","ancient rome documentary", ...]]

Anahtar yok, kota yok, kimlik doğrulama yok. **YouTube Data API kotasına
dokunmuyor** — sondaj bütçesiyle yarışmıyor.

⚠️ **Kodlama User-Agent'a göre değişiyor** — sabit varsaymak hata. Ölçüldü,
aynı sorgu (`hl=es`, "quién fue"), aynı uç:

    UA: duo-works-yt-automation/0.1 …  → charset=iso-8859-1, b"qui\\xe9n"
    UA: Mozilla/5.0                    → charset=utf-8,      b"qui\\xc3\\xa9n"

İyi haber: `Content-Type` başlığı **iki durumda da doğruyu söylüyor.** Bu
yüzden kodlama sabitlenmiyor, yanıttan okunuyor. UTF-8 sabitleyen ilk sürüm
İspanyolca'yı bozuyordu ("quién fue" → "qui\\ufffdn fue") ve bu sessiz bir
bozulma: terim yazılıyor, yalnızca Wikipedia'da hiçbir zaman eşleşmiyor.

Repo'nun kimlikli UA'sı bilerek korunuyor — kim olduğumuzu söylemek doğru
davranış. Tarayıcı taklidiyle UTF-8'e zorlamak yerine beyana uyuluyor.

## Tohum gerekiyor — bu bir trend listesi değil

Trends RSS "şu an ne yükseliyor" diye hazır bir liste veriyor. Öneri ucu
öyle değil: bir **önek** verirsin, tamamlamalarını döndürür. Yani kaynak
tohumla çalışıyor ve tohum kalitesi çıktıyı belirliyor.

Varsayılan tohumlar **konuya çapalı**, cümle kalıbına değil. Bu ölçülmüş bir
karar, estetik değil (2026-08-09, aynı boru, 24'er terim):

    cümle kalıbı  ("who was", "what happened to", "the mystery of")
        → 16/24 Wikipedia eşleşmesi, **0 tarih/bilim**
    konu çapalı   ("ancient rome", "roman empire", "ancient egypt", …)
        → 15/24 Wikipedia eşleşmesi, **6 tarih/bilim**

Sebebi öneri ucunun ne olduğu: tamamlama motoru, konu dizini değil. "who
was" öneki bugün **kimin arandığını** döndürüyor — Charlie Kirk, Jesus, "who
was in paris" (şarkı). Cümle kalıbı niyeti değil güncel magazini yakalıyor.
Konu çapası ise tamamlamayı konunun içinde tutuyor ve dönen şey asıl aranan
bilgi oluyor: "roman empire documentary", "ancient egypt history".

⚠️ **Bunun bedeli var ve gizlenmemeli:** konu çapalı tohum ancak *tohumladığın
konuyu* keşfeder. Yani bu kaynak "hangi yeni konu patlıyor" sorusunu
cevaplamıyor — onu Wikipedia sıçraması ve Trends yapıyor. Bu kaynağın
cevapladığı soru farklı: **"bu konuda insanlar YouTube'da tam olarak ne
arıyor?"** Aynı konunun "documentary" mi "history" mi "explained" mi
istendiği, üretilecek videonun açısını belirliyor.

Gürültü zaten ikinci savunmaya da takılıyor: boru terimi Wikipedia'da arıyor
ve Wikidata sınıfı `tarih`/`bilim` değilse konu huniye girmiyor. Tohum
kalitesi verimi belirliyor, doğruluğu değil.

`YT_ONERI_TOHUM` bir metin dosyasını gösteriyorsa varsayılanların **yerine**
o dosya kullanılır (satır başına bir tohum, `//` yorum). Kanal nişi
değiştiğinde kod değişmesin diye.

## Tek boru deseni (ADR-0010)

Kendi kuyruğunu/skorunu KURMUYOR. Terimler mevcut borunun girişine yazılıyor:

    öneri terimi → Wikipedia makalesi → Wikidata sınıfı → makale/okunma
    → sıçrama detektörü → sondaj + kapılar → Notion

## Yumuşak düşme

Uç erişilemezse ya da tohum yoksa modül **sessizce atlanır** ve huni
etkilenmez. Bir tohumun hatası diğerlerini düşürmez.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import gtrends, wikipedia

UC_NOKTA = "https://suggestqueries.google.com/complete/search"

# `client=firefox` en sade gövdeyi veriyor: [sorgu, [öneriler], ...]. Diğer
# istemci değerleri JSONP sarmalayıcı ya da ek meta döndürüyor ve ayrıştırması
# daha kırılgan.
ISTEMCI = "firefox"
VERI_KUMESI = "yt"  # ds=yt → YouTube arama önerileri; boş bırakılırsa Google Web

TOHUM_DEGISKENI = "YT_ONERI_TOHUM"

# İstekler arası bekleme — `gtrends.BEKLEME_SN` ile aynı gerekçe ve aynı değer:
# ücretsiz uca saniyede onlarca istek atmak hem kaba hem engellenme sebebi.
BEKLEME_SN = 0.5

ZAMAN_ASIMI_SN = 15

# Yanıt kodlamayı beyan etmezse düşülecek değer. Uç bugüne kadar her yanıtta
# beyan etti; bu yalnızca beyanın kaybolduğu gün sessizce bozulmamak için.
VARSAYILAN_KODLAMA = "utf-8"

# Pazar → (hl, gl) çiftleri. `gtrends.GEO_KODLARI` ile aynı pazar/ülke seçimi;
# fark, öneri ucunun **hem dil hem ülke** istemesi. `gtrends.isle` terim
# getiricisine yalnızca `geo` veriyor, o yüzden ikisi tek dizede taşınıyor
# ("en-US") ve `_coz` ayırıyor. Boruyu iki parametreli hale getirmemek için:
# `geo` orada zaten opak bir kaynak etiketi.
GEO_KODLARI: dict[str, tuple[str, ...]] = {
    "en": ("en-US", "en-GB"),
    "es": ("es-ES", "es-MX"),
    "tr": ("tr-TR",),
    "de": ("de-DE",),
}

# Varsayılan tohumlar — **konuya çapalı**, cümle kalıbına değil.
#
# Ölçüm docstring'de: cümle kalıbı 0/24 tarih-bilim, konu çapası 6/24. Kalıp
# önekler bugünün magazinini getiriyor ("who was" → Charlie Kirk), konu
# çapası tamamlamayı konunun içinde tutuyor ("roman empire documentary").
#
# Liste bilerek kısa ve geniş: her tohum tek bir konuyu değil bir **alanı**
# açıyor ve tamamlamalar alt açıları getiriyor. Kanal olgunlaştıkça
# `YT_ONERI_TOHUM` ile daralması beklenir — asıl kalibrasyon yayın
# sonuçlarıyla yapılır, bugün o veri yok.
VARSAYILAN_TOHUMLAR: dict[str, tuple[str, ...]] = {
    "en": (
        "ancient rome",
        "ancient egypt",
        "roman empire",
        "ottoman empire",
        "lost civilization",
        "archaeology discovery",
        "ancient greece",
        "medieval history",
        "space discovery",
        "human origins",
    ),
    "es": (
        "imperio romano",
        "antiguo egipto",
        "civilización perdida",
        "imperio otomano",
        "descubrimiento arqueológico",
        "antigua grecia",
        "historia medieval",
        "descubrimiento espacial",
        "origen del hombre",
        "misterio histórico",
    ),
    "tr": (
        "osmanlı imparatorluğu",
        "antik roma",
        "antik mısır",
        "kayıp medeniyet",
        "arkeolojik keşif",
        "antik yunan",
        "uzay keşfi",
        "insanın kökeni",
    ),
    "de": (
        "römisches reich",
        "altes ägypten",
        "verlorene zivilisation",
        "archäologische entdeckung",
        "antikes griechenland",
        "mittelalter geschichte",
    ),
}


class OneriHatasi(RuntimeError):
    """Öneri ucu okunamadı."""


def _coz(geo: str) -> tuple[str, str]:
    """`"en-US"` → `("en", "US")`. Ülkesiz verilirse dil ülke olarak da geçer."""
    dil, _, ulke = geo.partition("-")
    return dil, (ulke or dil.upper())


def dosya_yolu() -> Path | None:
    """`YT_ONERI_TOHUM` ile gösterilen tohum dosyası — yoksa `None`."""
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

    Dosya varsayılanları genişletmiyor, değiştiriyor: yarı yapılandırılmış bir
    kaynak "neden bu terim geldi" sorusunu cevaplanamaz hale getirir.
    """
    if dosyadan := tohumlari_oku():
        return tuple(dosyadan)
    return VARSAYILAN_TOHUMLAR.get(dil, ())


def onerileri_cek(tohum: str, geo: str) -> list[str]:
    """Bir tohumun YouTube arama önerileri. Ücretsiz, anahtarsız, kotasız."""
    dil, ulke = _coz(geo)
    sorgu = urllib.parse.urlencode(
        {"client": ISTEMCI, "ds": VERI_KUMESI, "hl": dil, "gl": ulke, "q": tohum}
    )
    istek = urllib.request.Request(
        f"{UC_NOKTA}?{sorgu}", headers={"User-Agent": wikipedia.KULLANICI_AJANI}
    )
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_SN) as yanit:
            ham = yanit.read()
            # ⚠️ Kodlama **yanıttan** okunuyor, sabitlenmiyor: uç aynı sorguya
            # User-Agent'a göre ISO-8859-1 ya da UTF-8 dönüyor (modül
            # docstring'i, ölçüldü 2026-08-09). Başlık ikisinde de doğru.
            kodlama = yanit.headers.get_content_charset() or VARSAYILAN_KODLAMA
    except (urllib.error.URLError, OSError, TimeoutError) as hata:
        raise OneriHatasi(f"{tohum} ({geo}): {hata}") from hata
    finally:
        time.sleep(BEKLEME_SN)

    # `errors="replace"` çökmemek için — bozuk tek bir bayt yüzünden pazarın
    # tamamını kaybetmek istemiyoruz.
    try:
        veri = json.loads(ham.decode(kodlama, errors="replace"))
    except (LookupError, json.JSONDecodeError) as hata:
        raise OneriHatasi(f"{tohum} ({geo}): gövde ayrıştırılamadı — {hata}") from hata

    if not isinstance(veri, list) or len(veri) < 2 or not isinstance(veri[1], list):
        raise OneriHatasi(f"{tohum} ({geo}): beklenmeyen gövde biçimi")

    # İlk öğe genelde tohumun kendisi; tohum zaten bilinen bir şey, terim
    # olarak geri yazmanın değeri yok.
    return [o for o in veri[1] if isinstance(o, str) and o.strip() and o.strip() != tohum.strip()]


def terimleri_cek(geo: str) -> list[gtrends.TrendTerimi]:
    """Bir pazarın bütün tohumlarından toplanan öneriler, tekrarsız.

    Bir tohumun hatası diğerlerini düşürmez — huninin her katmanındaki kararın
    aynısı. Hiçbir tohum çalışmazsa `OneriHatasi`: sessiz boş dönüş, kırık ucu
    "bugün öneri yokmuş" gibi gösterirdi.
    """
    dil, _ = _coz(geo)
    kume = tohumlar(dil)
    if not kume:
        return []

    terimler: list[gtrends.TrendTerimi] = []
    gorulen: set[str] = set()
    hatalar: list[str] = []
    for tohum in kume:
        try:
            oneriler = onerileri_cek(tohum, geo)
        except OneriHatasi as hata:
            hatalar.append(str(hata))
            continue
        for oneri in oneriler:
            anahtar = oneri.strip().casefold()
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            # `trafik` boş: öneri ucu hacim vermiyor. Sıra kaba bir popülerlik
            # göstergesi ama sayı değil — uydurma bir bant yazmaktansa boş
            # bırakmak dürüst.
            terimler.append(gtrends.TrendTerimi(terim=oneri.strip(), geo=geo, trafik=""))

    if not terimler and hatalar:
        raise OneriHatasi(f"{geo}: {len(hatalar)} tohumun tamamı başarısız — {hatalar[0]}")
    return terimler


def isle(
    veri_yolu: Path,
    *,
    pazarlar: tuple[str, ...] | None = None,
    terim_getir=None,
    makale_bul=None,
) -> gtrends.IslemeSonucu:
    """Öneri terimlerini DW-55 borusuna verir.

    `tiktok.isle` ile aynı desen (ADR-0010): yazma ve sınıflandırma kodu
    kopyalanmıyor, `gtrends.isle` kendi terim getiricisiyle yeniden
    kullanılıyor.
    """
    pazarlar = pazarlar or gtrends.bosluk.hedef_pazarlar()
    return gtrends.isle(
        veri_yolu,
        pazarlar=pazarlar,
        terim_getir=terim_getir or terimleri_cek,
        makale_bul=makale_bul,
        geo_kodlari={p: GEO_KODLARI.get(p, ()) for p in pazarlar},
    )
