"""Zamanlanmış otomasyonun kabuk katmanı.

Buradaki testler Python koduna değil **betiklere** bakıyor, çünkü DW-47'nin
sebebi olan iki hata da orada yaşıyordu:

1. `launchd` var olmayan bir betiği çağırdı ve beş saat boyunca 127 verdi.
2. `.env`'deki boş bir değer, plist'ten gelen gerçek veri yolunu ezebiliyordu.

En değerlisi `test_huni_komutlari_gercekten_var`: gece koşan bir betikteki
komut adı yeniden adlandırıldığında bunu ertesi sabah Notion'da aday
görmeyerek değil, CI'da kırmızı görerek öğrenmek istiyoruz.
"""

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from yt_automation import cli

KOK = Path(__file__).resolve().parent.parent
BETIKLER = KOK / "scripts"

CALISTIRILABILIR = ("saatlik-tarama.sh", "gunluk-huni.sh", "zamanlama-kur.sh")


def huni_adimlari() -> list[list[str]]:
    """`gunluk-huni.sh` içindeki `adim` çağrılarının CLI argümanlarını çıkarır.

    Satır biçimi: `adim <ad> <kuru_destekli> <cli argümanları…>`
    Kabuk değişkenleri (`"$SONDAJ"` gibi) hep sayı taşıyor; testte `1` konuyor.
    """
    metin = (BETIKLER / "gunluk-huni.sh").read_text(encoding="utf-8")
    adimlar = []
    for satir in metin.splitlines():
        if not satir.strip().startswith("adim "):
            continue
        parcalar = shlex.split(satir.strip())
        adimlar.append(["1" if p.startswith("$") else p for p in parcalar[3:]])
    return adimlar


@pytest.mark.parametrize("argumanlar", huni_adimlari(), ids=lambda a: " ".join(a[:2]))
def test_huni_komutlari_gercekten_var(argumanlar: list[str], capsys):
    """Betikteki her komut ve bayrak `cli`'da hâlâ tanımlı mı.

    `--help` argparse'ı komutu çalıştırmadan doğrulatıyor: alt komut ya da
    bayrak yoksa çıkış kodu 2 olur.
    """
    with pytest.raises(SystemExit) as cikis:
        cli.main([*argumanlar, "--help"])
    assert cikis.value.code == 0
    capsys.readouterr()


def test_huni_sirasi_aktarim_bagimliliklarina_uyuyor():
    """`trend aktar` hem sondajdan hem kaynak çekiminden SONRA gelmeli.

    `notion.aktarilmamis_bosluklar` bir adayı ancak arzı ölçülmüş **ve**
    kaynak dosyası çekilmişse aktarılabilir sayıyor. Sıra bozulursa huni
    hatasız koşar ve hiçbir şey aktarmaz — en sinsi başarısızlık biçimi.
    """
    sira = [" ".join(a[:2]) for a in huni_adimlari()]
    assert sira.index("konu topla") < sira.index("bosluk arastir")
    assert sira.index("bosluk arastir") < sira.index("trend aktar")
    assert sira.index("konu kaynak") < sira.index("trend aktar")


def test_sondaj_adimi_limit_tasiyor():
    """Sondaj huninin tek pahalı adımı (102 birim/sondaj); limitsiz koşmamalı."""
    sondaj = next(a for a in huni_adimlari() if a[:2] == ["bosluk", "arastir"])
    assert "--limit" in sondaj


@pytest.mark.parametrize("ad", CALISTIRILABILIR)
def test_betikler_calistirilabilir_ve_korumali(ad: str):
    betik = BETIKLER / ad
    assert betik.exists(), f"{ad} yok"
    assert os.access(betik, os.X_OK), f"{ad} çalıştırılabilir değil"
    assert "set -uo pipefail" in betik.read_text(encoding="utf-8")


def test_ortak_onyukleme_iki_betikte_de_kullaniliyor():
    """Ortam kurulumu tek yerde; iki betikte ayrı ayrı durursa biri sapar."""
    for ad in ("saatlik-tarama.sh", "gunluk-huni.sh"):
        assert "ortak.sh" in (BETIKLER / ad).read_text(encoding="utf-8")


