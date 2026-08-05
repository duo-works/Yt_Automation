from unittest.mock import MagicMock, patch

import pytest

from yt_automation import oauth


def test_yol_ortam_degiskeni_yoksa_hata(monkeypatch):
    monkeypatch.delenv("YT_TOKEN_PATH", raising=False)
    with pytest.raises(oauth.OAuthYapilandirmaHatasi, match="YT_TOKEN_PATH"):
        oauth._yol("YT_TOKEN_PATH")


def test_yol_kullanici_dizinini_genisletir(monkeypatch):
    monkeypatch.setenv("YT_TOKEN_PATH", "~/gizli/token.json")
    yol = oauth._yol("YT_TOKEN_PATH")
    assert not str(yol).startswith("~")


def test_gecerli_token_varsa_yeniden_yetkilendirme_yapilmaz(tmp_path):
    token_yolu = tmp_path / "token.json"
    token_yolu.write_text("{}", encoding="utf-8")

    sahte_kimlik = MagicMock(valid=True)
    with patch.object(oauth.Credentials, "from_authorized_user_file", return_value=sahte_kimlik):
        sonuc = oauth._yenile_veya_yetkilendir(tmp_path / "secret.json", token_yolu)

    assert sonuc is sahte_kimlik


def test_suresi_dolmus_token_sessizce_yenilenir(tmp_path):
    token_yolu = tmp_path / "token.json"
    token_yolu.write_text("{}", encoding="utf-8")

    sahte_kimlik = MagicMock(valid=False, expired=True, refresh_token="abc")
    sahte_kimlik.to_json.return_value = '{"refreshed": true}'
    with patch.object(oauth.Credentials, "from_authorized_user_file", return_value=sahte_kimlik):
        sonuc = oauth._yenile_veya_yetkilendir(tmp_path / "secret.json", token_yolu)

    sahte_kimlik.refresh.assert_called_once()
    assert sonuc is sahte_kimlik
    assert token_yolu.read_text(encoding="utf-8") == '{"refreshed": true}'


def test_token_yok_client_secret_de_yoksa_anlasilir_hata(tmp_path):
    with pytest.raises(oauth.OAuthYapilandirmaHatasi, match="client secret"):
        oauth._yenile_veya_yetkilendir(tmp_path / "yok.json", tmp_path / "token.json")


def test_ilk_yetkilendirme_akisi_token_dosyasini_yazar(tmp_path):
    client_secret_yolu = tmp_path / "secret.json"
    client_secret_yolu.write_text("{}", encoding="utf-8")
    token_yolu = tmp_path / "alt_dizin" / "token.json"

    sahte_kimlik = MagicMock()
    sahte_kimlik.to_json.return_value = '{"token": "yeni"}'
    sahte_akis = MagicMock()
    sahte_akis.run_local_server.return_value = sahte_kimlik

    with patch.object(
        oauth.InstalledAppFlow, "from_client_secrets_file", return_value=sahte_akis
    ) as sahte_from_secrets:
        sonuc = oauth._yenile_veya_yetkilendir(client_secret_yolu, token_yolu)

    sahte_from_secrets.assert_called_once_with(str(client_secret_yolu), oauth.KAPSAMLAR)
    sahte_akis.run_local_server.assert_called_once_with(port=0)
    assert sonuc is sahte_kimlik
    assert token_yolu.read_text(encoding="utf-8") == '{"token": "yeni"}'


def test_servis_olustur_uc_parcayi_birlestirir(monkeypatch, tmp_path):
    client_secret_yolu = tmp_path / "secret.json"
    token_yolu = tmp_path / "token.json"
    monkeypatch.setenv("YT_CLIENT_SECRET_PATH", str(client_secret_yolu))
    monkeypatch.setenv("YT_TOKEN_PATH", str(token_yolu))

    sahte_kimlik = MagicMock()
    sahte_servis = MagicMock()

    with (
        patch.object(oauth, "_yenile_veya_yetkilendir", return_value=sahte_kimlik) as sahte_yenile,
        patch.object(oauth, "build", return_value=sahte_servis) as sahte_build,
    ):
        sonuc = oauth.servis_olustur()

    sahte_yenile.assert_called_once_with(client_secret_yolu, token_yolu)
    sahte_build.assert_called_once_with(oauth.API_ADI, oauth.API_SURUMU, credentials=sahte_kimlik)
    assert sonuc is sahte_servis


