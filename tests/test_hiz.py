"""Hız, ivme ve yaşa göre normalize sinyaller.

Testler ölçümleri doğrudan depoya yazıyor — toplayıcıdan geçmek gerekmiyor,
çünkü `hiz` yalnızca `olcum` + `video` tablolarını okuyor. Zaman damgaları
**bilinçli olarak düzensiz**: modülün tek tasarım şartı bu.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_automation import cli, depo
from yt_automation.trend import hiz

BASLANGIC = datetime(2026, 7, 29, 6, 0, tzinfo=UTC)


def an(saat: float) -> datetime:
    return BASLANGIC + timedelta(hours=saat)


@pytest.fixture
def yaz(yol: Path):
    """Bir video ve ölçümlerini depoya yazar.

    `olcumler`: `(saat, izlenme)` ya da `(saat, izlenme, sıra)` ya da
    `(saat, izlenme, sıra, bölge)`. Saatler `BASLANGIC`'a göreli.
    """

    def kur(
        video_id: str,
        olcumler: list[tuple],
        *,
        yayin_saat: float = -100.0,
        sinif: str | None = None,
        ilk_gorulme_saat: float | None = None,
    ) -> None:
        ilk = ilk_gorulme_saat if ilk_gorulme_saat is not None else olcumler[0][0]
        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                "INSERT OR REPLACE INTO video (video_id, baslik, kanal_adi, yayin_zamani, "
                "kategori_id, sinif, ilk_gorulme) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id,
                    f"Başlık {video_id}",
                    f"Kanal {video_id}",
                    an(yayin_saat).isoformat(),
                    28,
                    sinif,
                    an(ilk).isoformat(),
                ),
            )
            for olcum in olcumler:
                saat, izlenme = olcum[0], olcum[1]
                sira = olcum[2] if len(olcum) > 2 else 1
                bolge = olcum[3] if len(olcum) > 3 else "TR"
                baglanti.execute(
                    "INSERT OR REPLACE INTO olcum (video_id, bolge, an, liste_kategori, "
                    "sira, izlenme) VALUES (?, ?, ?, 28, ?, ?)",
                    (video_id, bolge, an(saat).isoformat(), sira, izlenme),
                )

    return kur


def tek(yol: Path, **p) -> hiz.Sinyal:
    sonuc = hiz.hesapla(yol, **p)
    assert len(sonuc) == 1, f"tek sinyal beklenirken {len(sonuc)} geldi"
    return sonuc[0]


# --- Hız: düzensiz aralık -----------------------------------------------


def test_hiz_gercek_gecen_sureden_hesaplanir(yol: Path, yaz):
    """Kabul ölçütü: 2 saat ve 7 saat sonra gelen iki ölçümle hız doğru.

    Son aralık 7 saat ve 7.000 izlenme kazanılmış → 1.000/saat. "Saatte bir
    koşuyor" varsayan kod 7.000 derdi.
    """
    yaz("v1", [(0, 10_000), (2, 12_000), (9, 19_000)])
    sinyal = tek(yol)

    assert sinyal.hiz == pytest.approx(1_000.0)
    assert sinyal.olcum_sayisi == 3


def test_bosluk_matematigi_bozmaz(yol: Path, yaz):
    """Laptop üç gün kapalı kalırsa çözünürlük düşer, doğruluk düşmez."""
    yaz("v1", [(0, 10_000), (72, 82_000)])
    assert tek(yol).hiz == pytest.approx(1_000.0)


def test_tek_olcumun_hizi_yok(yol: Path, yaz):
    """`None`, sıfır değil: "bilinmiyor" demek."""
    yaz("v1", [(0, 10_000)])
    sinyal = tek(yol, sirala="izlenme")

    assert sinyal.hiz is None
    assert sinyal.ivme is None
    assert sinyal.izlenme == 10_000


def test_cok_yakin_olcumde_daha_geriye_bakilir(yol: Path, yaz):
    """İzlenme sayacı gerçek zamanlı değil, kabaca güncelleniyor.

    Son iki ölçüm 3 dakika arayla: o aralığa bölünürse sonuç anlamsız büyür.
    Modül eşiği geçen en yakın noktaya demirlenmeli — burada t=0.
    """
    yaz("v1", [(0, 10_000), (4.0, 14_000), (4.05, 14_010)])
    sinyal = tek(yol)

    assert sinyal.hiz == pytest.approx(4_010 / 4.05)
    assert sinyal.hiz < 1_100, "3 dakikalık aralığa bölünmüş olmamalı"


def test_hepsi_cok_yakinsa_hiz_yok(yol: Path, yaz):
    yaz("v1", [(0, 10_000), (0.05, 10_010)])
    assert tek(yol).hiz is None


def test_dusen_izlenme_negatif_hiz_verir(yol: Path, yaz):
    """YouTube izlenmeyi geriye düzeltebiliyor. Gerçek bir olay, kırpmıyoruz."""
    yaz("v1", [(0, 10_000), (5, 9_000)])
    assert tek(yol).hiz == pytest.approx(-200.0)


# --- İvme ---------------------------------------------------------------


def test_ivme_esit_araliklarda(yol: Path, yaz):
    """v1=1.000 (orta 1), v2=2.000 (orta 3) → (2.000-1.000)/2 = 500/sa²."""
    yaz("v1", [(0, 0), (2, 2_000), (4, 6_000)])
    sinyal = tek(yol)

    assert sinyal.onceki_hiz == pytest.approx(1_000.0)
    assert sinyal.hiz == pytest.approx(2_000.0)
    assert sinyal.ivme == pytest.approx(500.0)


def test_ivme_orta_noktalara_bolunur(yol: Path, yaz):
    """Düzensiz örneklemede ivmenin tek doğru böleni orta noktalar arası süre.

    t=0/2/9 → v1=1.000 (orta 1), v2=2.000 (orta 5,5). Doğru: 1.000/4,5 ≈ 222.
    Son aralığa bölmek (1.000/7 ≈ 143) ya da ilk aralığa bölmek (500) yanlış.
    """
    yaz("v1", [(0, 0), (2, 2_000), (9, 16_000)])
    sinyal = tek(yol)

    assert sinyal.ivme == pytest.approx(1_000 / 4.5)
    assert sinyal.ivme != pytest.approx(1_000 / 7)
    assert sinyal.ivme != pytest.approx(500.0)


def test_sabit_hizda_ivme_sifir(yol: Path, yaz):
    """Aralıklar farklı ama hız sabit: ivme tam sıfır olmalı, ~sıfır değil."""
    yaz("v1", [(0, 0), (3, 3_000), (8, 8_000)])
    assert tek(yol).ivme == pytest.approx(0.0)


def test_yavaslayan_video_negatif_ivme(yol: Path, yaz):
    """Zirveyi geçmiş video: hâlâ izleniyor ama ivme aşağı. Aradığımız bu değil."""
    yaz("v1", [(0, 0), (2, 4_000), (6, 6_000)])
    sinyal = tek(yol)

    assert sinyal.hiz == pytest.approx(500.0)
    assert sinyal.ivme == pytest.approx(-500.0)


def test_iki_olcumun_ivmesi_yok(yol: Path, yaz):
    """İvme üç nokta istiyor — hız var, ivme yok."""
    yaz("v1", [(0, 10_000), (5, 15_000)])
    sinyal = tek(yol)

    assert sinyal.hiz is not None
    assert sinyal.ivme is None


# --- Yaşa göre normalize -------------------------------------------------


def test_yeni_video_eski_devden_ayrilir(yol: Path, yaz):
    """Kabul ölçütü. Ham izlenmede dev kazanır, yaşa göre yeni video kazanır.

    Dev: 2.000 saatlik, 2.000.000 izlenme → 1.000/saat.
    Yeni: 6 saatlik, 60.000 izlenme → 10.000/saat.
    """
    yaz("dev", [(0, 2_000_000)], yayin_saat=-2_000)
    yaz("yeni", [(0, 60_000)], yayin_saat=-6)

    assert [s.video_id for s in hiz.hesapla(yol, sirala="izlenme")] == ["dev", "yeni"]
    assert [s.video_id for s in hiz.hesapla(yol, sirala="yas")] == ["yeni", "dev"]

    yeni = next(s for s in hiz.hesapla(yol) if s.video_id == "yeni")
    assert yeni.yasa_gore == pytest.approx(10_000.0)
    assert yeni.yas_saat == pytest.approx(6.0)


def test_cok_yeni_video_matematigi_ele_gecirmez(yol: Path, yaz):
    """6 dakikalık video: bölen tabanlanmadan 1.000/saat gösterip zirveye oturur.

    Taban 1 saat olduğu için 100 izlenme 100/saat kalıyor — sinyal değil,
    küçük bölen olduğu görülüyor.
    """
    yaz("v1", [(0, 100)], yayin_saat=-0.1)
    assert tek(yol).yasa_gore == pytest.approx(100.0)


def test_yayin_zamani_yoksa_normalize_yok(yol: Path, yaz):
    yaz("v1", [(0, 5_000)])
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute("UPDATE video SET yayin_zamani = NULL")

    sinyal = tek(yol, sirala="izlenme")
    assert sinyal.yasa_gore is None
    assert sinyal.yas_saat is None


# --- Bölge ve sıra -------------------------------------------------------


def test_izlenme_bolgeler_arasi_tekrarlanmaz(yol: Path, yaz):
    """`viewCount` küresel: aynı koşuda üç bölge = tek nokta, tek hız.

    Bölge başına hesaplanırsa aynı sayı üç kez listeye girer ve çok bölgede
    görünen videolar yapay olarak öne çıkar.
    """
    yaz("v1", [(0, 10_000, 5, "TR"), (0, 10_000, 2, "DE"), (0, 10_000, 9, "FR"), (5, 15_000)])
    sinyal = tek(yol)

    assert sinyal.olcum_sayisi == 2, "üç bölge tek nokta olmalı"
    assert sinyal.hiz == pytest.approx(1_000.0)


def test_en_iyi_sira_bolgeler_arasi_minimum(yol: Path, yaz):
    yaz("v1", [(0, 10_000, 5, "TR"), (0, 10_000, 2, "DE")])
    assert tek(yol, sirala="izlenme").en_iyi_sira == 2


def test_sira_degisiminde_arti_yukari_demek(yol: Path, yaz):
    """10. sıradan 3. sıraya çıkmak `+7`. Ham çıkarma `-7` verirdi."""
    yaz("v1", [(0, 10_000, 10), (5, 15_000, 3)])
    assert tek(yol).sira_degisimi == 7


def test_bolge_yayilimi_olculur(yol: Path, yaz):
    """Bir ülkeden üç ülkeye yayılmak kendi başına sinyal."""
    yaz(
        "v1",
        [(0, 10_000, 1, "TR"), (5, 15_000, 1, "TR"), (5, 15_000, 4, "DE"), (5, 15_000, 7, "FR")],
    )
    sinyal = tek(yol)

    assert sinyal.bolge_sayisi == 3
    assert sinyal.bolge_yayilimi == 2


def test_bolge_filtresi(yol: Path, yaz):
    yaz("sadece_tr", [(0, 10_000, 1, "TR")])
    yaz("sadece_de", [(0, 20_000, 1, "DE")])

    assert [s.video_id for s in hiz.hesapla(yol, bolge_kodu="DE")] == ["sadece_de"]


# --- Eksik veri ----------------------------------------------------------


def test_gizli_istatistik_olcumu_atlanir(yol: Path, yaz):
    """İzlenmesi `NULL` gelen ölçüm sıfır sayılırsa sahte bir çöküş üretir."""
    yaz("v1", [(0, 10_000), (5, 15_000)])
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO olcum (video_id, bolge, an, sira, izlenme) VALUES (?, ?, ?, 1, NULL)",
            ("v1", "TR", an(10).isoformat()),
        )

    sinyal = tek(yol)
    assert sinyal.olcum_sayisi == 2
    assert sinyal.izlenme == 15_000
    assert sinyal.hiz == pytest.approx(1_000.0), "NULL ölçüm hıza karışmamalı"


def test_olcumu_olmayan_video_listede_yok(yol: Path):
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO video (video_id, baslik, ilk_gorulme) VALUES ('yok', 'X', ?)",
            (an(0).isoformat(),),
        )
    assert hiz.hesapla(yol) == []


# --- Listeye giriş -------------------------------------------------------


def test_yeni_giren_isaretlenir(yol: Path, yaz):
    """Çarta ilk kez düşmek, çartta durmaktan farklı bir olay."""
    yaz("yeni", [(0, 5_000)], ilk_gorulme_saat=0)
    yaz("eski", [(-24, 5_000), (0, 6_000)], ilk_gorulme_saat=-24)

    sinyaller = {s.video_id: s for s in hiz.hesapla(yol, sirala="izlenme")}
    assert sinyaller["yeni"].yeni_giren is True
    assert sinyaller["eski"].yeni_giren is False


# --- Sıralama ------------------------------------------------------------


def test_hesaplanamayan_ivme_sona_gider(yol: Path, yaz):
    """Negatif ivme ile "ivme bilinmiyor" aynı kovaya düşmemeli.

    `float("-inf")` ile sıralamak ikisini karıştırırdı: ölçülmüş bir düşüş,
    hiç ölçülmemiş olmaktan daha çok bilgi taşıyor.
    """
    yaz("yukselen", [(0, 0), (2, 2_000), (4, 6_000)])  # ivme +500
    yaz("dusen", [(0, 0), (2, 4_000), (6, 6_000)])  # ivme -500
    yaz("olcumsuz", [(0, 999_999)])  # ivme None

    assert [s.video_id for s in hiz.hesapla(yol, sirala="ivme")] == [
        "yukselen",
        "dusen",
        "olcumsuz",
    ]


def test_sinif_filtresi(yol: Path, yaz):
    yaz("t", [(0, 10_000)], sinif="tarih")
    yaz("b", [(0, 20_000)], sinif="bilim")
    yaz("d", [(0, 30_000)], sinif="diger")

    sonuc = hiz.hesapla(yol, siniflar=("tarih", "bilim"), sirala="izlenme")
    assert [s.video_id for s in sonuc] == ["b", "t"]


def test_siniflandirilmamis_video_belirsiz_sayilir(yol: Path, yaz):
    """`sinif` `NULL` olan video filtreden düşerse yeni toplanan her şey kaybolur."""
    yaz("v1", [(0, 10_000)])
    assert hiz.hesapla(yol, siniflar=("belirsiz",), sirala="izlenme")[0].video_id == "v1"


def test_limit_uygulanir(yol: Path, yaz):
    for i in range(5):
        yaz(f"v{i}", [(0, 1_000 * (i + 1))])
    assert len(hiz.hesapla(yol, sirala="izlenme", limit=2)) == 2


def test_bilinmeyen_siralama_reddedilir(yol: Path):
    with pytest.raises(ValueError, match="bilinmeyen sıralama"):
        hiz.hesapla(yol, sirala="popülerlik")


# --- Özet ve CLI ---------------------------------------------------------


def test_rapor_ozeti_kosu_sayar(yol: Path, yaz):
    yaz("v1", [(0, 0), (2, 2_000), (4, 6_000)])
    yaz("v2", [(4, 500)], ilk_gorulme_saat=4)

    sinyaller = hiz.hesapla(yol, sirala="izlenme")
    ozet = hiz.rapor_ozeti(yol, sinyaller)

    assert ozet.video_sayisi == 2
    assert ozet.kosu_sayisi == 3, "farklı `an` sayısı"
    assert ozet.hizi_olan == 1
    assert ozet.ivmesi_olan == 1
    assert ozet.yeni_giren == 1


def test_cli_rapor_sirali_cikti_verir(yol: Path, yaz, monkeypatch, capsys):
    """Kabul ölçütü: `ytoto trend rapor` yerel sıralanmış çıktı veriyor."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    yaz("hizli", [(0, 0), (2, 2_000), (4, 6_000)])
    yaz("yavas", [(0, 0), (2, 4_000), (6, 6_000)])

    assert cli.main(["trend", "rapor"]) == 0
    cikti = capsys.readouterr().out
    assert cikti.index("Başlık hizli") < cikti.index("Başlık yavas")
    # Ayrı `an` damgaları: 0, 2, 4, 6 → dört koşu.
    assert "2 video · 4 koşu · 2 hız · 2 ivme" in cikti


def test_cli_rapor_bos_depoda_uyarir(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    assert cli.main(["trend", "rapor"]) == 1
    assert "trend topla" in capsys.readouterr().out


def test_cli_rapor_tek_kosuda_uyarir(yol: Path, yaz, monkeypatch, capsys):
    """Tek koşuda hız yok. Bunu söylememek, sıfır hızı gerçek sanmaya yol açar."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    yaz("v1", [(0, 10_000)])

    assert cli.main(["trend", "rapor"]) == 0
    assert "Tek koşu var" in capsys.readouterr().err
