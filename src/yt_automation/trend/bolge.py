"""Bölge ve liste kataloğu — taramaya özel ne varsa burada.

`kanal.py` ile aynı desen: soyutlama katmanı değil, **tek bir yer**. Hangi
listelerin çekileceği, derin taramanın kaç bölge kapsayacağı, kotanın trend
tarafına ayrılan payı — hepsi bu dosyada.
"""

from __future__ import annotations

import sqlite3
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


def derin_bolgeler(yol: Path, adet: int = DERIN_BOLGE_SAYISI) -> list[str]:
    """Derin taramanın kapsayacağı bölgeler — **ölçülerek**, varsayılmadan.

    Sıralama, son geniş taramada eğitim/bilim kategorisindeki videoların
    yoğunluğuna göre yapılır. Sabit bir "en büyük 20 pazar" listesi yazmak,
    *"hangi ülkede"* sorusunu ilk günden varsaymak olurdu — oysa izlenme
    hacmi ile tarih/bilim yoğunluğu aynı sırayı vermek zorunda değil.
    """
    baglanti = depo.baglan(yol)
    try:
        an = son_genis_kosu(baglanti)
        if an is None:
            raise BolgeHatasi(
                "derin tarama için önce en az bir geniş tarama gerekiyor — "
                "`ytoto trend topla --genis` çalıştırın"
            )
        satirlar = baglanti.execute(
            f"""
            SELECT o.bolge AS bolge, COUNT(*) AS adet
            FROM olcum o
            JOIN video v ON v.video_id = o.video_id
            WHERE o.an = ?
              AND v.kategori_id IN ({",".join("?" * len(ILGILI_KATEGORILER))})
            GROUP BY o.bolge
            ORDER BY adet DESC, o.bolge ASC
            LIMIT ?
            """,
            (an, *ILGILI_KATEGORILER, adet),
        ).fetchall()
    finally:
        baglanti.close()

    if not satirlar:
        raise BolgeHatasi(
            f"son geniş taramada ({an}) hiç eğitim/bilim videosu bulunamadı — "
            "taramanın gerçekten veri getirdiğini doğrulayın"
        )
    return [s["bolge"] for s in satirlar]