def test_plist_yer_tutucularinin_hepsi_dolduruluyor():
    """Şablondaki her `__YERTUTUCU__`'nun kurulumda bir `sed` karşılığı var.

    Eksik kalan bir yer tutucu plist'e ham metin olarak gider ve `launchd`
    onu yol sanar — yine sessiz bir 127.
    """
    plist = (BETIKLER / "works.duo.yt-trend.plist").read_text(encoding="utf-8")
    kurulum = (BETIKLER / "zamanlama-kur.sh").read_text(encoding="utf-8")

    yer_tutucular = set(re.findall(r"__[A-Z]+__", plist))
    sedler = set(re.findall(r"s\|(__[A-Z]+__)\|", kurulum))

    assert yer_tutucular, "şablonda hiç yer tutucu yok"
    assert yer_tutucular == sedler


def test_gunluk_nobet_dosyalari_tarihe_gore_adlandiriliyor():
    """Geniş tarama ve huni günde bir kez; nöbet dosyası ISO tarih taşıyor."""
    metin = (BETIKLER / "saatlik-tarama.sh").read_text(encoding="utf-8")
    assert ".genis-$(date +%Y-%m-%d)" in metin
    assert ".huni-$(date +%Y-%m-%d)" in metin


def test_huni_nobeti_yalnizca_basarida_konuyor():
    """Düşen huni ertesi saat yeniden denenmeli.

    Güvenli, çünkü tek pahalı adım `bosluk.SONDAJ_KOTA_TAVANI` ile ayrıca
    sınırlı. `touch` başarısızlık dalında olsaydı tek bir geçici ağ hatası
    o günün bütün adaylarını kaybettirirdi.
    """
    metin = (BETIKLER / "saatlik-tarama.sh").read_text(encoding="utf-8")
    blok = metin.split("HUNI_NOBET=")[1]
    govde = blok.split("# Eski günlükleri temizle")[0]
    basari_dali, _, hata_dali = govde.partition("else")
    assert 'touch "$HUNI_NOBET"' in basari_dali
    assert 'touch "$HUNI_NOBET"' not in hata_dali


def test_env_bos_degeri_launchd_yolunu_ezemez(tmp_path: Path):
    """`.env`'deki boş `YT_OTOMASYON_VERI` plist'ten geleni ezmemeli.

    `.env.example` bu satırı boş taşıyor. `set -a` ile kaynaklandığında boş
    değer `launchd`'ın verdiği gerçek yolu ezer ve depo, geliştirme ağacı
    yerine worktree'nin içine yazılırdı: iki ayrı veritabanı, hiç hata yok.

    Bu test gerçekten `bash` çalıştırıyor — kabuk davranışını metin arayarak
    değil koşturarak doğruluyor.
    """
    proje = tmp_path / "kod"
    (proje / "scripts").mkdir(parents=True)
    shutil.copy(BETIKLER / "ortak.sh", proje / "scripts" / "ortak.sh")

    env_dosya = tmp_path / ".env"
    env_dosya.write_text("YT_OTOMASYON_VERI=\nYOUTUBE_API_KEY=sahte\n", encoding="utf-8")

    gercek_veri = tmp_path / "gercek-veri"
    gercek_veri.mkdir()

    sonuc = subprocess.run(
        ["bash", "-c", f'. "{proje}/scripts/ortak.sh"; printf "%s" "$VERI_DIZIN"'],
        env={
            "HOME": str(tmp_path),
            "PATH": os.environ["PATH"],
            "YT_OTOMASYON_KOK": str(proje),
            "YT_OTOMASYON_VERI": str(gercek_veri),
            "YT_OTOMASYON_ENV": str(env_dosya),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert sonuc.stdout == str(gercek_veri), sonuc.stderr


def test_env_ornegi_yeni_degiskenleri_belgeliyor():
    """CLAUDE.md kural 6: yeni değişken `.env.example`'a değersiz eklenir."""
    ornek = (KOK / ".env.example").read_text(encoding="utf-8")
    for degisken in (
        "YT_OTOMASYON_KOK",
        "YT_OTOMASYON_CALISMA",
        "YT_OTOMASYON_ENV",
        "YT_OTOMASYON_GUNLUK",
    ):
        assert f"\n{degisken}=\n" in ornek, f"{degisken} .env.example'da değersiz yok"


def test_kurulum_worktree_kuruyor_ve_tazeleme_sunuyor():
    """ADR-0008'in özü: kod ayrı worktree'de ve ref bilinçli seçiliyor."""
    kurulum = (BETIKLER / "zamanlama-kur.sh").read_text(encoding="utf-8")
    assert "worktree add --detach" in kurulum
    assert "tazele)" in kurulum
    # `durum` sağlıksızsa sıfırdan farklı dönmeli; betikten kontrol edilebilsin.
    assert 'exit "$saglikli"' in kurulum
