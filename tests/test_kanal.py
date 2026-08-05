"""Kanal profilleri — yükleme hattının beyanları buradan besleniyor.

Bu dosya DW-81'de açıldı: `kanal.py`'nin hiç testi yoktu ve içindeki tek alan
(`cocuk_icerigi`) doğrudan `selfDeclaredMadeForKids` olarak YouTube'a gidiyor.
Modülün kendi uyarısına göre yanlış işaretlemenin bedeli ihlal başına $53.088.
Test edilmeyen bir yapılandırma değeri için fazla pahalı bir sessizlik.
"""

import pytest

from yt_automation import kanal


def test_kayitli_hicbir_kanal_cocuk_icerigi_degil():
    """Çocuk içeriği ürün kararı olarak bırakıldı (2026-08-05).

    Bu testin asıl işi ileriye dönük: biri `KANALLAR`'a `cocuk_icerigi=True`
    bir profil eklerse bunun bilinçli bir karar olması gerekir, kopyala-yapıştır
    kazası değil. FTC beyanı geri alınabilir bir şey değil.
    """
    cocuk_olanlar = [k for k in kanal.KANALLAR.values() if k.cocuk_icerigi]
    assert cocuk_olanlar == [], (
        f"çocuk içeriği işaretli profil var: {[k.kimlik for k in cocuk_olanlar]}"
    )


@pytest.mark.parametrize("komut", ["dogrula", "yukle"])
def test_cli_varsayilanlari_kayitli_bir_kanali_gosteriyor(komut: str, capsys):
    """`--kanal` varsayılanı silinmiş bir profili gösterirse yükleme çöker.

    Kusur bu yönde ölçüldü: `cocuk` profili CLI'da iki komutun varsayılanıydı.
    Profil silinip varsayılan güncellenmeseydi argümansız her `ytoto yukle`
    "bilinmeyen kanal" ile düşerdi; profil silinmeseydi de argümansız yükleme
    çocuk içeriği beyanıyla giderdi. İki uç da kötü, ikisini de bu test tutar.

    Varsayılan `--help` çıktısından okunuyor: ayrıştırıcı `main()` içinde
    kuruluyor ve dışarıdan erişilemiyor, ama kullanıcının gördüğü metin
    zaten sözleşmenin kendisi.
    """
    from yt_automation import cli

    with pytest.raises(SystemExit) as cikis:
        cli.main([komut, "--help"])
    assert cikis.value.code == 0

    yardim = capsys.readouterr().out
    kayitli = [k for k in kanal.KANALLAR if f"varsayılan: {k}" in yardim]
    assert kayitli, (
        f"`{komut} --kanal` varsayılanı kayıtlı bir kanalı göstermiyor. "
        f"Tanımlı kanallar: {sorted(kanal.KANALLAR)}"
    )


def test_bilinmeyen_kanal_tanimlilari_soyluyor():
    """Hata mesajı ne yapılacağını söylemeli — çıplak KeyError değil."""
    with pytest.raises(KeyError, match="tanımlı olanlar"):
        kanal.getir("olmayan-kanal")


def test_muezza_ingilizce_yayin_yapiyor():
    """`varsayilan_dil` doğrudan `snippet.defaultLanguage`'a gidiyor.

    muezza İngilizce Shorts kanalı (MoneyPrinterTurbo `CHANNEL_ANALYSIS.md`:
    35-50 saniye, 80-120 İngilizce kelime). Dataclass varsayılanı `tr` olduğu
    için profil bunu açıkça geçmezse her videoya yanlış dil etiketi giderdi.
    """
    assert kanal.getir("muezza").varsayilan_dil == "en"
