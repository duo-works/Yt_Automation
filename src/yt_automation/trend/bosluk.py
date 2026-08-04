"""Talep-arz boşluğu — huninin merkez parçası.

Cevapladığı soru "ne popüler?" değil, **"talep var ama arz zayıf nerede?"**

Sebebi ölçülmüş bir gerçek: trend çartı zaten kitlesi olan büyük kanalların
aldığı sonucu gösteriyor. Sıfır aboneli bir kanal aynı konuyu yaptığında o
kitleyi miras almıyor. Yeni kanal için doğru soru arz boşluğu.

## Huni

    1. ADAY ÜRETİMİ   ücretsiz   Wikipedia okunma sıçramaları (DW-34)
    2. ELEME          ücretsiz   sınıf, tekrar, daha önce sondalanmış
    3. ARZ ÖLÇÜMÜ     102 birim  search.list (100) + videos.list + channels.list
    4. SKORLAMA       ücretsiz   log ölçekte talep − arz

`search.list` 100 birim olduğu için **aday üretmek** için kullanılamaz,
yalnızca en iyi adayları **doğrulamak** için. Ücretsiz katmanlar huninin
ağzını besliyor.

## Sondaj başına 102 birim, 101 değil

Görev 101 birim öngörüyordu (search + videos). Bir birim daha eklendi:
`channels.list`. Gerekçe, görevin kendi "arz gücü neyle ölçülür" listesinde
**kanal büyüklüğü** de var ve `videos.list` abone sayısı döndürmüyor. Mevcut
sonuçların hepsi milyonluk kanallardansa niş kazanılmaz; küçük kanallardansa
kazanılır — bu ayrım bir birime değer.

## `totalResults` kullanılmıyor

`search.list` bir `totalResults` döndürüyor ama Google onu **tahmini** veriyor
ve gerçekten yanıltıcı. Arz, dönen videoların kendi istatistiklerinden
ölçülüyor: izlenme, yaş, kanal büyüklüğü ve konuyla gerçek alakası.

## Alaka ölçümü sözlüksel ve bu yönde bilinçli hata yapıyor

Bir videonun konuyla alakalı olup olmadığı başlıktaki belirteç örtüşmesiyle
ölçülüyor — LLM'e sormak doğru sonuç verirdi ama her sondaja bir çağrı ekler.

Eşik gevşek (belirteçlerin yarısı) çünkü **hata yönü asimetrik**:

- Alakasız videoyu alakalı saymak → arz olduğundan güçlü görünür → skor düşer
  → gerçek bir fırsatı atlarız. **Bedeli: kaçırılmış video.**
- Alakalı videoyu alakasız saymak → arz zayıf görünür → skor şişer → doymuş
  bir nişe video çekeriz. **Bedeli: harcanmış üretim emeği.**

İkincisi çok daha pahalı, o yüzden gevşek eşik doğru taraf.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import log10
from pathlib import Path
from statistics import median

from .. import depo, kota
from . import hiz

ARAMA = "search.list"
ISTATISTIK = "videos.list"
KANAL = "channels.list"

# Bir sondajın tam maliyeti. Arama boş dönerse 100'de kalır.
SONDAJ_MALIYETI = kota.MALIYET[ARAMA] + kota.MALIYET[ISTATISTIK] + kota.MALIYET[KANAL]

# Boşluk sondajlarının günlük payı.
#
#   yükleme (2 video)   3.302   ← dokunulmaz, `rezerve` ile korunuyor
#   trend çartı         2.500   ← bolge.TREND_KOTA_TAVANI
#   niş kanal izleme      500   ← nis.NIS_KOTA_TAVANI (kanal başına 2 birim)
#   boşluk sondajı      3.000   ← burası, ~29 sondaj
#   ────────────────────────────
#   pay toplamı         9.302 / 10.000
#
# Günde 1 video için 29 sondaj fazlasıyla yeterli. Ayrı bir `surec` etiketi
# kullanılıyor ("bosluk"): çart toplayıcısıyla aynı tavanı paylaşsalardı
# sondajlar çartı açlıktan öldürebilirdi.
SONDAJ_KOTA_TAVANI = 3_000
SUREC = "bosluk"

MAKSIMUM_SONUC = 50  # search.list tek sayfada en fazla bu kadar; maliyet aynı

# Belirteç örtüşme eşiği ve anlamsız belirteç uzunluğu. 4 karakterden kısa
# olanlar atılıyor: "of", "the", "ve", "de", "bir" gibi işlev sözcükleri her
# başlıkta var ve alaka hakkında hiçbir şey söylemiyor.
ALAKA_ESIGI = 0.5
ASGARI_BELIRTEC = 4

# Skor ağırlıkları. Hepsi log10 ölçekte: 10 kat fark = 1 puan. Böylece 500
# izlenmeli bir video ile 5.000.000 izlenmeli bir video arasındaki mesafe
# doğrusal ölçekte olduğu gibi her şeyi ezmiyor.
#
# ⚠️ Bu ağırlıklar **kalibre edilmedi.** Sentetik iyi/kötü boşluk örnekleriyle
# ayrımın çalıştığı doğrulandı; gerçek sonuçlarla eşleştirme yapılmadı. Değişme
# olasılığı yüksek olan tek yer burası, o yüzden skor diske yazılmıyor.
IZLENME_AGIRLIGI = 1.0
ALAKALI_SAYI_AGIRLIGI = 0.5
ABONE_AGIRLIGI = 0.5
YAS_AGIRLIGI = 0.5  # eski içerik = zayıf arz, bu yüzden **çıkarılıyor**

# --- Kapılar (DW-51) -----------------------------------------------------
#
# Huni bunlardan önce **hiçbir günü boş geçiremiyordu**: skora göre sıralayıp
# ilk N'i koşulsuz gönderiyordu. PRD'nin pazarlık dışı saydığı dördüncü karşı
# önlem bunu doğrudan yasaklıyor — "üretilen her çıktıyı koşulsuz yayınlayan
# sistem slop üretir".
#
# ⚠️ Aşağıdaki iki eşik **sonuçla kalibre edilmedi ve bugün edilemez**: henüz
# tek video yayınlanmadı, yani "bu aday tuttu mu" diye sorulabilecek bir gerçek
# yok. Değerler 2026-08-03'te ölçülmüş 73 sondajın **dağılımından** seçildi.
# Yukarıdaki ağırlıklar gibi bunlar da değişmesi beklenen yerler.

# Bir dilin tabanı için gereken asgari ölçüm. `nis._taban`'ın gerekçesiyle
# aynı: yetersiz örneklemden çıkan taban güvenilmez, yanlış taban yanlış zirve
# demek. Altında kalan dil sıralanmıyor — ama sessizce değil, CLI sayıyı basar.
ASGARI_TABAN_ORNEK = 5

# Göreli kapı: aday kendi dilinin olağanından kaç MAD daha iyi olmalı.
#
# Neden dile göre: skorun mutlak seviyesi fırsatı değil **pazar büyüklüğünü**
# kodluyor. 2026-08-03 ölçümünde İngilizce arz medyanı 1.296.193 izlenme iken
# Almanca 58.040, Hintçe talep medyanı 292 iken Almanca 4.775. Küresel tek bir
# kesme bu yüzden dil seçiyor, aday değil: 0,0 eşiğinde geçen 3 adayın 3'ü de
# Almanca'ydı. `skorla()`'nın docstring'i "talep tarafına bir ölçek katsayısı
# gerekiyor" diyor; dil bazında ortalamak o katsayıyı pazar başına ampirik
# kestirmektir.
ESIK_KALIBRE = 2.0

# Mutlak kapı: zirve günlük Wikipedia okunması.
#
# Göreli kapı tek başına yetmiyor ve sebebi yapısal: her dilin en iyisi tanım
# gereği kendi medyanının üstünde, yani salt göreli bir kapı **hiçbir günü boş
# geçiremez** — çözmesi istenen sorunun ta kendisi. Ölçümde z ≥ 2,0'ı geçen üç
# aday mutlak olarak kötüydü: günde 328, 419 ve 596 okunma, üçü de 50/50
# alakalı (YouTube'un döndürdüğü her sonuç konu üzerinde, yani boşluk yok).
# Yalnızca kendi dillerinin tabanı daha kötü olduğu için geçiyorlardı.
#
# Eşik skor değil **yorumlanabilir birim**: günde 1.000 kişinin okumadığı bir
# konu için video yapılmaz, dilinin tabanı ne olursa olsun. Gözlenen medyanın
# (1.211) hemen altında.
ASGARI_TALEP = 1_000

# Red gerekçeleri — CLI bunları sayıp basıyor. Sessiz eleme, sessiz
# başarısızlığın kardeşi: DW-47 aynı dersi zamanlama tarafında verdi.
RED_OLCUM = "ölçüm geçersiz"
RED_TABAN = f"dil tabanı güvenilmez (< {ASGARI_TABAN_ORNEK} ölçüm)"
RED_KALIBRE = f"dilinin olağanına göre yeterince iyi değil (< {ESIK_KALIBRE:.1f} MAD)"
RED_TALEP = f"talep eşiğin altında (< {ASGARI_TALEP:,} okunma/gün)"

# Sondaj sorgusundan atılacak Wikipedia ayrım eki: "Cleopatra_(1963_film)".
# Kimse böyle aramıyor; parantez içi Wikipedia'nın kendi konvansiyonu.
_AYRIM_EKI = re.compile(r"\s*\([^)]*\)\s*$")
_BELIRTEC_AYIRICI = re.compile(r"[^0-9a-z]+")

# NFKD'nin **ayrıştırmadığı** harfler. Aksanlı harflerin çoğu (ü → u + ¨)
# ayrışıyor ama bunlar ayrı birer harf olduğu için ayrışmıyor; tablo olmadan
# belirteç ayırıcı sayılıp sözcüğü ortadan kesiyorlar.
#
# ⚠️ Bu tablo Türkçe yüzünden zorunlu: `ı` (noktasız i) ayrışmıyor ve
# "Osmanlı" → "osmanl" oluyordu. Türkçe birincil hedef dil olduğu için
# sessizce yanlış eşleşen bir alaka ölçümü kabul edilemez. Kalanlar aynı
# sınıftan, sık karşılaşılan Avrupa harfleri; yeni dil eklendikçe uzar.
_AYRISMAYAN = str.maketrans(
    {
        "ı": "i",  # Türkçe
        "ø": "o",  # Danca, Norveççe
        "ł": "l",  # Lehçe
        "đ": "d",  # Hırvatça, Vietnamca
        "ð": "d",  # İzlandaca
        "þ": "th",
        "æ": "ae",
        "œ": "oe",
        "ħ": "h",
        "ŧ": "t",
    }
)


class BoslukHatasi(RuntimeError):
    """Sondaj yapılamadı."""


def sorguya_cevir(baslik: str) -> str:
    """Wikipedia başlığını insanların gerçekten arayacağı sorguya çevirir."""
    return _AYRIM_EKI.sub("", baslik.replace("_", " ")).strip()


def _sadelestir(metin: str) -> str:
    """Aksanları düşürür ve küçük harfe indirir.

    Diller arası çalışması gerekiyor: "Süleyman" ile "Suleyman", "Osmanlı" ile
    "Osmanli" aynı belirteç sayılmalı. İki aşama: NFKD ayrışan aksanları
    (ü → u + ¨) hallediyor, `_AYRISMAYAN` tablosu ayrışmayanları.
    """
    sade = unicodedata.normalize("NFKD", metin.casefold().translate(_AYRISMAYAN))
    return "".join(k for k in sade if not unicodedata.combining(k))


def belirtecler(metin: str) -> set[str]:
    """Alaka karşılaştırmasına girecek anlamlı belirteçler."""
    return {b for b in _BELIRTEC_AYIRICI.split(_sadelestir(metin)) if len(b) >= ASGARI_BELIRTEC}


def alakali_mi(sorgu_belirtecleri: set[str], baslik: str) -> bool:
    """Videonun başlığı konuyu gerçekten karşılıyor mu.

    Yalnızca **başlığa** bakılıyor, açıklamaya değil: açıklamalar etiket ve
    kalıp metinle dolu ve neredeyse her sorguyu eşleştirir. Bir izleyici de
    başlığa bakarak tıklıyor.

    Sorguda anlamlı belirteç yoksa (çok kısa başlık) video alakalı sayılıyor —
    yukarıdaki asimetriye uygun taraf.
    """
    if not sorgu_belirtecleri:
        return True
    ortak = sorgu_belirtecleri & belirtecler(baslik)
    return len(ortak) / len(sorgu_belirtecleri) >= ALAKA_ESIGI


def _tam_sayi(deger) -> int | None:
    try:
        return int(deger)
    except (TypeError, ValueError):
        return None


def _medyan(degerler: list[int]) -> int | None:
    return round(median(degerler)) if degerler else None


@dataclass
class ArzOlcumu:
    """Bir konuda YouTube'da ne olduğunun ham ölçümü — skor yok, olgu var."""

    qid: str
    dil: str
    sorgu: str
    an: str
    donen: int = 0
    alakali: int = 0
    medyan_izlenme: int | None = None
    ust_izlenme: int | None = None
    medyan_yas_gun: int | None = None
    medyan_abone: int | None = None
    harcanan: int = 0

    @property
    def gecerli(self) -> bool:
        """Arama hiç video döndürmediyse ölçüm anlamlı değil.

        Bu ayrım kritik: "50 sonuç döndü, hiçbiri alakalı değil" gerçek bir
        boşluk. "Hiç sonuç dönmedi" ise sorgunun bozuk olduğunun işareti —
        ikisini karıştırmak bize var olmayan bir fırsat gösterir.
        """
        return self.donen > 0

    def ozet(self) -> str:
        if not self.gecerli:
            return "arama boş döndü — sorgu şüpheli"
        parcalar = [f"{self.alakali}/{self.donen} alakalı"]
        if self.medyan_izlenme is not None:
            parcalar.append(f"medyan {self.medyan_izlenme:,} izlenme")
        if self.medyan_yas_gun is not None:
            parcalar.append(f"medyan yaş {self.medyan_yas_gun:,} gün")
        if self.medyan_abone is not None:
            parcalar.append(f"medyan {self.medyan_abone:,} abone")
        return " · ".join(parcalar)


