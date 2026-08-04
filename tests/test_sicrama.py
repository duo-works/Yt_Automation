"""Sıçrama detektörü — patlayan konunun huniyi beklememesi (DW-54).

`okunma` serileri DW-34'ten beri birikiyor ama gün-üstü-gün kıyas hiç
yapılmıyordu; bir konu patladıktan en geç ~30 saat sonra haberimiz oluyordu.
Bu testler tanımın kendisini kilitliyor: oran, taban penceresi, asgari taban
günü, mutlak talep tabanı ve son günün tabana girmemesi.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from yt_automation import cli, depo
from yt_automation.trend import bosluk, sicrama

SIMDI = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _seri(yol: Path, baslik: str, gunluk: list[int], *, dil: str = "en", sinif: str = "tarih"):
    """Son elemanı en son gün olacak şekilde okunma serisi + makale yazar."""
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT OR REPLACE INTO makale (dil, baslik, qid, sinif, sinif_kaynagi, ilk_gorulme)"
            " VALUES (?, ?, ?, ?, 'wikidata', ?)",
            (dil, baslik, f"Q-{baslik}", sinif, SIMDI.isoformat()),
        )
        for i, okunma in enumerate(gunluk):
            gun = (SIMDI - timedelta(days=len(gunluk) - 1 - i)).date().isoformat()
            baglanti.execute(
                "INSERT OR REPLACE INTO okunma (dil, baslik, gun, okunma, sira)"
                " VALUES (?, ?, ?, ?, 1)",
                (dil, baslik, gun, okunma),
            )


def test_uc_kat_sicrama_yakalanir(yol: Path):
    _seri(yol, "Patlayan", [2_000, 2_100, 1_900, 2_000, 8_000])

    tespitler = sicrama.tespit_et(yol)
    assert [t.baslik for t in tespitler] == ["Patlayan"]
    assert tespitler[0].oran == 4.0
    assert tespitler[0].taban == 2_000


def test_dalgalanma_sicrama_sayilmaz(yol: Path):
    """Hafta içi/sonu salınımı 2 katı bulabiliyor; 3 kat eşiği onun dışında."""
    _seri(yol, "Salinan", [2_000, 3_500, 2_200, 2_000, 4_100])
    assert sicrama.tespit_et(yol) == []


def test_dusuk_tabanli_gurultu_elenir(yol: Path):
    """300 → 900 oransal sıçramadır ama video yapılacak talep değildir —
    DW-51'in talep kapısıyla aynı sabit, aynı gerekçe."""
    _seri(yol, "Cilik", [300, 320, 290, 900])
    assert sicrama.tespit_et(yol) == []
    assert bosluk.ASGARI_TALEP * 3 > 900, "test kurulumu sabitle tutarlı kalsın"


def test_yeni_konu_taban_yokken_sicrama_sayilmaz(yol: Path):
    """İki günlük seriden '3 kat' çıkarmak örneklem gürültüsü ölçmektir."""
    _seri(yol, "Yeni", [2_000, 9_000])
    assert sicrama.tespit_et(yol) == []


def test_son_gun_tabana_girmez(yol: Path):
    """Sıçrama kendi tabanını yükseltip kendini gizleyemez."""
    _seri(yol, "Konu", [2_000, 2_000, 2_000, 12_000])
    tespitler = sicrama.tespit_et(yol)
    assert tespitler and tespitler[0].taban == 2_000, "12.000 tabana karışmamalı"


def test_diger_sinifi_izlenmez(yol: Path):
    """Acil kuyruğu üretim kuyruğudur; `diger` 50 kat da sıçrasa video olmaz."""
    _seri(yol, "Magazin", [2_000, 2_000, 2_000, 50_000], sinif="diger")
    assert sicrama.tespit_et(yol) == []


def test_sicrayan_kuyrugun_basina_gecer(yol: Path):
    """Sıradan aday yarın da sorulabilir; sıçramanın yarını yok."""
    _seri(yol, "Sakin_Buyuk", [90_000, 90_000, 90_000, 91_000])
    _seri(yol, "Patlayan_Kucuk", [1_500, 1_400, 1_600, 6_000])

    kuyruk = bosluk.sondajlanmamis_adaylar(
        yol, pazarlar=("en",), oncelikli_qidler=sicrama.sicrayan_qidler(yol)
    )
    assert [a["baslik"] for a in kuyruk] == ["Patlayan_Kucuk", "Sakin_Buyuk"]


def test_acil_aday_notion_durumuyla_gider(yol: Path, monkeypatch):
    """Uçtan uca: sıçrayan aday kapıları geçtiyse Durum=🔥 Acil yazılır."""
    from yt_automation.trend import notion

    # Pazar tabanı: kapının çalışması için 6 sıradan ölçüm (DW-51 idiyomu).
    for i in range(6):
        _seri(yol, f"taban_{i}", [40_000, 40_000, 40_000, 40_000])
        _arz(yol, f"Q-taban_{i}", izlenme=400_000 * 2**i)
    _seri(yol, "Patlayan", [2_000, 2_000, 2_000, 9_000])
    _arz(yol, "Q-Patlayan", izlenme=800)

    govdeler = []

    def sahte_istek(yol_api, govde, token):
        govdeler.append(govde)
        return {"url": "https://notion.so/x", "id": "id-1"}

    monkeypatch.setattr(notion, "_istek", sahte_istek)
    notion.bosluklari_aktar(
        yol,
        adaylar=notion.aktarilmamis_bosluklar(yol),
        database="db",
        token="t",
        an=SIMDI,
        acil_qidler=sicrama.sicrayan_qidler(yol),
    )

    durumlar = {
        g["properties"]["Başlık"]["title"][0]["text"]["content"]: g["properties"]["Durum"][
            "select"
        ]["name"]
        for g in govdeler
    }
    assert durumlar["Patlayan"] == "🔥 Acil"
    assert all(d == "Yeni" for b, d in durumlar.items() if b != "Patlayan")


def _arz(yol: Path, qid: str, *, izlenme: int):
    bosluk.olcumu_yaz(
        yol,
        bosluk.ArzOlcumu(
            qid=qid,
            dil="en",
            sorgu="x",
            an=SIMDI.isoformat(),
            donen=50,
            alakali=20,
            medyan_izlenme=izlenme,
            medyan_yas_gun=300,
            medyan_abone=5_000,
            harcanan=102,
        ),
    )


def test_cli_arastir_sicramayi_kuyruk_basina_bildirir(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    _seri(yol, "Patlayan", [2_000, 2_000, 2_000, 9_000])

    assert cli.main(["bosluk", "arastir", "--kuru"]) == 0
    cikti = capsys.readouterr().out
    assert "sıçrama tespit edildi" in cikti
    assert "4.5×" in cikti


def test_huni_betigi_acil_aday_bildirimi_tasiyor():
    """Diller arası sözleşme: betik CLI'ın 'acil aday' metnini arıyor.

    CLI tarafı `_trend_aktar` basar; metin değişirse bildirim sessizce ölür.
    """
    betik = (Path(__file__).resolve().parent.parent / "scripts" / "gunluk-huni.sh").read_text(
        encoding="utf-8"
    )
    assert 'grep -qi "acil aday"' in betik
