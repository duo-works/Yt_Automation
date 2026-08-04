"""Sıçrama detektörü — patlayan konu gece hunisini beklemesin.

`okunma` tablosunda günlük seriler DW-34'ten beri birikiyordu ama gün-üstü-gün
kıyas hiç yapılmıyordu: huni "bugünün top-N'i"ne bakıyor, yani dünden beri
5 katına çıkmış bir konu ile aylardır aynı seviyede okunan bir konu aynı
görünüyordu. Bir konu patladıktan en geç ~30 saat sonra haberimiz oluyordu.

Bu modül o kıyası yapıyor: son günün okunması, önceki günlerin medyanına
bölünüyor. Sıçrayan konu sondaj kuyruğunun **başına** geçer ve DW-51
kapılarını geçerse Notion'a `🔥 Acil` durumuyla düşer.

Wikipedia verisi günlük yayımlanıyor — bu detektör "dün patlayanı bugün"
yakalar. Gün-içi tazelik ayrı kaynakların işi (DW-55 Google Trends); onların
bulduğu konular da aynı kuyruğa akar.

YouTube kotasına dokunmuyor: girdisi zaten toplanmış `okunma` satırları.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

from .. import depo
from . import bosluk

# Sıçrama tanımı. ⚠️ İki eşik de dağılımdan seçildi, yayın sonucundan değil
# (ADR-0009'daki gerekçenin aynısı) — ilk gerçek sıçramalar geldikçe revize
# edilmeli.
#
# Oran: son gün ≥ taban × 3. Günlük okunma serilerinde hafta içi/hafta sonu
# salınımı 2 katı bulabiliyor; 3 kat o gürültünün dışı.
SICRAMA_ORANI = 3.0

# Taban, önceki günlerin **medyanı**: `nis._taban` gerekçesi — dünkü tek bir
# anormal gün ortalamayı sürükler, medyan olağanı temsil eder.
TABAN_PENCERE_GUN = 7

# Tabanda en az bu kadar gün olmalı. İki günlük seriden "3 kat" çıkarmak
# sıçrama değil örneklem gürültüsü ölçmek olur.
ASGARI_TABAN_GUN = 3

# Mutlak taban: DW-51'in talep kapısıyla aynı sabit ve aynı gerekçe — günde
# 300 okunmadan 900'e çıkmak oransal olarak sıçramadır ama video yapılacak
# talep değildir. Düşük tabanlı gürültü acil kuyruğunu doldurmamalı.


@dataclass
class Sicrama:
    dil: str
    baslik: str
    qid: str | None
    sinif: str | None
    son_okunma: int
    taban: float
    oran: float

    def satir(self) -> str:
        baslik = self.baslik.replace("_", " ")
        etiket = f"[{self.sinif}] " if self.sinif else ""
        return (
            f"{self.oran:>5.1f}× {etiket}{self.dil}: {baslik} — "
            f"{self.son_okunma:,} okunma (taban {self.taban:,.0f})"
        )


def tespit_et(yol: Path, *, siniflar: tuple[str, ...] = ("tarih", "bilim")) -> list[Sicrama]:
    """Son günü tabanının ≥ SICRAMA_ORANI katı okunan konular, oran sırasıyla.

    Taban son günden **önceki** pencereden hesaplanıyor; son günün kendisi
    tabana girseydi her sıçrama kendi tabanını yükseltip kendini gizlerdi.

    Sınıf filtresi varsayılan açık: acil kuyruğu üretim kuyruğudur ve kanal
    tarih/bilim yayınlıyor. `diger` bir konu 50 kat da sıçrasa video olmaz.
    """
    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute("SELECT MAX(gun) g FROM okunma").fetchone()
        son_gun = satir["g"] if satir else None
        if son_gun is None:
            return []
        satirlar = baglanti.execute(
            f"""
            SELECT o.dil, o.baslik, o.okunma, m.qid, m.sinif
            FROM okunma o
            JOIN makale m ON m.dil = o.dil AND m.baslik = o.baslik
            WHERE o.gun = ?
              AND m.sinif IN ({",".join("?" * len(siniflar))})
              AND o.okunma >= ?
            """,
            (son_gun, *siniflar, bosluk.ASGARI_TALEP),
        ).fetchall()

        cikti: list[Sicrama] = []
        for s in satirlar:
            gecmis = [
                g["okunma"]
                for g in baglanti.execute(
                    """
                    SELECT okunma FROM okunma
                    WHERE dil = ? AND baslik = ? AND gun < ?
                    ORDER BY gun DESC LIMIT ?
                    """,
                    (s["dil"], s["baslik"], son_gun, TABAN_PENCERE_GUN),
                ).fetchall()
            ]
            if len(gecmis) < ASGARI_TABAN_GUN:
                # Yeni görülen konu: taban yok, sıçrama da yok. Top listesine
                # ilk kez girmek zaten hunide "en çok okunan" olarak yarışıyor;
                # burada ölçülen şey **değişim**, popülerlik değil.
                continue
            taban = median(gecmis)
            if taban <= 0:
                continue
            oran = s["okunma"] / taban
            if oran >= SICRAMA_ORANI:
                cikti.append(
                    Sicrama(
                        dil=s["dil"],
                        baslik=s["baslik"],
                        qid=s["qid"],
                        sinif=s["sinif"],
                        son_okunma=s["okunma"],
                        taban=taban,
                        oran=oran,
                    )
                )
        cikti.sort(key=lambda x: -x.oran)
        return cikti
    finally:
        baglanti.close()


def sicrayan_qidler(yol: Path) -> set[str]:
    """Sıçrayan konuların QID kümesi — kuyruk önceliği ve Acil işareti için."""
    return {s.qid for s in tespit_et(yol) if s.qid}