def skorla(olcum: ArzOlcumu, talep: int) -> float | None:
    """Talep-arz boşluğu skoru: yüksek = iyi boşluk.

    `log10(talep) − arz_gucu`, hepsi log ölçekte.

    ⚠️ **Skor bir sıralamadır, eşik değildir.** İlk canlı sondajda (3 aday,
    2026-07-30) ölçülen gerçek:

        Great Zimbabwe        -1,60   49/50 alakalı, medyan   22.125 izlenme
        A. P. J. Abdul Kalam  -3,93   50/50 alakalı, medyan 1.462.458 izlenme
        Cleopatra             -3,98   47/50 alakalı, medyan 1.129.928 izlenme

    Sıralama doğru — Great Zimbabwe gerçekten en az doymuş olan. Ama **üçü de
    negatif**, çünkü iki ölçek karşılaştırılıyor: Wikipedia'nın günlük okunması
    bu konularda 25 bin civarında (log10 ≈ 4,4) iken YouTube izlenmesi
    milyonlarda (log10 ≈ 6). İşaretin anlamlı olması için talep tarafına bir
    ölçek katsayısı gerekiyor ve o katsayı veriyle kalibre edilmeli.

    Bugün kullanılabilir olan: **adayları birbirine göre sıralamak.** "Skor
    artı, demek ki yap" çıkarımı henüz yapılamaz.

    Ölçüm geçersizse (`donen == 0`) `None` döner: sorgusu bozuk bir konuyu
    "arzı hiç yok" diye zirveye koymak, huninin en pahalı hatası olurdu.
    """
    if not olcum.gecerli:
        return None

    talep_puani = log10(1 + max(talep, 0))

    arz = IZLENME_AGIRLIGI * log10(1 + (olcum.medyan_izlenme or 0))
    arz += ALAKALI_SAYI_AGIRLIGI * log10(1 + olcum.alakali)
    arz += ABONE_AGIRLIGI * log10(1 + (olcum.medyan_abone or 0))
    # Eski içerik zayıf arz: 5 yıllık videolar öneri akışında dönmüyor ve
    # görüntüsü bayat. Yaş arzdan **düşülüyor**.
    arz -= YAS_AGIRLIGI * log10(1 + (olcum.medyan_yas_gun or 0))

    return talep_puani - arz


