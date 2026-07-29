from pathlib import Path

from yt_automation import cli


def test_yukle_komutu_dizin_ve_kanali_aktarir(monkeypatch, tmp_path: Path):
    cagrilar = []

    def sahte_yukle(dizin: Path, kanal: str) -> int:
        cagrilar.append((dizin, kanal))
        return 0

    monkeypatch.setattr(cli, "_yukle", sahte_yukle)

    sonuc = cli.main(["yukle", str(tmp_path), "--kanal", "cocuk"])

    assert sonuc == 0
    assert cagrilar == [(tmp_path, "cocuk")]
