"""TikTok kaynağı — ölçülmüş kısıt ve elle besleme yolu (DW-56).

Bu dosyada canlı çağrı yok ve olmayacak: TikTok'un ücretsiz ucu
kimlik doğrulaması istiyor (2026-08-03 ölçümü, modül docstring'inde).
Testler beslemenin ve **yumuşak düşmenin** doğruluğunu kilitliyor.
"""

from pathlib import Path

from yt_automation import cli, depo
from yt_automation.trend import gtrends, tiktok


def test_hashtag_terime_cevrilir():
    assert tiktok.terime_cevir("#AncientRome") == "Ancient Rome"
    assert tiktok.terime_cevir("#ancient_rome") == "ancient rome"
    assert tiktok.terime_cevir("roman-empire") == "roman empire"
    assert tiktok.terime_cevir("  ") == ""
    assert tiktok.terime_cevir("// yorum") == ""


def test_dosya_yoksa_sessizce_atlanir(yol: Path, monkeypatch):
    """Yapılandırılmamış kaynak hata değil: huni etkilenmemeli."""
    monkeypatch.delenv(tiktok.DOSYA_DEGISKENI, raising=False)
    sonuc = tiktok.isle(yol)
    assert sonuc.terim == 0
    assert sonuc.hatalar == []


def test_var_olmayan_dosya_cokmez(yol: Path, monkeypatch):
    monkeypatch.setenv(tiktok.DOSYA_DEGISKENI, "/yok/boyle/bir/dosya.txt")
    assert tiktok.dosya_yolu() is None
    assert tiktok.isle(yol).terim == 0


def test_terimler_ayni_boruya_girer(yol: Path, tmp_path: Path, monkeypatch):
    """ADR-0010: kaynak çoğalır, boru tektir. TikTok kendi yazma/sınıflandırma
    kodunu kopyalamıyor — `gtrends.isle` yeniden kullanılıyor."""
    besleme = tmp_path / "tiktok.txt"
    besleme.write_text("#PompeiiEruption\n// not\n#ancient_rome\n", encoding="utf-8")
    monkeypatch.setenv(tiktok.DOSYA_DEGISKENI, str(besleme))
    monkeypatch.setattr(gtrends, "_siniflandir", lambda dil, baslik: ("tarih", "Q1"))
    monkeypatch.setattr(
        gtrends.wikipedia,
        "makale_serisi",
        lambda dil, baslik, bas, son: [
            gtrends.wikipedia.Okunma(dil=dil, baslik=baslik, gun="2026-08-02", okunma=4_000)
        ],
    )

    sonuc = tiktok.isle(
        yol,
        pazarlar=("en",),
        makale_bul=lambda dil, terim: terim.title().replace(" ", "_"),
    )

    assert sonuc.terim == 2, "yorum satırı elenmeli"
    assert sonuc.yazilan == 2
    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute(
            "SELECT sinif_kaynagi FROM makale WHERE baslik = 'Pompeii_Eruption'"
        ).fetchone()
        assert satir is not None, "konu boruya yazılmalı"
        seri = baglanti.execute("SELECT COUNT(*) n FROM okunma").fetchone()["n"]
        assert seri == 2, "talep kanıtı olmadan konu kuyruğa giremez"
    finally:
        baglanti.close()


def test_cli_tiktok_yapilandirilmamisken_bildirir(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    monkeypatch.delenv(tiktok.DOSYA_DEGISKENI, raising=False)
    monkeypatch.setattr(gtrends, "isle", lambda *a, **k: gtrends.IslemeSonucu(terim=3))

    assert cli.main(["konu", "gtrends"]) == 0
    cikti = capsys.readouterr().out
    assert "tiktok · atlandı" in cikti


def test_kisitlar_belgeleniyor():
    """Ölçüm modülde yazılı kalmalı: sonraki kişi aynı ucu yeniden denemesin."""
    assert "40101" in tiktok.__doc__
    assert "Research API" in tiktok.__doc__