# --- Sondaj --------------------------------------------------------------


def _ara(istemci, sorgu: str, dil: str) -> list[dict]:
    """`search.list` — 100 birim, istatistik **döndürmez**.

    `part="snippet"` başlık için gerekli (alaka ölçümü oradan). İzlenme ve
    abone gelmediği için ikinci ve üçüncü çağrı şart.
    """
    yanit = (
        istemci.search()
        .list(
            part="snippet",
            q=sorgu,
            type="video",
            maxResults=MAKSIMUM_SONUC,
            relevanceLanguage=dil,
        )
        .execute()
    )
    return yanit.get("items", [])


def _istatistikleri_getir(istemci, video_kimlikleri: list[str]) -> dict[str, dict]:
    """`videos.list` — 50 kimliğe kadar tek çağrı, 1 birim."""
    yanit = (
        istemci.videos().list(part="snippet,statistics", id=",".join(video_kimlikleri)).execute()
    )
    return {oge["id"]: oge for oge in yanit.get("items", [])}


def _aboneleri_getir(istemci, kanal_kimlikleri: list[str]) -> dict[str, int | None]:
    """`channels.list` — 50 kimliğe kadar tek çağrı, 1 birim.

    Abone sayısı gizlenmiş olabiliyor; o kanallar `None` dönüyor ve medyana
    girmiyor. Sıfır saymak, büyük bir kanalı küçük göstermek olurdu.
    """
    yanit = istemci.channels().list(part="statistics", id=",".join(kanal_kimlikleri)).execute()
    cikti: dict[str, int | None] = {}
    for oge in yanit.get("items", []):
        istatistik = oge.get("statistics") or {}
        gizli = istatistik.get("hiddenSubscriberCount")
        cikti[oge["id"]] = None if gizli else _tam_sayi(istatistik.get("subscriberCount"))
    return cikti


