"""Wikipedia aday üretimi — okunma listelerini çeker, sınıflandırır, depolar.

Huninin ilk katmanı. Tamamen ücretsiz: ne YouTube kotası harcıyor ne API
anahtarı istiyor. Pahalı doğrulama (`search.list`, 100 birim) DW-35'te ve
yalnızca bu katmanın süzdüğü adaylara uygulanacak.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from .. import depo
from . import konu, wikipedia


@dataclass
class ToplamaSonucu:
    gun: str
    diller: list[str] = field(default_factory=list)
    aday: int = 0
    siniflar: dict[str, int] = field(default_factory=dict)
    hatalar: list[str] = field(default_factory=list)

    def ozet(self) -> str:
        dagilim = " · ".join(f"{k}:{v}" for k, v in sorted(self.siniflar.items()))
        satir = f"{self.gun} · {len(self.diller)} dil · {self.aday} makale · {dagilim}"
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        return satir


def _sinifi_yaz(baglanti, dil: str, baslik: str, qid, tipler, sinif: str, simdi: str) -> None:
    baglanti.execute(
        """
        INSERT INTO makale (dil, baslik, qid, turler, sinif, sinif_kaynagi, ilk_gorulme)
        VALUES (?, ?, ?, ?, ?, 'wikidata', ?)
        ON CONFLICT(dil, baslik) DO UPDATE SET
            qid    = COALESCE(excluded.qid, makale.qid),
            turler = COALESCE(excluded.turler, makale.turler),
            -- LLM bir kez karar verdiyse (DW-30) Wikidata onu ezmemeli:
            -- LLM daha fazla bilgiyle bakıyor, bu katman yalnızca ön eleme.
            sinif  = CASE WHEN makale.sinif_kaynagi = 'llm'
                          THEN makale.sinif ELSE excluded.sinif END
        """,
        (dil, baslik, qid, json.dumps(tipler) if tipler else None, sinif, simdi),
    )


def topla(
    yol: Path,
    *,
    diller: tuple[str, ...] = wikipedia.VARSAYILAN_DILLER,
    gun: date | None = None,
    adet: int = 200,
) -> ToplamaSonucu:
    """Verilen diller için bir günün en çok okunan makalelerini toplar.

    Bir dilin hatası diğerlerini düşürmez — DW-28'de aynı kararı bölgeler için
    vermiştik ve ilk canlı koşumda 111 bölgenin hatası sayesinde kalan verinin
    korunması işe yaradı.
    """
    gun = gun or wikipedia.son_yayimlanan_gun()
    simdi = datetime.now(UTC).isoformat()
    sonuc = ToplamaSonucu(gun=gun.isoformat())

    for dil in diller:
        try:
            okunmalar = wikipedia.gunluk_liste(dil, gun, adet=adet)
        except wikipedia.WikipediaHatasi as hata:
            sonuc.hatalar.append(f"{dil}: {hata}")
            continue
        if not okunmalar:
            continue
        sonuc.diller.append(dil)

        basliklar = [o.baslik for o in okunmalar]
        try:
            kimlikler = konu.kimlikleri_getir(dil, basliklar)
            varliklar = konu.varliklari_getir(sorted(set(kimlikler.values())))
        except konu.WikidataHatasi as hata:
            sonuc.hatalar.append(f"{dil}/wikidata: {hata}")
            kimlikler, varliklar = {}, {}

        with depo.yazma_islemi(yol) as baglanti:
            for o in okunmalar:
                qid = kimlikler.get(o.baslik)
                varlik = varliklar.get(qid) if qid else None
                tipler = varlik["tipler"] if varlik else []
                # Kimlik yoksa sınıflandıramayız; "diger" demek yanlış olur —
                # bilinmiyor demek doğru. `belirsiz` LLM kuyruğuna gider.
                sinif = konu.siniflandir(tipler, varlik) if qid else "belirsiz"
                _sinifi_yaz(baglanti, dil, o.baslik, qid, tipler, sinif, simdi)
                baglanti.execute(
                    """
                    INSERT INTO okunma (dil, baslik, gun, okunma, sira)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(dil, baslik, gun) DO UPDATE SET
                        okunma = excluded.okunma,
                        sira   = COALESCE(excluded.sira, okunma.sira)
                    """,
                    (o.dil, o.baslik, o.gun, o.okunma, o.sira),
                )
                sonuc.aday += 1
                sonuc.siniflar[sinif] = sonuc.siniflar.get(sinif, 0) + 1

    return sonuc


ADAY_PENCERESI_GUN = 7
"""Aday listesi kaç günlük pencereye bakar.

