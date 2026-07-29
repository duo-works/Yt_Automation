"""Konu sınıflandırma — Wikidata tipleriyle, dile bakmadan.

Neden anahtar kelime değil: kategori ve başlık kalıpları her dilde farklı
(`Kategori:` / `Category:` / `تصنيف:`). Altı dil için altı liste yazmak ve
bakmak sürdürülemez; ilk yanlış eşleşme de sessizce yanlış sınıf üretir.

Wikidata bunu çözüyor. Her makalenin dil-bağımsız bir kimliği (`Q12560`) ve
tip iddiaları var:

    Osmanlı İmparatorluğu → P31: Q3024240 (tarihi ülke), Q48349 (imparatorluk)
    Battle of Hastings    → P31: Q178561 (muharebe)
    Yeni Parti (2026)     → P31: Q7278   (siyasi parti)  → elenir

Aynı kimlikler her dilde aynı. Ücretsiz, deterministik, tekrarlanabilir.

**Sınır:** `Q5` (insan) tek başına bir şey söylemiyor — Atatürk de bir insan,
güncel bir futbolcu da. Bu tür kayıtlar `belirsiz` işaretlenir ve LLM katmanına
(DW-30) devredilir. Amaç LLM'i ortadan kaldırmak değil, ona giden kuyruğu
küçültmek.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
KULLANICI_AJANI = "duo-works-yt-automation/0.1 (https://github.com/duo-works/Yt_Automation)"

# Toplu sorgu sınırı — her iki API de tek çağrıda 50 kimlik kabul ediyor.
TOPLU_SINIR = 50

# Tip kimlikleri 2026-07-29'da Wikidata'dan tek tek doğrulandı; etiketler
# yorumlarda duruyor ki bir daha kimse ezberden kontrol etmek zorunda kalmasın.
TARIH_TIPLERI: dict[str, str] = {
    "Q3024240": "tarihi ülke",
    "Q178561": "muharebe",
    "Q198": "savaş",
    "Q13418847": "tarihi olay",
    "Q48349": "imparatorluk",
    "Q11514315": "tarihi dönem",
    "Q839954": "arkeolojik sit",
    "Q28171280": "antik medeniyet",
    "Q17524420": "tarihsel kavram",
}

BILIM_TIPLERI: dict[str, str] = {
    "Q336": "bilim",
    "Q413": "fizik",
    "Q395": "matematik",
    "Q11190": "tıp",
    "Q7205": "paleontoloji",
    "Q12136": "hastalık",
    "Q11173": "kimyasal bileşik",
}

# Bu tipler tarih/bilim olma ihtimalini **dışlıyor**: film, albüm, oyun,
# siyasi parti. Liste tepesinin çoğu bunlar oluyor (güncel dizi, yeni albüm).
DISLANAN_TIPLERI: dict[str, str] = {
    "Q11424": "film",
    "Q482994": "albüm",
    "Q7889": "video oyunu",
    "Q2743": "müzikal",
    "Q7278": "siyasi parti",
    "Q571": "kitap",
}

# Tek başına karar verdirmeyen tipler — LLM'e gider.
BELIRSIZ_TIPLERI: dict[str, str] = {
    "Q5": "insan",
    "Q1190554": "olay",
    "Q4164871": "makam",
}

# --- Kişiler ------------------------------------------------------------
#
# İlk canlı koşumda 400 makalenin 193'ü `Q5` (insan) çıktı — belirsizlerin
# neredeyse tamamı. Wikipedia'nın günlük listesi ağırlıklı olarak kişilerden
# oluşuyor ve `Q5` tek başına Fatih Sultan Mehmet'i Cristiano Ronaldo'dan
# ayırmıyor. Hepsini LLM'e göndermek kuyruğu anlamsız büyütürdü.
#
# İki ücretsiz sinyal çözüyor: **ölüm tarihi** ve **meslek**.
#
#     Mehmed II   ö. 1481  · hükümdar      → tarih
#     Einstein    ö. 1955  · bilim insanı  → bilim
#     Ronaldo     yaşıyor  · futbolcu      → diğer

OLUM_TARIHI = "P570"
DOGUM_TARIHI = "P569"
MESLEK = "P106"

# Bu kimlikler 2026-07-29'da Wikidata'dan doğrulandı.
BILIM_MESLEKLERI: dict[str, str] = {
    "Q901": "bilim insanı",
    "Q170790": "matematikçi",
    "Q169470": "fizikçi",
    "Q593644": "kimyager",
    "Q864503": "biyolog",
    "Q11063": "astronom",
}

TARIH_MESLEKLERI: dict[str, str] = {
    "Q1097498": "yönetici",
    "Q116": "hükümdar",
    "Q189290": "subay",
    "Q47064": "asker",
    "Q201788": "tarihçi",
}

# ⚠️ Bu iki meslek listesi **bilinçli olarak dar**. İlk canlı koşumda geniş
# tuttuğumda liste bozuldu:
#
#   Graeme Garden  → "bilim" çıktı. Yaşayan İngiliz komedyen; tıp okuduğu için
#                    `Q39631` (hekim) etiketi taşıyor. Hekimlik mesleği bilim
#                    konusu olmayı garanti etmiyor — çıkarıldı.
#   Paul Newman    → "tarih" çıktı. Oyuncu.
#   Frida Kahlo    → "tarih" çıktı. Ressam.
#   Richard Wagner → "tarih" çıktı. Besteci.
#
# Son üçünün ortak sebebi "1975'ten önce ölen herkes tarihîdir" kuralıydı.
# Yanlıştı: ressam, besteci, oyuncu ölünce **tarih** konusu olmuyor, **kültür**
# konusu oluyor. Eşik kaldırıldı; kişinin tarih sayılması için mesleğinin
# doğrudan tarihle ilgili olması gerekiyor.
#
# `Q4964182` (filozof) da çıkarıldı: yaşayan filozoflar var ve felsefe tarih
# değil. Sınırda kalanlar `belirsiz` olup LLM'e (DW-30) gidiyor — bu doğru
# davranış, çünkü listeyi yanlış doldurmaktansa küçük tutmak yeğdir.


class WikidataHatasi(RuntimeError):
    """Wikidata'dan veri alınamadı."""


