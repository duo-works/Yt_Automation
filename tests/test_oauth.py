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
