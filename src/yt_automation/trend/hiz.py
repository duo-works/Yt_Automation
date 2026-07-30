"""Hız, ivme ve yaşa göre normalize sinyaller — düzensiz örneklemeye dayanıklı.

`chart=mostPopular` **zaten popüler olanı** verir; aradığımız yükselen. Bu
modül o farkı hesaplar ve hiç kota harcamaz: girdisi `olcum` tablosundaki
zaman serisi, çıktısı türetilmiş sayılar.

## Neden hiçbir şey diske yazılmıyor

Hız ve ivme türetilmiş değerler. Saklansalardı yeni bir ölçüm geldiğinde
bayatlarlardı ve "hangisi güncel" sorusu doğardı. Okuma anında hesaplanıyor,
şema değişmiyor. Aynı gerekçe Notion panosunda türetilmiş gerçek tutmama
kuralıyla aynı.

## İzlenme küresel, sıra bölgesel

`viewCount` bir bölge sayısı değil, dünya toplamı: aynı koşuda TR ve DE için
dönen izlenme aynıdır. Bu yüzden hız **video başına** hesaplanıyor, (video,
bölge) başına değil — yoksa tek bir sayı bölge sayısı kadar tekrarlanır ve
sıralama, çok bölgede görünen videoları yapay olarak öne çıkarırdı.

Bölgesel olan iki şey var: `sira` ve videonun **kaç bölgede** göründüğü.
İkincisinin artması ("yayılım") kendi başına sinyal.

## Düzensiz örnekleme

v1 elle çalışıyor (PRD); zamanlanmış koşum DW-32'ye bağlı. Laptop kapalıyken
boşluk oluşacak. Bu yüzden hiçbir yerde "saatte bir çalışıyor" varsayılmıyor:
her aralık **iki ölçümün gerçek zaman damgası** farkından hesaplanır.

İvme için de aynısı geçerli ve orada bir incelik var: eşit aralıklı olmayan
örneklerde iki hızı çıkarıp sabit bir sayıya bölmek yanlış sonuç verir. Her
hız, ait olduğu aralığın **orta noktasına** yerleştirilip ivme o iki orta
nokta arasındaki süreye bölünüyor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import depo

# İki ölçüm bundan yakınsa aralık kullanılmaz, daha geriye bakılır.
#
# Neden: izlenme sayacı kabaca güncelleniyor ve gerçek zamanlı değil. 3 dakika
# arayla iki koşum yapılırsa Δizlenme çoğu videoda 0, bazılarında bir sıçrama
# olur; 0.05 saate bölünce ikisi de saçmalar. 15 dakika, sayacın oturması için
# gözlenen en kısa makul süre.
ASGARI_ARALIK_SAAT = 0.25

# Yaşa göre normalizede bölenin tabanı.
#
# 6 dakikalık bir video 100 izlenmeyle 1.000 izlenme/saat gösterir ve listenin
# tepesine oturur — sinyal değil, küçük bölen. Taban, çok yeni videoların
# matematiği ele geçirmesini engelliyor.
ASGARI_YAS_SAAT = 1.0

SIRALAMA_ALANLARI = ("ivme", "hiz", "yas", "izlenme")


def _zamana_cevir(metin: str | None) -> datetime | None:
    """ISO 8601 metnini UTC'ye demirlenmiş `datetime`a çevirir.

    İki farklı kaynak var ve biçimleri farklı: `olcum.an` bizim yazdığımız
    `datetime.isoformat()` (`+00:00`), `video.yayin_zamani` YouTube'un
    döndürdüğü `Z` sonlu biçim. Naive gelen bir değer UTC sayılır — depoya
    yazan tek yol `datetime.now(UTC)` olduğu için bu varsayım güvenli.
    """
    if not metin:
        return None
    try:
        an = datetime.fromisoformat(metin)
    except ValueError:
        return None
    return an if an.tzinfo else an.replace(tzinfo=UTC)


def _saat_farki(sonra: datetime, once: datetime) -> float:
    return (sonra - once).total_seconds() / 3600


@dataclass(frozen=True)
class Nokta:
    """Bir videonun tek bir koşudaki durumu — bölgeler birleştirilmiş."""

    an: datetime
    izlenme: int
    en_iyi_sira: int | None
    bolge_sayisi: int


@dataclass
class Sinyal:
    """Bir video için türetilmiş bütün sinyaller.

    `None` alanlar "hesaplanamadı" demek, "sıfır" demek değil: tek ölçümü olan
    bir videonun hızı bilinmiyor, sıfır değil. Ayrım korunuyor çünkü sıralama
    ikisini farklı yerlere koymalı.
    """

    video_id: str
    baslik: str
    kanal_adi: str | None
    sinif: str | None
    kategori_id: int | None

    olcum_sayisi: int
    izlenme: int
    son_an: datetime

    hiz: float | None = None  # izlenme/saat, en son geçerli aralık
    onceki_hiz: float | None = None
    ivme: float | None = None  # izlenme/saat², hızın kendi değişimi
    yas_saat: float | None = None
    yasa_gore: float | None = None  # toplam izlenme / yaş

    en_iyi_sira: int | None = None
    sira_degisimi: int | None = None  # + = yukarı çıktı
    bolge_sayisi: int = 0
    bolge_yayilimi: int | None = None  # + = daha çok ülkede göründü
    yeni_giren: bool = False

    def sirala_anahtari(self, alan: str) -> tuple[int, float]:
        """`None` değerleri sona atan sıralama anahtarı.

        `float("-inf")` yeterli değil: hesaplanamayan ivme ile gerçekten
        negatif ivme aynı kovaya düşerdi. İlk eleman "hesaplandı mı"yı taşıyor.
        """
        deger = {
            "ivme": self.ivme,
            "hiz": self.hiz,
            "yas": self.yasa_gore,
            "izlenme": float(self.izlenme),
        }[alan]
        if deger is None or math.isnan(deger):
            return (0, 0.0)
        return (1, deger)

    def satir(self) -> str:
        def sayi(deger: float | None, birim: str) -> str:
            return "—" if deger is None else f"{deger:+,.0f} {birim}"

        parcalar = [
            f"{self.izlenme:>12,} izlenme",
            f"hız {sayi(self.hiz, '/sa')}",
            f"ivme {sayi(self.ivme, '/sa²')}",
        ]
        if self.yasa_gore is not None:
            parcalar.append(f"yaş {self.yasa_gore:,.0f}/sa ({self.yas_saat:,.0f} sa)")
        if self.en_iyi_sira is not None:
            sira = f"#{self.en_iyi_sira}"
            if self.sira_degisimi:
                sira += f" ({self.sira_degisimi:+d})"
            parcalar.append(sira)
        parcalar.append(f"{self.bolge_sayisi} bölge")
        if self.yeni_giren:
            parcalar.append("🆕 listeye YENİ girdi")
        etiket = f"[{self.sinif}] " if self.sinif else ""
        return f"{' · '.join(parcalar)}\n      {etiket}{self.baslik}"


def _geriye_bak(seri: list[Nokta], i: int, asgari: float) -> int | None:
    """`i`'den geriye, en az `asgari` saat uzakta **en yakın** noktayı bulur.

    En yakını seçmek bilinçli: hız son durumu yansıtmalı. Üç gün önceki bir
    ölçüme demirlenmiş "hız", aradaki sıçramayı ortalayıp yok eder.
    """
    for j in range(i - 1, -1, -1):
        if _saat_farki(seri[i].an, seri[j].an) >= asgari:
            return j
    return None


def _aralik_hizi(seri: list[Nokta], sonra: int, once: int) -> tuple[float, datetime]:
    """Bir aralığın hızı ve o hızın ait olduğu **orta nokta**.

    Orta nokta ivme için gerekli: hız bir aralığa aittir, tek bir ana değil.
    """
    fark_saat = _saat_farki(seri[sonra].an, seri[once].an)
    hiz = (seri[sonra].izlenme - seri[once].izlenme) / fark_saat
    orta = seri[once].an + (seri[sonra].an - seri[once].an) / 2
    return hiz, orta


def turet(
    seri: list[Nokta],
    *,
    yayin_zamani: datetime | None = None,
    ilk_gorulme: datetime | None = None,
    sinyal: Sinyal,
) -> Sinyal:
    """Bir videonun serisinden hız, ivme ve normalize değerleri doldurur.

    Seri `an`'a göre artan sırada olmalı. İzlenmesi `NULL` gelen ölçümler
    (gizli istatistik) çağıran tarafından ayıklanmış varsayılıyor.
    """
    son = seri[-1]
    sinyal.olcum_sayisi = len(seri)
    sinyal.izlenme = son.izlenme
    sinyal.son_an = son.an
    sinyal.en_iyi_sira = son.en_iyi_sira
    sinyal.bolge_sayisi = son.bolge_sayisi

    # --- Hız: en son geçerli aralık ---------------------------------------
    j = _geriye_bak(seri, len(seri) - 1, ASGARI_ARALIK_SAAT)
    if j is not None:
        sinyal.hiz, son_orta = _aralik_hizi(seri, len(seri) - 1, j)

        if seri[j].en_iyi_sira is not None and son.en_iyi_sira is not None:
            # Sıra küçükse iyi; işareti çeviriyoruz ki "+" yukarı çıkmak olsun.
            sinyal.sira_degisimi = seri[j].en_iyi_sira - son.en_iyi_sira
        sinyal.bolge_yayilimi = son.bolge_sayisi - seri[j].bolge_sayisi

        # --- İvme: bir önceki aralığın hızıyla karşılaştır -----------------
        k = _geriye_bak(seri, j, ASGARI_ARALIK_SAAT)
        if k is not None:
            sinyal.onceki_hiz, onceki_orta = _aralik_hizi(seri, j, k)
            orta_fark = _saat_farki(son_orta, onceki_orta)
            if orta_fark > 0:
                sinyal.ivme = (sinyal.hiz - sinyal.onceki_hiz) / orta_fark

    # --- Yaşa göre normalize ----------------------------------------------
    if yayin_zamani is not None:
        yas = _saat_farki(son.an, yayin_zamani)
        if yas > 0:
            sinyal.yas_saat = yas
            sinyal.yasa_gore = son.izlenme / max(yas, ASGARI_YAS_SAAT)

    # --- Listeye giriş ----------------------------------------------------
    # Videonun ilk görüldüğü koşu, son koşuysa: bu tarama onu ilk kez gördü.
    # Tek başına güçlü sinyal — çarta yeni düşmek, çartta durmaktan farklı.
    if ilk_gorulme is not None:
        sinyal.yeni_giren = ilk_gorulme == son.an

    return sinyal


def _serileri_oku(baglanti, bolge_kodu: str | None) -> dict[str, list[Nokta]]:
    """Video başına, `an`'a göre sıralı nokta serisi.

    `MAX(izlenme)`: aynı koşuda aynı video birden çok bölgede görünüyor ve
    izlenme küresel olduğu için hepsinde aynı. `MAX` ayrıca `NULL` gelen
    bölgeleri sessizce atlıyor.
    """
    kosul = "WHERE bolge = ?" if bolge_kodu else ""
    parametreler = (bolge_kodu,) if bolge_kodu else ()
    satirlar = baglanti.execute(
        f"""
        SELECT video_id,
               an,
               MAX(izlenme)           AS izlenme,
               MIN(sira)              AS en_iyi_sira,
               COUNT(DISTINCT bolge)  AS bolge_sayisi
        FROM olcum
        {kosul}
        GROUP BY video_id, an
        ORDER BY video_id, an
        """,
        parametreler,
    ).fetchall()

    seriler: dict[str, list[Nokta]] = {}
    for satir in satirlar:
        an = _zamana_cevir(satir["an"])
        if an is None or satir["izlenme"] is None:
            # İzlenmesi gizli bir ölçüm hız hesabına giremez. Atlamak, sıfır
            # varsaymaktan iyi: sıfır varsaymak sahte bir çöküş üretirdi.
            continue
        seriler.setdefault(satir["video_id"], []).append(
            Nokta(
                an=an,
                izlenme=satir["izlenme"],
                en_iyi_sira=satir["en_iyi_sira"],
                bolge_sayisi=satir["bolge_sayisi"] or 0,
            )
        )
    return seriler


def hesapla(
    yol: Path,
    *,
    bolge_kodu: str | None = None,
    siniflar: tuple[str, ...] | None = None,
    sirala: str = "ivme",
    limit: int | None = None,
) -> list[Sinyal]:
    """Depodaki bütün videolar için sinyalleri hesaplar ve sıralar.

    `siniflar` verilirse yalnızca o sınıflar döner — projenin amacı tarih ve
    bilim, ama filtre varsayılan olarak kapalı: sınıflandırıcı henüz karar
    vermemiş videoları da görmek gerekiyor.
    """
    if sirala not in SIRALAMA_ALANLARI:
        raise ValueError(f"bilinmeyen sıralama: {sirala} (geçerli: {SIRALAMA_ALANLARI})")

    baglanti = depo.baglan(yol)
    try:
        seriler = _serileri_oku(baglanti, bolge_kodu)
        if not seriler:
            return []
        videolar = {
            satir["video_id"]: satir
            for satir in baglanti.execute(
                "SELECT video_id, baslik, kanal_adi, sinif, kategori_id, "
                "yayin_zamani, ilk_gorulme FROM video"
            ).fetchall()
        }
    finally:
        baglanti.close()

    sonuclar: list[Sinyal] = []
    for video_id, seri in seriler.items():
        ust = videolar.get(video_id)
        if ust is None:
            continue  # `olcum` var, `video` yok — normalde olamaz
        if siniflar and (ust["sinif"] or "belirsiz") not in siniflar:
            continue
        sonuclar.append(
            turet(
                seri,
                yayin_zamani=_zamana_cevir(ust["yayin_zamani"]),
                ilk_gorulme=_zamana_cevir(ust["ilk_gorulme"]),
                sinyal=Sinyal(
                    video_id=video_id,
                    baslik=ust["baslik"],
                    kanal_adi=ust["kanal_adi"],
                    sinif=ust["sinif"],
                    kategori_id=ust["kategori_id"],
                    olcum_sayisi=len(seri),
                    izlenme=seri[-1].izlenme,
                    son_an=seri[-1].an,
                ),
            )
        )

    sonuclar.sort(key=lambda s: s.sirala_anahtari(sirala), reverse=True)
    return sonuclar[:limit] if limit else sonuclar


@dataclass
class RaporOzeti:
    """Raporun kendisi hakkındaki gerçekler — sinyallerin ne kadar güvenilir
    olduğunu okuyucu bunlardan anlar."""

    video_sayisi: int
    kosu_sayisi: int
    hizi_olan: int
    ivmesi_olan: int
    yeni_giren: int

    def ozet(self) -> str:
        satir = (
            f"{self.video_sayisi} video · {self.kosu_sayisi} koşu · "
            f"{self.hizi_olan} hız · {self.ivmesi_olan} ivme"
        )
        if self.yeni_giren:
            satir += f" · {self.yeni_giren} yeni giren"
        return satir


def rapor_ozeti(yol: Path, sinyaller: list[Sinyal]) -> RaporOzeti:
    baglanti = depo.baglan(yol)
    try:
        kosu = baglanti.execute("SELECT COUNT(DISTINCT an) AS n FROM olcum").fetchone()["n"]
    finally:
        baglanti.close()
    return RaporOzeti(
        video_sayisi=len(sinyaller),
        kosu_sayisi=kosu or 0,
        hizi_olan=sum(1 for s in sinyaller if s.hiz is not None),
        ivmesi_olan=sum(1 for s in sinyaller if s.ivme is not None),
        yeni_giren=sum(1 for s in sinyaller if s.yeni_giren),
    )
