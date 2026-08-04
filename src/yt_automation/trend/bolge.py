"""Bölge ve liste kataloğu — taramaya özel ne varsa burada.

`kanal.py` ile aynı desen: soyutlama katmanı değil, **tek bir yer**. Hangi
listelerin çekileceği, derin taramanın kaç bölge kapsayacağı, kotanın trend
tarafına ayrılan payı — hepsi bu dosyada.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .. import depo

# Çekilecek listeler. Her biri bölge başına bir `videos.list` çağrısı = 1 birim.
#
# ⚠️ **Eğitim (27) burada yok ve bu bir eksiklik değil, ölçülmüş bir gerçek.**
# `chart=mostPopular` her kategori için mevcut değil; 27 istendiğinde API
# HTTP 404 "Requested entity was not found" döndürüyor. İlk canlı taramada
# 111 bölgenin 111'inde de aynı hata çıktı. 2026-07-29'da tek tek denendi:
# 0, 22, 24, 25, 26, 28 çalışıyor — **yalnızca 27 çalışmıyor.**
#
# ⚠️ Ayrıca YouTube'da **Tarih diye bir kategori hiç yok.** Tarih içeriği
# normalde Eğitim altında yaşar; o çart da olmadığına göre tarihi kategoriyle
# bulmanın yolu kalmıyor.
#
# 22/24/25 eklemek çözmüyor: kategoriye göre filtrelenmiş bir çart yalnızca o
# kategorideki videoları döndürür, yani içlerinden tarihi *kategoriyle* ayıklamak
# mümkün değil. Sınıflandırıcı (DW-30) gelmeden oraya girmek, bölge başına 150
# satır çöp depolamak olur. O yüzden liste seti DW-30'da yeniden değerlendirilecek.
LISTELER: tuple[int, ...] = (
    28,  # Science & Technology — çartı var, doğrudan ilgili
    0,  # kısıtsız — kategorisi ne olursa olsun o bölgede trend olanlar
)

# Sınıflandırıcı (DW-30) gelene kadar "ilgili" saydığımız kategoriler.
# Derin tarama bölgelerini sıralamak için yeterli: kategori bedava, LLM değil.
#
# 27 burada var ama `LISTELER`'de yok — çelişki değil: bu küme videonun
# **kendi** kategorisine bakıyor, hangi çarttan geldiğine değil. Eğitim
# videoları kısıtsız listeden geliyor (ilk taramada 46 tane) ve bir bölgenin
# eğitim yoğunluğunu ölçerken onları saymamak yanlış olurdu.
ILGILI_KATEGORILER: tuple[int, ...] = (27, 28)

DERIN_BOLGE_SAYISI = 20

# Bölge sıralamasının bakacağı geçmiş penceresi (gün).
#
# Tek bir geniş taramaya bakmak kırılgan: o koşumda bir bölge hata verdiyse
# (ilk canlı taramada 111 bölgenin hepsi 404 aldı) sıralamadan tamamen düşer.
# Bir hafta, haftalık yeniden seçim ritmine denk geliyor ve tek koşumun
# gürültüsünü yumuşatıyor.
SECIM_PENCERESI_GUN = 7

# İki bölgenin "aynı çartı döndürüyor" sayılması için örtüşme oranı.
#
# ⚠️ Bu eşik ölçülerek konuldu. 2026-07-30 geniş taramasında:
#
#     LI ∩ CH   %100   ← Liechtenstein, İsviçre çartının birebir kopyası
#     US ∩ GB    %62
#     AT ∩ DE    %48
#     CH ∩ AT    %42
#     SG ∩ MY    %28
#     TR ∩ DE     %7
#
# Liechtenstein 40 bin nüfuslu ve YouTube ona ayrı bir çart üretmiyor. Onu
# ayrı bölge saymak derin taramanın 20 yuvasından birini hiç yeni veri
# getirmeyen bir çağrıya harcamak olur.
#
# %90: yalnızca fiilen aynı olanı eliyor. %62'de duran US/GB gerçekten farklı
# — ortak dil örtüşme üretiyor ama %38'i ayrı ve o kısım bilgi taşıyor.
ORTUSME_ESIGI = 0.90

# Yalnızca `--kuru` maliyet tahmini için. Gerçek sayı her koşuda
# `i18nRegions.list`'ten geliyor; burası bir çağrı yapmadan büyüklük sırası
# verebilmek için duruyor. Google bölge eklerse tahmin biraz şaşar, koşu şaşmaz.
TAHMINI_BOLGE_SAYISI = 100

# Trend tarafının günlük kota payı. Toplam bütçe 10.000 ve yükleme hattı
# günde ~1.651–3.302 birim yiyor; geriye rahat sığıyor. Tavanın kendisi
# `TREND_KOTA_TAVANI` ile sınırlanıyor ki bir hata döngüsü bütçeyi süpürmesin.
TREND_KOTA_TAVANI = 2_500


class BolgeHatasi(RuntimeError):
    """Bölge listesi belirlenemedi."""


def bolgeleri_getir(istemci) -> list[str]:
    """`i18nRegions.list` ile desteklenen tüm bölge kodları (1 birim).

    Sabit liste tutulmuyor: Google zaman zaman bölge ekliyor ve eskimiş bir
    liste sessizce eksik tarama yapar.
    """
    yanit = istemci.i18nRegions().list(part="snippet").execute()
    return sorted(oge["snippet"]["gl"] for oge in yanit.get("items", []))


def son_genis_kosu(baglanti: sqlite3.Connection) -> str | None:
    satir = baglanti.execute(
        "SELECT an FROM kosu WHERE tur = 'genis' ORDER BY an DESC LIMIT 1"
    ).fetchone()
    return satir["an"] if satir else None


def _ilgi_siralamasi(baglanti: sqlite3.Connection, sinir: str) -> list[tuple[str, int]]:
    """Bölgeleri ilgili içerik yoğunluğuna göre sıralar.

    Ölçüt **kategori**, sınıf değil ve bu ölçülmüş bir seçim. DW-31'de
    `video.sinif` doldurulduktan sonra ikisini karşılaştırdım:

        sinif IN ('tarih','bilim')  →  en yüksek bölge  6 video
        kategori_id IN (27, 28)     →  en yüksek bölge 93 video

    Sınıf sinyali 20 bölgeyi sıralamak için fazla seyrek: altıncı bölgeden
    sonra hepsi 3'e düşüyor ve sıralama alfabetik kura dönüyor. Kategori zayıf
    ama **yoğun** bir sinyal ve burada aranan şey mutlak doğruluk değil, hangi
    ülkeye ikinci bir çağrı yapmaya değer olduğu.
    """
    yer = ",".join("?" * len(ILGILI_KATEGORILER))
    return [
        (s["bolge"], s["adet"])
        for s in baglanti.execute(
            f"""
            SELECT o.bolge AS bolge, COUNT(DISTINCT o.video_id) AS adet
            FROM olcum o
            JOIN video v ON v.video_id = o.video_id
            JOIN kosu k ON k.an = o.an AND k.tur = 'genis'
            WHERE o.an >= ?
              AND v.kategori_id IN ({yer})
            GROUP BY o.bolge
            ORDER BY adet DESC, o.bolge ASC
            """,
            (sinir, *ILGILI_KATEGORILER),
        ).fetchall()
    ]


def _ortusme_haritasi(baglanti: sqlite3.Connection, an: str) -> dict[str, frozenset[str]]:
    """Bir koşudaki her bölgenin video kümesi."""
    kumeler: dict[str, set[str]] = {}
    for s in baglanti.execute("SELECT bolge, video_id FROM olcum WHERE an = ?", (an,)).fetchall():
        kumeler.setdefault(s["bolge"], set()).add(s["video_id"])
    return {b: frozenset(v) for b, v in kumeler.items()}


def kopya_bolgeler(
    kumeler: dict[str, frozenset[str]], sirali: list[str], esik: float = ORTUSME_ESIGI
) -> dict[str, str]:
    """`kopya → temsilci` eşlemesi.

    Sıralamada **önde** olan bölge temsilci olur; arkadakiler onun kopyası
    sayılır. Böylece LI/CH çiftinde hangisinin kaldığı sıralamaya göre
    belirlenir, alfabeye göre değil.
    """
    kopyalar: dict[str, str] = {}
    temsilciler: list[str] = []
    for bolge in sirali:
        kume = kumeler.get(bolge)
        if not kume:
            continue
        for temsilci in temsilciler:
            digeri = kumeler[temsilci]
            ortak = len(kume & digeri)
            if ortak / min(len(kume), len(digeri)) >= esik:
                kopyalar[bolge] = temsilci
                break
        else:
            temsilciler.append(bolge)
    return kopyalar


def derin_bolgeler(
    yol: Path, adet: int = DERIN_BOLGE_SAYISI, *, pencere_gun: int = SECIM_PENCERESI_GUN
) -> list[str]:
    """Derin taramanın kapsayacağı bölgeler — **ölçülerek**, varsayılmadan.

    Sabit bir "en büyük 20 pazar" listesi yazmak, *"hangi ülkede"* sorusunu
    ilk günden varsaymak olurdu — oysa izlenme hacmi ile tarih/bilim yoğunluğu
    aynı sırayı vermek zorunda değil.

    İki iyileştirme DW-32'de geldi:

    1. **Pencere.** Tek bir koşuya değil son `pencere_gun` gündeki geniş
       taramalara bakılıyor. Tek koşuma bakmak kırılgan: o koşumda hata almış
       bir bölge sıralamadan tamamen düşerdi.
    2. **Kopya eleme.** Aynı çartı döndüren bölgeler tek bir yuva harcıyor;
       gerekçe `ORTUSME_ESIGI`'nde ölçümle birlikte duruyor.
    """
    sinir = (datetime.now(UTC) - timedelta(days=pencere_gun)).isoformat()
    baglanti = depo.baglan(yol)
    try:
        an = son_genis_kosu(baglanti)
        if an is None:
            raise BolgeHatasi(
                "derin tarama için önce en az bir geniş tarama gerekiyor — "
                "`ytoto trend topla --genis` çalıştırın"
            )
        sirali = _ilgi_siralamasi(baglanti, sinir)
        if not sirali:
            raise BolgeHatasi(
                f"son {pencere_gun} günde hiç eğitim/bilim videosu bulunamadı "
                f"(en son geniş tarama: {an}) — taramanın veri getirdiğini doğrulayın"
            )
        kumeler = _ortusme_haritasi(baglanti, an)
    finally:
        baglanti.close()

    adlar = [b for b, _ in sirali]
    kopyalar = kopya_bolgeler(kumeler, adlar)
    return [b for b in adlar if b not in kopyalar][:adet]


def secim_raporu(
    yol: Path, adet: int = DERIN_BOLGE_SAYISI, *, pencere_gun: int = SECIM_PENCERESI_GUN
) -> list[dict]:
    """Sıralamanın **neden** böyle olduğunu gösteren teşhis çıktısı.

    Bölge seçimi otomatik ama denetlenebilir olmalı: "neden TR listede yok"
    sorusunun cevabı koda bakmadan görülebilmeli.
    """
    sinir = (datetime.now(UTC) - timedelta(days=pencere_gun)).isoformat()
    baglanti = depo.baglan(yol)
    try:
        an = son_genis_kosu(baglanti)
        sirali = _ilgi_siralamasi(baglanti, sinir)
        kumeler = _ortusme_haritasi(baglanti, an) if an else {}
    finally:
        baglanti.close()

    kopyalar = kopya_bolgeler(kumeler, [b for b, _ in sirali])
    rapor: list[dict] = []
    secilen = 0
    for bolge, sayi in sirali:
        kopya = kopyalar.get(bolge)
        if kopya is None and secilen < adet:
            secilen += 1
            durum = "seçildi"
        elif kopya is not None:
            durum = f"kopya → {kopya}"
        else:
            durum = "sıra dışı"
        rapor.append({"bolge": bolge, "adet": sayi, "durum": durum})
    return rapor