def _cek(url: str) -> dict:
    istek = urllib.request.Request(url, headers={"User-Agent": KULLANICI_AJANI})
    try:
        with urllib.request.urlopen(istek, timeout=30) as yanit:
            return json.load(yanit)
    except (urllib.error.HTTPError, OSError) as hata:
        raise WikidataHatasi(f"Wikidata erişilemedi: {hata}") from None


def _gruplar(ogeler: list[str], boyut: int = TOPLU_SINIR):
    for i in range(0, len(ogeler), boyut):
        yield ogeler[i : i + boyut]


def kimlikleri_getir(dil: str, basliklar: list[str]) -> dict[str, str]:
    """Makale başlığı → Wikidata kimliği (`Q...`). Toplu, 50'lik gruplar."""
    eslesme: dict[str, str] = {}
    for grup in _gruplar(basliklar):
        url = (
            f"https://{dil}.wikipedia.org/w/api.php?action=query&prop=pageprops"
            f"&ppprop=wikibase_item&format=json&redirects=1&titles="
            + urllib.parse.quote("|".join(grup), safe="|")
        )
        veri = _cek(url).get("query", {})
        # Yönlendirme varsa API normalleştirilmiş başlığı döndürüyor; istenen
        # başlıkla eşlemek için `redirects`/`normalized` haritalarını izliyoruz.
        takma: dict[str, str] = {}
        for anahtar in ("normalized", "redirects"):
            for kayit in veri.get(anahtar, []):
                takma[kayit["to"]] = takma.get(kayit["from"], kayit["from"])

        for sayfa in veri.get("pages", {}).values():
            qid = sayfa.get("pageprops", {}).get("wikibase_item")
            if not qid:
                continue
            baslik = sayfa.get("title", "")
            eslesme[takma.get(baslik, baslik)] = qid
    return eslesme


def _kimlikler(iddialar: dict, pid: str) -> list[str]:
    return [
        d["id"]
        for i in iddialar.get(pid, [])
        if isinstance(d := i.get("mainsnak", {}).get("datavalue", {}).get("value", {}), dict)
        and "id" in d
    ]


