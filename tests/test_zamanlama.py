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
from yt_automation.trend import bosluk

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


def test_bos_gun_hata_sayilmiyor():
    """İşlenecek aday kalmaması normal hâl; bildirim tetiklememeli.

    Sondaj tavanı dolduğunda ya da o günün adayları zaten aktarılmışsa üç
    adım birden sıfırdan farklı dönüyor. Boş günü hata sayarsak bildirim her
    gün gelir, kimse bakmaz ve DW-47'nin çözdüğü sessiz başarısızlık bu kez
    gürültünün içinde kaybolur.
    """
    metin = (BETIKLER / "gunluk-huni.sh").read_text(encoding="utf-8")
    assert 'grep -qi "aday yok"' in metin


def test_kota_tavani_hata_sayilmiyor():
    """Tavan dolduğunda çıktı "aday yok" değil — ayrı bir desen gerekiyor.

    Bu ayrım gözden kaçmıştı: `test_bos_gun_hata_sayilmiyor` docstring'i tavan
    hâlini kapsadığını söylüyordu ama aday kuyrukta dururken bütçe biterse
    `bosluk arastir` "0 sondaj · 0 birim · KOTA TAVANINDA DURDU" basıyor ve
    hiçbir desene uymadığı için adım **hata** sayılıyordu. Tavan tam olarak
    durdurmak için var; dolduğu her gün bildirim göndermek yanlış alarm.
    """
    metin = (BETIKLER / "gunluk-huni.sh").read_text(encoding="utf-8")
    assert 'grep -q "KOTA TAVANINDA DURDU"' in metin


def test_kota_tavani_deseni_turkce_kucultmeye_guvenmiyor():
    """Desen `-i` ile yazılmamalı — Türkçe'de "I" ile "ı" ayrı harfler.

    İlk düzeltme `grep -qi "kota tavanında durdu"` idi ve üretimde **hiç
    tutmayacaktı**: `grep -i` ASCII "I"yı dotless "ı" ile katlamaz, yani
    "KOTA TAVANINDA DURDU" çıktısı desene uymaz ve yanlış alarm sürerdi.
    Aynı tuzak Python'da da var (`"TAVANINDA".lower()` → "tavaninda").
    """
    metin = (BETIKLER / "gunluk-huni.sh").read_text(encoding="utf-8")
    # Yorumda ifade geçebilir; yasak olan **komut** biçimi.
    assert 'grep -qi "kota tavanında durdu"' not in metin
    assert 'grep -qi "KOTA TAVANINDA DURDU"' not in metin


def test_kota_tavani_metni_sozlesme():
    """Betiğin aradığı metni `ArastirmaSonucu` üretmeye devam etmeli.

    Sözleşmenin iki ucu: betik bu ifadeyi arıyor, CLI bu ifadeyi basıyor.
    Biri yeniden yazılırsa tavanın dolduğu gece yanlış alarm geri gelir.
    """
    assert "KOTA TAVANINDA DURDU" in bosluk.ArastirmaSonucu(kota_bitti=True).ozet()


@pytest.mark.parametrize(
    "cagri",
    [
        ["bosluk", "arastir"],
        ["konu", "kaynak"],
        ["trend", "aktar"],
        ["konu", "listele"],
    ],
    ids=lambda c: " ".join(c),
)
def test_bos_sonuc_metni_huninin_bekledigi_gibi(cagri, tmp_path, monkeypatch, capsys):
    """Boş sonuç mesajları "aday yok" ifadesini taşımaya devam ediyor mu.

    `gunluk-huni.sh` boş günü bu metinden tanıyor. Mesaj yeniden yazılırsa
    huni her boş günü hata sayar ve gece yarısı yanlış alarm üretir — bunu
    üretimde değil burada yakalamak istiyoruz.
    """
    monkeypatch.setenv("YT_OTOMASYON_VERI", str(tmp_path))
    assert cli.main(cagri) != 0
    cikti = capsys.readouterr()
    assert "aday yok" in (cikti.out + cikti.err).lower()


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


def test_kurulum_veri_yolunu_ana_agacta_ariyor(tmp_path: Path):
    """Geliştirme worktree'sinden çalıştırılsa bile veri ANA ağaçta aranmalı.

    Bu fiilen ters gitti: betik bir ajan worktree'sinden koşturulunca `.env`
    ve `veri/` orada arandı, ikisi de yoktu ve görev boş bir veritabanına
    bağlanacaktı — ADR-0008'in "iki ayrı veritabanı" hatasının başka kapıdan
    gelen hâli. `--git-common-dir` her worktree'de ana depoyu gösteriyor.
    """
    ana = tmp_path / "ana"
    (ana / "scripts").mkdir(parents=True)
    shutil.copy(BETIKLER / "zamanlama-kur.sh", ana / "scripts" / "zamanlama-kur.sh")

    kimlik = ["-c", "user.email=test@duo.works", "-c", "user.name=test"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(ana)], check=True)
    subprocess.run(["git", "-C", str(ana), *kimlik, "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ana), *kimlik, "commit", "-qm", "ilk"], check=True)

    dal = tmp_path / "dal"
    subprocess.run(
        ["git", "-C", str(ana), "worktree", "add", "-q", "--detach", str(dal)], check=True
    )

    sonuc = subprocess.run(
        ["bash", str(dal / "scripts" / "zamanlama-kur.sh"), "durum"],
        env={"HOME": str(tmp_path), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )

    assert str(ana / "veri") in sonuc.stdout, sonuc.stdout
    assert str(dal / "veri") not in sonuc.stdout


def test_kurulum_sirsiz_kurmuyor():
    """`.env` yoksa `kur` durmalı — uyarıp devam etmek sessiz ölüm üretiyor."""
    kurulum = (BETIKLER / "zamanlama-kur.sh").read_text(encoding="utf-8")
    kur_blogu = kurulum.split('case "$komut" in')[1].split("tazele)")[0]
    assert 'echo "❌ .env yok' in kur_blogu
    assert "exit 1" in kur_blogu


def test_kurulum_worktree_kuruyor_ve_tazeleme_sunuyor():
    """ADR-0008'in özü: kod ayrı worktree'de ve ref bilinçli seçiliyor."""
    kurulum = (BETIKLER / "zamanlama-kur.sh").read_text(encoding="utf-8")
    assert "worktree add --detach" in kurulum
    assert "tazele)" in kurulum
    # `durum` sağlıksızsa sıfırdan farklı dönmeli; betikten kontrol edilebilsin.
    assert 'exit "$saglikli"' in kurulum