def sondala(
    istemci,
    sayac: kota.KaliciSayac,
    *,
    qid: str,
    dil: str,
    baslik: str,
    an: datetime | None = None,
    rezerve: int | None = None,
) -> ArzOlcumu:
    """Tek bir konu için arz ölçümü. 102 birim (arama boşsa 100).

    Kota her çağrıdan **önce** düşülüyor: reddedilen istek de birim harcıyor.
    `rezerve` bir videoluk yükleme payını koruyor — araştırma hiçbir koşulda
    yayını bloke etmemeli.
    """
    an = an or datetime.now(UTC)
    sorgu = sorguya_cevir(baslik)
    olcum = ArzOlcumu(qid=qid, dil=dil, sorgu=sorgu, an=an.isoformat())
    rezerve = kota.video_basina_maliyet() if rezerve is None else rezerve

    sayac.harca(ARAMA, rezerve=rezerve)
    olcum.harcanan += kota.MALIYET[ARAMA]
    ogeler = _ara(istemci, sorgu, dil)
    olcum.donen = len(ogeler)
    if not ogeler:
        return olcum

    hedef = belirtecler(sorgu)
    alakali_kimlikler = [
        oge["id"]["videoId"]
        for oge in ogeler
        if oge.get("id", {}).get("videoId")
        and alakali_mi(hedef, (oge.get("snippet") or {}).get("title") or "")
    ]
    olcum.alakali = len(alakali_kimlikler)
    if not alakali_kimlikler:
        # Gerçek boşluk: 50 sonuç var, hiçbiri konuyu karşılamıyor. İkinci ve
        # üçüncü çağrıyı yapmak 2 birimi çöpe atmak olur.
        return olcum

    sayac.harca(ISTATISTIK, rezerve=rezerve)
    olcum.harcanan += kota.MALIYET[ISTATISTIK]
    ayrintilar = _istatistikleri_getir(istemci, alakali_kimlikler)

    izlenmeler: list[int] = []
    yaslar: list[int] = []
    kanallar: list[str] = []
    for ayrinti in ayrintilar.values():
        snippet = ayrinti.get("snippet") or {}
        izlenme = _tam_sayi((ayrinti.get("statistics") or {}).get("viewCount"))
        if izlenme is not None:
            izlenmeler.append(izlenme)
        yayin = hiz.zamana_cevir(snippet.get("publishedAt"))
        if yayin is not None:
            yaslar.append(max((an - yayin).days, 0))
        if kanal_id := snippet.get("channelId"):
            kanallar.append(kanal_id)

    olcum.medyan_izlenme = _medyan(izlenmeler)
    olcum.ust_izlenme = max(izlenmeler) if izlenmeler else None
    olcum.medyan_yas_gun = _medyan(yaslar)

    if kanallar:
        sayac.harca(KANAL, rezerve=rezerve)
        olcum.harcanan += kota.MALIYET[KANAL]
        aboneler = _aboneleri_getir(istemci, sorted(set(kanallar)))
        # Aynı kanal birden çok videoyla listede olabilir; her video için bir
        # kez sayılıyor, çünkü ölçtüğümüz şey "karşımdaki kanal ne büyüklükte",
        # "kaç ayrı kanal var" değil.
        gorulen = [aboneler[k] for k in kanallar if aboneler.get(k) is not None]
        olcum.medyan_abone = _medyan(gorulen)

    return olcum