def _yil(iddialar: dict, pid: str) -> int | None:
    """Wikidata zaman değerinden yılı çıkarır (`+1481-05-03T00:00:00Z`).

    MÖ tarihler `-` ile başlıyor; onlar da tarihî sayıldığı için negatif yıl
    doğru sonuç veriyor.
    """
    for iddia in iddialar.get(pid, []):
        deger = iddia.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(deger, dict) and (zaman := deger.get("time")):
            try:
                return int(zaman[:5])
            except ValueError:
                continue
    return None


def varliklari_getir(kimlikler: list[str]) -> dict[str, dict]:
    """Wikidata kimliği → sınıflandırma için gereken alanlar.

    Tek çağrıda hem tipleri hem kişi alanlarını alıyoruz; ayrı sorgular
    Wikidata'ya iki kat yük bindirir ve aynı bilgiyi getirir.
    """
    sonuc: dict[str, dict] = {}
    for grup in _gruplar(kimlikler):
        url = f"{WIKIDATA_API}?action=wbgetentities&ids={'|'.join(grup)}&props=claims&format=json"
        for qid, varlik in _cek(url).get("entities", {}).items():
            iddialar = varlik.get("claims", {})
            sonuc[qid] = {
                "tipler": _kimlikler(iddialar, "P31") + _kimlikler(iddialar, "P279"),
                "meslekler": _kimlikler(iddialar, MESLEK),
                "olum": _yil(iddialar, OLUM_TARIHI),
                "dogum": _yil(iddialar, DOGUM_TARIHI),
            }
    return sonuc


def tipleri_getir(kimlikler: list[str]) -> dict[str, list[str]]:
    """Geriye dönük uyumluluk: yalnızca tip kimliklerini döndürür."""
    return {q: v["tipler"] for q, v in varliklari_getir(kimlikler).items()}


def _kisiyi_siniflandir(varlik: dict) -> str:
    """Kişiyi mesleğine ve ölüm tarihine göre ayırır.

    Meslek belirleyici, ölüm tarihi değil. "Yeterince eski ölen herkes
    tarihîdir" kuralı ilk canlı koşumda Frida Kahlo'yu ve Richard Wagner'ı
    tarih adayı yaptı — ölmüş bir ressam tarih konusu değil.
    """
    meslekler = set(varlik.get("meslekler") or [])
    olum = varlik.get("olum")

    if meslekler & BILIM_MESLEKLERI.keys():
        # Yaşayan bilim insanı da bilim konusudur — ölüm şartı aranmıyor.
        return "bilim"
    if meslekler & TARIH_MESLEKLERI.keys():
        # Hükümdar, subay, tarihçi. Yaşayan bir devlet başkanı güncel siyaset
        # olduğu için ölüm şartı burada aranıyor.
        return "tarih" if olum is not None else "diger"
    if olum is None:
        return "diger"  # yaşıyor ve mesleği ilgisiz → güncel kişi
    # Ölmüş ama mesleği ne tarih ne bilim: sanatçı, sporcu, iş insanı…
    # Karar LLM'e bırakılıyor; yanlış doldurmaktansa boş bırakmak yeğdir.
    return "belirsiz"


def siniflandir(tipler: list[str], varlik: dict | None = None) -> str:
    """Sınıf üretir: `tarih` | `bilim` | `diger` | `belirsiz`.

    Sıra önemli. Dışlama **önce** geliyor: "Gladyatör (film)" hem tarihî bir
    konuyu işler hem filmdir, ama bizim için filmdir. Tarihi önce kontrol
    etseydik kurgu eserler tarih diye sınıflanırdı.

    `varlik` verilirse kişiler (`Q5`) meslek ve ölüm tarihine göre ayrılır;
    verilmezse `belirsiz` kalır ve LLM katmanına (DW-30) gider.
    """
    kume = set(tipler)
    if kume & DISLANAN_TIPLERI.keys():
        return "diger"
    if kume & TARIH_TIPLERI.keys():
        return "tarih"
    if kume & BILIM_TIPLERI.keys():
        return "bilim"
    if "Q5" in kume and varlik:
        return _kisiyi_siniflandir(varlik)
    if kume & BELIRSIZ_TIPLERI.keys():
        return "belirsiz"
    return "diger"