def test_token_dosyasi_yalnizca_sahibine_okunur(tmp_path):
    """İçinde refresh token var — 0644 bırakmak ssh anahtarını açıkta bırakmak gibi.

    Ölçüldü (review, 2026-08-05): düz `write_text` umask'e tabi ve bu makinede
    0644 üretiyordu, yani makinedeki her kullanıcı kanala yükleme yetkisi veren
    kimlik bilgisini okuyabiliyordu.
    """
    token_yolu = tmp_path / "yeni" / "token.json"
    sahte_kimlik = MagicMock()
    sahte_kimlik.to_json.return_value = "{}"

    oauth._kaydet(sahte_kimlik, token_yolu)

    assert token_yolu.stat().st_mode & 0o777 == 0o600
    assert token_yolu.parent.stat().st_mode & 0o777 == 0o700


def test_yenileme_basarisizsa_tarayici_akisina_dusulur(tmp_path):
    """`RefreshError` yakalanmazsa hat, en sık karşılaşılan hâlde çöker.

    Onay ekranı "Testing" durumundayken refresh token 7 günde doluyor — yani
    bu yol haftada bir kez geçiliyor. Yakalanmazsa kütüphane traceback'i ile
    patlar ve modülün "sessiz yenileme" iddiası tam da orada tutmaz.
    """
    token_yolu = tmp_path / "token.json"
    token_yolu.write_text("{}", encoding="utf-8")
    client_secret_yolu = tmp_path / "secret.json"
    client_secret_yolu.write_text("{}", encoding="utf-8")

    bayat = MagicMock(valid=False, expired=True, refresh_token="abc")
    bayat.refresh.side_effect = oauth.RefreshError("token iptal edilmiş")

    yeni_kimlik = MagicMock()
    yeni_kimlik.to_json.return_value = '{"yeni": true}'
    sahte_akis = MagicMock()
    sahte_akis.run_local_server.return_value = yeni_kimlik

    with (
        patch.object(oauth.Credentials, "from_authorized_user_file", return_value=bayat),
        patch.object(oauth.InstalledAppFlow, "from_client_secrets_file", return_value=sahte_akis),
    ):
        sonuc = oauth._yenile_veya_yetkilendir(client_secret_yolu, token_yolu)

    sahte_akis.run_local_server.assert_called_once()
    assert sonuc is yeni_kimlik
    assert token_yolu.read_text(encoding="utf-8") == '{"yeni": true}'


def test_kapsam_eksikse_eski_token_kullanilmaz(tmp_path):
    """`Credentials.valid` kapsam kontrol etmiyor — `has_scopes` ayrı metot.

    Bu ayrım olmadan KAPSAMLAR'a bir kapsam eklendiğinde diskteki eski token
    geçerli görünmeye devam eder ve hata `403 insufficient scopes` olarak
    çağrı yerinde patlar. DW-25 (Analytics) tam olarak ayrı bir kapsam istiyor.
    """
    token_yolu = tmp_path / "token.json"
    token_yolu.write_text("{}", encoding="utf-8")
    client_secret_yolu = tmp_path / "secret.json"
    client_secret_yolu.write_text("{}", encoding="utf-8")

    dar_kapsamli = MagicMock(valid=True, expired=False)
    dar_kapsamli.has_scopes.return_value = False

    yeni_kimlik = MagicMock()
    yeni_kimlik.to_json.return_value = "{}"
    sahte_akis = MagicMock()
    sahte_akis.run_local_server.return_value = yeni_kimlik

    with (
        patch.object(oauth.Credentials, "from_authorized_user_file", return_value=dar_kapsamli),
        patch.object(oauth.InstalledAppFlow, "from_client_secrets_file", return_value=sahte_akis),
    ):
        sonuc = oauth._yenile_veya_yetkilendir(client_secret_yolu, token_yolu)

    dar_kapsamli.has_scopes.assert_called_once_with(oauth.KAPSAMLAR)
    sahte_akis.run_local_server.assert_called_once()
    assert sonuc is yeni_kimlik