def olcumu_yaz(yol: Path, olcum: ArzOlcumu) -> None:
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            """
            INSERT INTO arz (qid, dil, an, sorgu, donen, alakali, medyan_izlenme,
                             ust_izlenme, medyan_yas_gun, medyan_abone, harcanan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qid, dil, an) DO UPDATE SET
                donen          = excluded.donen,
                alakali        = excluded.alakali,
                medyan_izlenme = excluded.medyan_izlenme,
                ust_izlenme    = excluded.ust_izlenme,
                medyan_yas_gun = excluded.medyan_yas_gun,
                medyan_abone   = excluded.medyan_abone,
                harcanan       = excluded.harcanan
            """,
            (
                olcum.qid,
                olcum.dil,
                olcum.an,
                olcum.sorgu,
                olcum.donen,
                olcum.alakali,
                olcum.medyan_izlenme,
                olcum.ust_izlenme,
                olcum.medyan_yas_gun,
                olcum.medyan_abone,
                olcum.harcanan,
            ),
        )


# --- Aday seçimi ---------------------------------------------------------


def sondajlanmamis_adaylar(yol: Path, limit: int = 10) -> list[dict]:
    """Tarih/bilim sınıfında, henüz sondalanmamış, en çok okunan makaleler.

    `qid` şart: `arz` tablosu qid üzerinden anahtarlanıyor, çünkü aynı konu
    her dilde ayrı makale ama arz ölçümü konuya ait.

    Sondalanmış olanı tekrar sormamak huninin en önemli tasarrufu: her tekrar
    102 birim.
    """
    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute("SELECT MAX(gun) g FROM okunma").fetchone()
        gun = satir["g"] if satir else None
        if gun is None:
            return []
        return [
            dict(s)
            for s in baglanti.execute(
                """
                SELECT o.dil, o.baslik, o.okunma, m.qid, m.sinif
                FROM okunma o
                JOIN makale m ON m.dil = o.dil AND m.baslik = o.baslik
                WHERE o.gun = ?
                  AND m.sinif IN ('tarih', 'bilim')
                  AND m.qid IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM arz a WHERE a.qid = m.qid AND a.dil = o.dil)
                ORDER BY o.okunma DESC
                LIMIT ?
                """,
                (gun, limit),
            ).fetchall()
        ]
    finally:
        baglanti.close()


