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
# ⚠️ YouTube'da **Tarih diye bir kategori yok.** Tarih içeriği Eğitim (27)
# altında yaşıyor, taşanı People & Blogs (22), Entertainment (24) ve News (25)
# içinde. O üçünü ayrı ayrı çekmek bölge başına 150 satır getirir ve neredeyse
# tamamı alakasız olur.
#
# Bunun yerine kısıtsız liste (0) çekiliyor: taşan tarih/bilim içeriğini
# *zaten genel trend olduğu için* yakalar, çöp getirmeden. Kategoriye göre
# ayıklama DW-30'un işi.
LISTELER: tuple[int, ...] = (
    27,  # Education
    28,  # Science & Technology
    0,  # kısıtsız — kategorisi ne olursa olsun o bölgede trend olanlar
)

# Sınıflandırıcı (DW-30) gelene kadar "ilgili" saydığımız kategoriler.
# Derin tarama bölgelerini sıralamak için yeterli: kategori bedava, LLM değil.
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
