"""Kaynak dosyası — bir adayın referans, olgu ve görsel tabanı.

Hattın geri kalanı **konu seçiyor**. Bu modül seçilen konunun neye
dayanacağını üretiyor. PRD'nin YPP karşı önlemlerinin birincisi:

    Her videonun altında gerçek bir kaynak — veri, olay, arşiv. LLM'in
    kendi kafasından ürettiği dolgu metin, politikanın hedeflediği şeyin
    ta kendisi.

Üç çekici, üçü de ücretsiz:

    referans → makalenin dış bağlantıları (British Museum, arşiv, akademik)
    olgu     → Wikidata'nın yapılandırılmış iddiaları (tarih, yer, statü)
    gorsel   → Commons dosyaları, **lisans ve atıfla birlikte**

Kaynaklar `qid` üzerinden anahtarlanıyor, `(dil, baslik)` üzerinden değil:
aynı konu her dilde ayrı makale ama kaynaklar ortak. Bir kez çekilir.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import depo
from . import konu, wikipedia

# Videoda işe yarayan iddia türleri. Wikidata'da yüzlerce özellik var ama
# çoğu kimlik numarası (VIAF, GND, Freebase, Britannica…) — anlatıya girmez,
# bu yüzden allowlist tutuluyor, blocklist değil.
#
# ⚠️ İlk canlı koşumda liste **yer ve yapı odaklıydı** ve kişilerde sıfır olgu
# üretti: Cleopatra 1, Paul Newman 0, Hermann Göring 0. Wikipedia'nın günlük
# listesinin çoğu kişi olduğu için bu, hattın büyük kısmını kaynaksız
# bırakıyordu. Doğum/ölüm/meslek grubu o koşumdan sonra eklendi.
#
# Etiketler 2026-07-29'da Wikidata'dan tek tek doğrulandı.
OLGU_OZELLIKLERI: dict[str, str] = {
    # Zaman
    "P571": "ortaya çıkışı",
    "P576": "sona erişi",
    "P585": "tarihi",
    "P580": "başlangıcı",
    "P582": "bitişi",
    "P575": "keşif tarihi",
    # Yer ve yapı
    "P17": "ülkesi",
    "P276": "konumu",
    "P625": "koordinatları",
    "P1435": "miras statüsü",
    "P2044": "rakımı",
    "P1082": "nüfusu",
    "P361": "parçası olduğu",
    "P527": "kapsadığı",
    # Kişi — listenin çoğu kişi olduğu için bu grup belirleyici
    "P569": "doğum tarihi",
    "P570": "ölüm tarihi",
    "P19": "doğum yeri",
    "P20": "ölüm yeri",
    "P509": "ölüm nedeni",
    "P106": "mesleği",
    "P27": "vatandaşlığı",
    "P39": "üstlendiği görev",
    "P69": "öğrenim gördüğü yer",
    "P166": "aldığı ödül",
    "P800": "önemli eseri",
    "P607": "katıldığı çatışma",
    "P1399": "mahkûm edildiği suç",
    # İlişki ve bağlam
    "P155": "öncesinde",
    "P156": "sonrasında",
    "P793": "önemli olayı",
    "P138": "adını veren",
    "P170": "yaratıcısı",
    "P50": "yazarı",
    "P61": "kâşifi",
}

# Toplayıcı ve arşiv siteleri: referans listesinde çok yer kaplıyor ama
# birincil kaynak değiller. Kitap/makale bağlantıları buradan hariç.
ZAYIF_ALANLAR = frozenset(
    {"web.archive.org", "wikipedia.org", "wikimedia.org", "wikidata.org", "doi.org"}
)

GORSEL_UZANTILARI = (".jpg", ".jpeg", ".png", ".svg", ".tif", ".tiff")

# Lisansı bilinmeyen görsel kullanılmaz. Varsayılan "muhtemelen serbesttir"
# değil — telif riski PRD'de işaretli ve görsel tek tek kontrol edilmiyor.
BELIRSIZ_LISANSLAR = frozenset({"", "?", "unknown", "bilinmiyor"})

_ETIKET = re.compile(r"<[^>]+>")
_KIMLIK = re.compile(r"Q\d+")


@dataclass
class KaynakSonucu:
    qid: str = ""
    referans: int = 0
    olgu: int = 0
    gorsel: int = 0
    elenen_gorsel: int = 0
    hatalar: list[str] = field(default_factory=list)

    @property
    def yeterli(self) -> bool:
        """Kabul ölçütü: en az 3 referans ve 5 olgu.

        Altındaysa konu videoya dönüşmemeli — dayanaksız anlatı tam olarak
        YPP'nin 1. kategorisi.
        """
        return self.referans >= 3 and self.olgu >= 5

    def ozet(self) -> str:
        satir = f"{self.qid}: {self.referans} referans · {self.olgu} olgu · {self.gorsel} görsel"
        if self.elenen_gorsel:
            satir += f" ({self.elenen_gorsel} görsel lisanssız, elendi)"
        if not self.yeterli:
            satir += " · ⚠️ YETERSİZ"
        return satir


def metne_cevir(ham: str) -> str:
    """Commons `Artist` alanı HTML içeriyor; atıf metni düz olmalı."""
    return " ".join(_ETIKET.sub(" ", ham or "").split())


def _alan(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _zayif_mi(alan: str) -> bool:
    """Alt alan adlarını da kapsar.

    Tam eşleşme yetmiyor: `wikipedia.org` listede olsa da referanslar
    `en.wikipedia.org` / `tr.wikipedia.org` olarak geliyor ve elemeden
    geçiyorlardı. Wikipedia'nın kendisini kaynak diye göstermek, kaynak
    göstermemekle aynı şey.
    """
    return any(alan == z or alan.endswith("." + z) for z in ZAYIF_ALANLAR)


def referanslari_getir(dil: str, baslik: str, adet: int = 12) -> list[str]:
    """Makalenin dış bağlantıları — birincil kaynak adayları.

    Toplayıcılar ve wiki iç bağlantıları eleniyor: bir arşiv linki kaynağın
    kendisi değil, kopyası. Kalanlar müze, üniversite, kurum siteleri oluyor.
    """
    url = (
        f"https://{dil}.wikipedia.org/w/api.php?action=query&prop=extlinks"
        f"&ellimit=100&format=json&redirects=1&titles=" + urllib.parse.quote(baslik, safe="")
    )
    try:
        veri = wikipedia._cek(url).get("query", {})
    except wikipedia.WikipediaHatasi:
        return []

    gorulen: set[str] = set()
    sonuc: list[str] = []
    for sayfa in veri.get("pages", {}).values():
        for bag in sayfa.get("extlinks", []):
            adres = bag.get("*", "")
            alan = _alan(adres)
            if not alan or _zayif_mi(alan) or alan in gorulen:
                continue
            # Alan başına bir bağlantı: aynı sitenin on sayfası tek kaynak.
            gorulen.add(alan)
            sonuc.append(adres)
            if len(sonuc) >= adet:
                return sonuc
    return sonuc


def etiketleri_coz(kimlikler: list[str], dil: str = "tr") -> dict[str, str]:
    """Wikidata kimliklerini okunabilir etiketlere çevirir.

    İlk canlı koşumda olgular `ölüm nedeni: Q114953` gibi çıktı — teknik
    olarak doğru ama üretim tarafına gönderilemez. Toplu çözülüyor: 50
    kimlik tek çağrıda, yani konu başına bir istek.

    Türkçe etiket yoksa İngilizceye düşülüyor; ikisi de yoksa kimlik kalıyor.
    """
    if not kimlikler:
        return {}
    etiketler: dict[str, str] = {}
    for i in range(0, len(kimlikler), 50):
        grup = kimlikler[i : i + 50]
        url = (
            f"{konu.WIKIDATA_API}?action=wbgetentities&ids={'|'.join(grup)}"
            f"&props=labels&languages={dil}|en&format=json"
        )
        try:
            varliklar = konu._cek(url).get("entities", {})
        except konu.WikidataHatasi:
            continue
        for qid, varlik in varliklar.items():
            etiket = varlik.get("labels", {})
            if deger := (etiket.get(dil) or etiket.get("en") or {}).get("value"):
                etiketler[qid] = deger
    return etiketler


def _olgu_degeri(deger) -> str | None:
    """Wikidata değerini okunabilir metne çevirir.

    Varlık referansları (`Q...`) burada ham kalıyor; `olgulari_getir`
    hepsini tek çağrıda toplu çözüyor.
    """
    if isinstance(deger, str):
        return deger
    if not isinstance(deger, dict):
        return None
    if "id" in deger:
        return deger["id"]
    if zaman := deger.get("time"):
        # +1450-01-01T00:00:00Z → 1450, -0500-...  → MÖ 500
        # Gün/ay çoğu tarihî kayıtta anlamsız (çoğu zaten 01-01).
        # ⚠️ Baştaki sıfırları kırparken işareti korumak gerekiyor: ilk
        # denemede `-0500` → `-050` çıktı, yani MÖ tarihler bozuluyordu.
        yil = zaman[1:5].lstrip("0") or "0"
        return f"MÖ {yil}" if zaman.startswith("-") else yil
    if "latitude" in deger:
        return f"{deger['latitude']:.4f}, {deger['longitude']:.4f}"
    if "amount" in deger:
        return str(deger["amount"]).lstrip("+")
    return None


def olgulari_getir(qid: str) -> list[tuple[str, str]]:
    """Wikidata iddiaları → `(etiket, değer)` çiftleri."""
    url = f"{konu.WIKIDATA_API}?action=wbgetentities&ids={qid}&props=claims&format=json"
    try:
        varlik = konu._cek(url).get("entities", {}).get(qid, {})
    except konu.WikidataHatasi:
        return []

    olgular: list[tuple[str, str]] = []
    for pid, etiket in OLGU_OZELLIKLERI.items():
        for iddia in varlik.get("claims", {}).get(pid, []):
            ham = iddia.get("mainsnak", {}).get("datavalue", {}).get("value")
            if (deger := _olgu_degeri(ham)) is not None:
                olgular.append((etiket, deger))
                break  # Özellik başına bir değer yeter; listeyi şişirme.

    # Ham kimlikleri okunabilir hale getir — tek toplu çağrı.
    kimlikler = [d for _, d in olgular if _KIMLIK.fullmatch(d)]
    cozum = etiketleri_coz(kimlikler)
    return [(e, cozum.get(d, d)) for e, d in olgular]


def gorselleri_getir(dil: str, baslik: str, adet: int = 4) -> list[dict]:
    """Commons görselleri — **lisansı doğrulanmış olanlar**.

    Lisansı belirsiz görsel döndürülmüyor. Bu bir kolaylık filtresi değil:
    telif riski PRD'de işaretli ve görseller tek tek elle kontrol edilmiyor.
    """
    url = (
        f"https://{dil}.wikipedia.org/w/api.php?action=query&prop=images"
        f"&imlimit=20&format=json&redirects=1&titles=" + urllib.parse.quote(baslik, safe="")
    )
    try:
        veri = wikipedia._cek(url).get("query", {})
    except wikipedia.WikipediaHatasi:
        return []

    dosyalar = [
        oge["title"]
        for sayfa in veri.get("pages", {}).values()
        for oge in sayfa.get("images", [])
        if oge.get("title", "").lower().endswith(GORSEL_UZANTILARI)
    ][: adet * 3]  # Lisans elemesi bazılarını düşürecek, fazladan al.
    if not dosyalar:
        return []

    bilgi_url = (
        f"https://{dil}.wikipedia.org/w/api.php?action=query&prop=imageinfo"
        f"&iiprop=url|extmetadata&format=json&titles="
        + urllib.parse.quote("|".join(dosyalar), safe="|")
    )
    try:
        bilgi = wikipedia._cek(bilgi_url).get("query", {})
    except wikipedia.WikipediaHatasi:
        return []

    sonuc: list[dict] = []
    for sayfa in bilgi.get("pages", {}).values():
        ust = (sayfa.get("imageinfo") or [{}])[0].get("extmetadata", {})
        lisans = metne_cevir(ust.get("LicenseShortName", {}).get("value", ""))
        if lisans.lower() in BELIRSIZ_LISANSLAR:
            continue
        sonuc.append(
            {
                "dosya": sayfa.get("title", ""),
                "lisans": lisans,
                "atif": metne_cevir(ust.get("Artist", {}).get("value", "")),
            }
        )
        if len(sonuc) >= adet:
            break
    return sonuc


def _yaz(baglanti, qid: str, tur: str, deger: str, simdi: str, **ek) -> None:
    baglanti.execute(
        """
        INSERT INTO kaynak (qid, tur, deger, etiket, atif, lisans, cekilme)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(qid, tur, deger) DO UPDATE SET
            lisans = excluded.lisans, atif = excluded.atif
        """,
        (qid, tur, deger, ek.get("etiket"), ek.get("atif"), ek.get("lisans"), simdi),
    )


def cek(yol: Path, dil: str, baslik: str, qid: str) -> KaynakSonucu:
    """Bir adayın kaynak dosyasını çeker ve depoya yazar."""
    sonuc = KaynakSonucu(qid=qid)
    simdi = datetime.now(UTC).isoformat()

    referanslar = referanslari_getir(dil, baslik)
    olgular = olgulari_getir(qid)
    gorseller = gorselleri_getir(dil, baslik)

    with depo.yazma_islemi(yol) as baglanti:
        for adres in referanslar:
            _yaz(baglanti, qid, "referans", adres, simdi)
            sonuc.referans += 1
        for etiket, deger in olgular:
            _yaz(baglanti, qid, "olgu", deger, simdi, etiket=etiket)
            sonuc.olgu += 1
        for g in gorseller:
            _yaz(baglanti, qid, "gorsel", g["dosya"], simdi, atif=g["atif"], lisans=g["lisans"])
            sonuc.gorsel += 1
    return sonuc


def cekilmemis_adaylar(yol: Path, limit: int = 20) -> list[dict]:
    """Kaynağı henüz çekilmemiş adaylar — en çok okunanlar önce.

    Yalnızca `tarih`/`bilim` sınıfı: 544 `diger` için kaynak çekmek anlamsız.
    """
    baglanti = depo.baglan(yol)
    try:
        return [
            dict(s)
            for s in baglanti.execute(
                """
                SELECT m.dil, m.baslik, m.qid, MAX(o.okunma) AS okunma
                FROM makale m
                JOIN okunma o ON o.dil = m.dil AND o.baslik = m.baslik
                WHERE m.sinif IN ('tarih', 'bilim')
                  AND m.qid IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM kaynak k WHERE k.qid = m.qid)
                GROUP BY m.dil, m.baslik
                ORDER BY okunma DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    finally:
        baglanti.close()


def dosyayi_oku(yol: Path, qid: str) -> dict[str, list[dict]]:
    """Bir konunun kaynak dosyası, türe göre gruplanmış."""
    baglanti = depo.baglan(yol)
    try:
        satirlar = baglanti.execute(
            "SELECT tur, deger, etiket, atif, lisans FROM kaynak WHERE qid = ? ORDER BY tur, deger",
            (qid,),
        ).fetchall()
    finally:
        baglanti.close()

    dosya: dict[str, list[dict]] = {"referans": [], "olgu": [], "gorsel": []}
    for s in satirlar:
        dosya.setdefault(s["tur"], []).append(dict(s))
    return dosya


def json_disa_aktar(yol: Path, qid: str) -> str:
    """Kaynak dosyasını JSON'a çevirir — üretim hattının girdisi."""
    return json.dumps(dosyayi_oku(yol, qid), ensure_ascii=False, indent=2)
