"""Videoların kategori + konu etiketiyle sınıflandırması. Hiç çağrı yok."""

import json
from datetime import UTC, datetime
from pathlib import Path

from yt_automation import cli, depo
from yt_automation.trend import video_sinif

SIMDI = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def etiket(*adlar: str) -> str:
    return json.dumps([f"https://en.wikipedia.org/wiki/{a}" for a in adlar])


def yaz(yol: Path, video_id: str, *, kategori: int | None = None, etiketler: str | None = None):
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT OR REPLACE INTO video (video_id, baslik, kategori_id, "
            "konu_etiketleri, ilk_gorulme) VALUES (?, ?, ?, ?, ?)",
            (video_id, f"Başlık {video_id}", kategori, etiketler, SIMDI.isoformat()),
        )


def sinif_oku(yol: Path, video_id: str) -> tuple[str, str]:
    baglanti = depo.baglan(yol)
    try:
        s = baglanti.execute(
            "SELECT sinif, sinif_kaynagi FROM video WHERE video_id = ?", (video_id,)
        ).fetchone()
    finally:
        baglanti.close()
    return (s["sinif"], s["sinif_kaynagi"])


# --- Etiket ayıklama -----------------------------------------------------


def test_url_son_parcasi_alinir():
    assert video_sinif.etiketleri_ayikla(etiket("History", "Music")) == {"History", "Music"}


def test_bozuk_json_cokmez():
    assert video_sinif.etiketleri_ayikla("{bozuk") == set()
    assert video_sinif.etiketleri_ayikla(None) == set()
    assert video_sinif.etiketleri_ayikla("") == set()


# --- Sınıflandırma -------------------------------------------------------


def test_tarih_etiketi_taniniyor():
    assert video_sinif.siniflandir(None, etiket("History")) == "tarih"
    assert video_sinif.siniflandir(None, etiket("Military_history")) == "tarih"


def test_bilim_etiketi_taniniyor():
    assert video_sinif.siniflandir(None, etiket("Physics")) == "bilim"
    assert video_sinif.siniflandir(None, etiket("Knowledge")) == "bilim"


def test_dislama_once_gelir():
    """Bir "Knowledge" etiketi taşıyan pop şarkısı bilim değil.

    Knowledge Graph geniş eşleme yapıyor; sıra tersine olsa müzik videoları
    bilim listesine sızardı. `konu.siniflandir()` ile aynı desen.
    """
    assert video_sinif.siniflandir(None, etiket("Knowledge", "Pop_music")) == "diger"
    assert video_sinif.siniflandir(None, etiket("History", "Video_game_culture")) == "diger"


def test_tanimadigimiz_etiket_belirsiz():
    """Karar vermemek, yanlış karar vermekten iyi."""
    assert video_sinif.siniflandir(None, etiket("Technology")) == "belirsiz"


def test_kategori_tek_basina_bilim_demiyor():
    """DW-28'de ölçüldü: "Bilim & Teknoloji" listesinin ilk 12'si telefon incelemesi.

    Kategori 28 ilgisiz olduğunu da söylemiyor, o yüzden `belirsiz`.
    """
    assert video_sinif.siniflandir(28, None) == "belirsiz"
    assert video_sinif.siniflandir(27, None) == "belirsiz"


def test_ilgisiz_kategori_diger():
    assert video_sinif.siniflandir(10, None) == "diger"
    assert video_sinif.siniflandir(None, None) == "diger"


def test_etiket_kategoriyi_ezer():
    """Etiket daha zengin bir sinyal; kategori yalnızca etiket yokken bakılıyor."""
    assert video_sinif.siniflandir(28, etiket("Pop_music")) == "diger"
    assert video_sinif.siniflandir(10, etiket("History")) == "tarih"


# --- Uygulama -----------------------------------------------------------


def test_bos_sinifi_dolduruyor(yol: Path):
    yaz(yol, "tarih1", etiketler=etiket("History"))
    yaz(yol, "muzik", etiketler=etiket("Music"))
    sonuc = video_sinif.uygula(yol)

    assert sonuc.islenen == 2
    assert sonuc.siniflar == {"tarih": 1, "diger": 1}
    assert sinif_oku(yol, "tarih1") == ("tarih", "konu")


def test_siniflandirilmis_video_tekrar_islenmiyor(yol: Path):
    yaz(yol, "v1", etiketler=etiket("History"))
    video_sinif.uygula(yol)
    assert video_sinif.uygula(yol).islenen == 0


def test_yeniden_llm_kararini_korur(yol: Path):
    """LLM daha fazla bilgiyle bakıyor; kategori/konu katmanı onu ezmemeli.

    Aynı koruma `konu_toplayici._sinifi_yaz`'da da var.
    """
    yaz(yol, "v1", etiketler=etiket("Music"))
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute("UPDATE video SET sinif = 'tarih', sinif_kaynagi = 'llm'")

    sonuc = video_sinif.uygula(yol, yeniden=True)
    assert sonuc.islenen == 0
    assert sinif_oku(yol, "v1") == ("tarih", "llm")


def test_yeniden_konu_kararini_hesaplar(yol: Path):
    """Etiket kümesi genişletildiğinde eski kararların güncellenmesi gerekiyor."""
    yaz(yol, "v1", etiketler=etiket("History"))
    video_sinif.uygula(yol)
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute("UPDATE video SET sinif = 'diger' WHERE video_id = 'v1'")

    assert video_sinif.uygula(yol, yeniden=True).islenen == 1
    assert sinif_oku(yol, "v1") == ("tarih", "konu")


# --- CLI -----------------------------------------------------------------


def test_cli_hic_ilgili_video_yoksa_sebebini_soyluyor(yol: Path, monkeypatch, capsys):
    """Canlı koşumda 4.905 videoda sıfır tarih çıktı. Bu beklenen ve söylenmeli;
    yoksa kullanıcı sınıflandırıcının bozuk olduğunu düşünür."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    yaz(yol, "v1", etiketler=etiket("Music"))

    assert cli.main(["trend", "siniflandir"]) == 0
    # `readouterr()` tamponu boşaltıyor — iki kez çağırmak ikinciyi boş bırakır.
    yakalanan = capsys.readouterr()
    assert "1 video sınıflandırıldı" in yakalanan.out
    assert "Aday üretimi" in yakalanan.err


def test_cli_ilgili_video_varsa_uyarmiyor(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    yaz(yol, "v1", etiketler=etiket("History"))

    assert cli.main(["trend", "siniflandir"]) == 0
    assert "Aday üretimi" not in capsys.readouterr().err