@dataclass
class ArastirmaSonucu:
    sondaj: int = 0
    harcanan: int = 0
    gecersiz: int = 0
    kota_bitti: bool = False
    hatalar: list[str] = field(default_factory=list)

    def ozet(self) -> str:
        satir = f"{self.sondaj} sondaj · {self.harcanan} birim"
        if self.gecersiz:
            satir += f" · {self.gecersiz} geçersiz"
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        if self.kota_bitti:
            satir += " · KOTA TAVANINDA DURDU"
        return satir


def arastir(
    istemci,
    sayac: kota.KaliciSayac,
    yol: Path,
    *,
    limit: int = 10,
    tavan: int = SONDAJ_KOTA_TAVANI,
    an: datetime | None = None,
) -> ArastirmaSonucu:
    """Sondajlanmamış adayları sırayla sondalar ve ölçümleri yazar.

    Bir adayın hatası araştırmayı bitirmez — DW-28'de aynı kararı bölgeler
    için vermiştik ve ilk canlı koşumda işe yaradı.
    """
    sonuc = ArastirmaSonucu()
    rezerve = kota.video_basina_maliyet()

    for aday in sondajlanmamis_adaylar(yol, limit):
        if sayac.surec_harcamasi + SONDAJ_MALIYETI > tavan:
            sonuc.kota_bitti = True
            break
        try:
            olcum = sondala(
                istemci,
                sayac,
                qid=aday["qid"],
                dil=aday["dil"],
                baslik=aday["baslik"],
                an=an,
                rezerve=rezerve,
            )
        except kota.KotaAsimi:
            sonuc.kota_bitti = True
            break
        except Exception as hata:  # noqa: BLE001 — tek aday araştırmayı bitirmemeli
            sonuc.hatalar.append(f"{aday['baslik']}: {hata}")
            continue

        sonuc.sondaj += 1
        sonuc.harcanan += olcum.harcanan
        if not olcum.gecerli:
            sonuc.gecersiz += 1
        olcumu_yaz(yol, olcum)

    return sonuc