⚠️ Tek güne bakmak huniyi kurutuyordu. Ölçüldü (2026-08-06, DW-92): Google
Trends keşfi saat başı koşuyor ve eşleştirdiği birkaç makaleyi **bugünün**
tarihiyle yazıyor. O gün `MAX(gun)` oluyor ve tek-gün sorgusu yalnızca oraya
bakıyor:

    2026-08-05:     9 satır  ←  gtrends keşfi, 1 tarih/bilim makalesi
    2026-08-04: 3.021 satır  ←  asıl günlük toplama, 247 tarih/bilim

Yani 247 aday, 9 satırlık bir günün gölgesinde görünmez kaldı. Sondaj
kapasitesinin %97'si boşta dururken kuyrukta tek aday vardı ve kimse sebebini
göremiyordu — huni "kurumuş" görünüyordu, oysa doluydu.

Pencere ölçülerek seçildi (sondajlanmamış aday): 1 gün → 1, 2 gün → 183,
7 gün → 208, 14 gün → 226. Marjinal kazanç 7'den sonra düşüyor; buna karşılık
eskiyen konu riski artıyor. 7 gün ayrıca birkaç günlük veri kaybına (dizüstü
kapalı) dayanıklı.
"""


def adaylar(yol: Path, *, gun: str | None = None, limit: int = 40) -> list[dict]:
    """İlgili sınıftaki makaleleri okunmaya göre sıralar.

    Varsayılan olarak son `ADAY_PENCERESI_GUN` günlük pencereye bakar; `gun`
    verilirse yalnızca o gün. Aynı makale birden çok gün listeye girmişse **en
    yüksek** okunmasıyla bir kez görünür.

    Hız/ivme burada **yok** — o DW-29'un işi ve seri matematiği kaynaktan
    bağımsız olduğu için aynı modül buraya da uygulanacak.
    """
    baglanti = depo.baglan(yol)
    try:
        if gun is not None:
            # Açıkça bir gün istendi — pencere uygulanmaz.
            return [
                dict(s)
                for s in baglanti.execute(
                    """
                    SELECT o.dil, o.baslik, o.okunma, m.sinif, m.qid
                    FROM okunma o JOIN makale m ON m.dil = o.dil AND m.baslik = o.baslik
                    WHERE o.gun = ? AND m.sinif IN ('tarih', 'bilim')
                    ORDER BY o.okunma DESC LIMIT ?
                    """,
                    (gun, limit),
                ).fetchall()
            ]
        return [
            dict(s)
            for s in baglanti.execute(
                """
                SELECT o.dil, o.baslik, MAX(o.okunma) AS okunma, m.sinif, m.qid
                FROM okunma o JOIN makale m ON m.dil = o.dil AND m.baslik = o.baslik
                WHERE m.sinif IN ('tarih', 'bilim')
                  AND o.gun >= date((SELECT MAX(gun) FROM okunma), ?)
                GROUP BY o.dil, o.baslik
                ORDER BY okunma DESC LIMIT ?
                """,
                (f"-{ADAY_PENCERESI_GUN - 1} day", limit),
            ).fetchall()
        ]
    finally:
        baglanti.close()