# --- Rapor ---------------------------------------------------------------


@dataclass
class Bosluk:
    """Bir adayın skorlanmış hâli — depodaki ham ölçümden türetilir."""

    qid: str
    dil: str
    baslik: str
    sinif: str | None
    talep: int
    olcum: ArzOlcumu
    skor: float | None
    # Ham skorun kendi dilinin tabanına göre kaç MAD üstünde olduğu. Dilin
    # örneklemi yetmiyorsa `None` — "kötü" değil, **bilinmiyor**.
    kalibre: float | None = None

    def satir(self) -> str:
        baslik = self.baslik.replace("_", " ")
        skor = "—" if self.skor is None else f"{self.skor:+.2f}"
        kal = "—" if self.kalibre is None else f"{self.kalibre:+.2f}"
        etiket = f"[{self.sinif}] " if self.sinif else ""
        return (
            f"{kal:>6} MAD (ham {skor})  {etiket}{self.dil}: {baslik}\n"
            f"           talep {self.talep:,} okunma · arz: {self.olcum.ozet()}"
        )


def _dil_tabani(skorlar: list[float]) -> tuple[float, float] | None:
    """Bir dilin taban çizgisi: skorlarının medyanı ve medyan mutlak sapması.

    Medyan + MAD, ortalama + standart sapma değil — `nis._taban`'ın gerekçesi
    burada da geçerli: tek bir uç değer ortalamayı sürükler, aradığımız şey ise
    tam olarak "bu dilde olağandışı olan", yani taban olağanı temsil etmeli.

    MAD sıfırsa `None`: bütün skorlar aynı demek, bölme tanımsız ve o dilde
    "olağandışı" diye bir şey yok.
    """
    if len(skorlar) < ASGARI_TABAN_ORNEK:
        return None
    orta = median(skorlar)
    yayilim = median([abs(s - orta) for s in skorlar])
    return (orta, yayilim) if yayilim > 0 else None


def red_gerekcesi(kayit: Bosluk) -> str | None:
    """Adayın hangi kapıdan elendiği; `None` ise geçti.

    Sıra bilinçli: en temel eksiklik önce raporlanıyor, böylece "ölçümü bozuk"
    bir aday "talebi düşük" diye görünmüyor.
    """
    if kayit.skor is None:
        return RED_OLCUM
    if kayit.kalibre is None:
        return RED_TABAN
    if kayit.kalibre < ESIK_KALIBRE:
        return RED_KALIBRE
    if kayit.talep < ASGARI_TALEP:
        return RED_TALEP
    return None


def bosluklar(yol: Path, *, limit: int | None = None) -> list[Bosluk]:
    """Ölçülmüş adayları skora göre sıralar. Kota harcamaz.

    Her (qid, dil) için **en son** ölçüm kullanılıyor: arz zamanla değişiyor
    ve eski bir ölçümle karar vermek, ölçmemekten daha yanıltıcı olabilir.
    """
    baglanti = depo.baglan(yol)
    try:
        satirlar = baglanti.execute(
            """
            SELECT a.*, m.baslik, m.sinif,
                   (SELECT o.okunma FROM okunma o
                     WHERE o.dil = a.dil AND o.baslik = m.baslik
                     ORDER BY o.gun DESC LIMIT 1) AS talep
            FROM arz a
            JOIN makale m ON m.qid = a.qid AND m.dil = a.dil
            WHERE a.an = (SELECT MAX(b.an) FROM arz b WHERE b.qid = a.qid AND b.dil = a.dil)
            """
        ).fetchall()
    finally:
        baglanti.close()

    cikti: list[Bosluk] = []
    for s in satirlar:
        olcum = ArzOlcumu(
            qid=s["qid"],
            dil=s["dil"],
            sorgu=s["sorgu"],
            an=s["an"],
            donen=s["donen"],
            alakali=s["alakali"],
            medyan_izlenme=s["medyan_izlenme"],
            ust_izlenme=s["ust_izlenme"],
            medyan_yas_gun=s["medyan_yas_gun"],
            medyan_abone=s["medyan_abone"],
            harcanan=s["harcanan"],
        )
        talep = s["talep"] or 0
        cikti.append(
            Bosluk(
                qid=s["qid"],
                dil=s["dil"],
                baslik=s["baslik"],
                sinif=s["sinif"],
                talep=talep,
                olcum=olcum,
                skor=skorla(olcum, talep),
            )
        )

    # Kalibrasyon ikinci geçişte: taban, o dilin **bütün** ölçümlerinden
    # çıkıyor, yani tek bir adaya bakarak hesaplanamaz. `limit` bilerek en
    # sonda uygulanıyor — tabanı kırpılmış bir örneklemden kurmak, kırpmanın
    # kendisini sinyal sanmak olurdu.
    dile_gore: dict[str, list[float]] = {}
    for b in cikti:
        if b.skor is not None:
            dile_gore.setdefault(b.dil, []).append(b.skor)
    tabanlar = {dil: _dil_tabani(ss) for dil, ss in dile_gore.items()}

    for b in cikti:
        taban = tabanlar.get(b.dil)
        if b.skor is not None and taban is not None:
            orta, yayilim = taban
            b.kalibre = (b.skor - orta) / yayilim

    # Kalibresi olmayanlar (geçersiz ölçüm ya da güvenilmez taban) sona:
    # bilinmiyor, "kötü" değil. Ham skor ikincil anahtar olarak kalıyor ki
    # kalibre edilemeyenler de kendi aralarında anlamlı sırada dursun.
    cikti.sort(
        key=lambda b: (b.kalibre is not None, b.kalibre or 0.0, b.skor is not None, b.skor or 0.0),
        reverse=True,
    )
    return cikti[:limit] if limit else cikti
