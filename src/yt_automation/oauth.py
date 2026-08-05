"""OAuth ve token yönetimi — YouTube Data API v3.

PRD kararı: tek kanal, tek proje, çoklu kullanıcı yok — bu yüzden OAuth
tek seferlik ve kalıcı olmalı. Google'ın resmi belgesine göre onay ekranı
"Testing" durumundayken verilen refresh token'lar 7 günde doluyor; günlük
bir otomasyon için bu, her hafta elle yeniden yetkilendirmek demek. Uygulama
Google Cloud Console'da **In Production**'a alınmalı — bu kodun dışında,
bir kerelik manuel adım (bkz. PRD → Diğer).

Sırlar asla repo'ya veya Notion'a yazılmaz (CONTRIBUTING.md §8). Client
secret ve token dosyalarının yolu ortam değişkeninden okunur; gerçek
dosyalar parola yöneticisinden indirilir ve .gitignore'dadır.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

# videos.insert / videos.update / thumbnails.set için gerekli.
KAPSAM_YUKLEME = "https://www.googleapis.com/auth/youtube.upload"
# DW-22'nin 5. başarı ölçütü: yükleme sonrası videos.list ile beyan
# bayraklarının (containsSyntheticMedia, selfDeclaredMadeForKids) gerçekten
# yazıldığını doğrulamak. Yükleme kapsamı bunu garanti etmiyor.
KAPSAM_OKUMA = "https://www.googleapis.com/auth/youtube.readonly"
KAPSAMLAR = [KAPSAM_YUKLEME, KAPSAM_OKUMA]

API_ADI = "youtube"
API_SURUMU = "v3"


class OAuthYapilandirmaHatasi(RuntimeError):
    """Gerekli ortam değişkeni tanımlı değil ya da işaret ettiği dosya yok."""


def _yol(ortam_degiskeni: str) -> Path:
    ham = os.environ.get(ortam_degiskeni)
    if not ham:
        raise OAuthYapilandirmaHatasi(
            f"{ortam_degiskeni} tanımlı değil. .env dosyanızda ayarlayın "
            "(gerçek değer parola yöneticisinde — bkz. .env.example)."
        )
    return Path(ham).expanduser()


def _kaydet(kimlik_bilgisi: Credentials, token_yolu: Path) -> None:
    """Token'ı **yalnızca sahibinin okuyabileceği** izinle yazar.

    İçinde refresh token var: uzun ömürlü ve kanala yükleme yetkisi veren bir
    kimlik bilgisi. Düz `write_text` dosyayı umask'e bırakıyordu ve ölçüldü —
    bu makinede 0644 çıkıyor, yani makinedeki her kullanıcı okuyabiliyor.
    `ssh` özel anahtarını 0644 bırakmakla aynı sınıf hata. Modül docstring'i
    sırların repoya yazılmamasını söylüyor; aynı özen dosya iznine de gerekli.

    ⚠️ `mkdir(mode=...)` yalnızca dizin **yeni oluşturulurken** etkili; var
    olan bir dizinin iznini değiştirmiyor. Yeni kurulumlarda doğru olanı
    yapıyor, eskiden kalan gevşek dizin izni elle düzeltilmeli.
    """
    token_yolu.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    token_yolu.write_text(kimlik_bilgisi.to_json(), encoding="utf-8")
    token_yolu.chmod(0o600)


def _yenile_veya_yetkilendir(client_secret_yolu: Path, token_yolu: Path) -> Credentials:
    """Kayıtlı bir token varsa onu kullanır/yeniler; yoksa tarayıcı akışını başlatır."""
    kimlik_bilgisi: Credentials | None = None

    if token_yolu.is_file():
        kimlik_bilgisi = Credentials.from_authorized_user_file(str(token_yolu), KAPSAMLAR)

    # ⚠️ `Credentials.valid` KAPSAM KONTROL ETMİYOR — kaynağı yalnızca
    # `token is not None and not expired` diyor. `has_scopes` ayrı bir metot.
    # Bu ayrım olmadan `KAPSAMLAR`'a ileride bir kapsam eklendiğinde diskteki
    # eski token geçerli görünmeye devam eder ve hata çalışma anında
    # `403 insufficient scopes` olarak, çağrı yerinde patlar — sebebi
    # anlaşılmayan bir yerde. Varsayımsal değil: DW-25 (Analytics) ayrı bir
    # kapsam gerektiriyor ve PRD bunu zaten yazıyor.
    if kimlik_bilgisi and kimlik_bilgisi.valid and kimlik_bilgisi.has_scopes(KAPSAMLAR):
        return kimlik_bilgisi

    if kimlik_bilgisi and kimlik_bilgisi.expired and kimlik_bilgisi.refresh_token:
        try:
            kimlik_bilgisi.refresh(Request())
        except RefreshError:
            # İptal edilmiş ya da 7 günde dolmuş refresh token. Bu, modül
            # docstring'inde uyarı olarak yazılı olan senaryonun ta kendisi:
            # onay ekranı "Testing"teyken HER HAFTA buraya düşülür. Yakalanmazsa
            # kütüphane traceback'i ile patlar ve "sessiz yenileme" iddiası
            # tam da en sık karşılaşılan hâlde tutmaz.
            #
            # Bayat dosya siliniyor: bırakılırsa her koşumda önce okunup sonra
            # aynı hataya düşülür ve dosyanın varlığı yanıltıcı kalır.
            kimlik_bilgisi = None
            token_yolu.unlink(missing_ok=True)
        else:
            _kaydet(kimlik_bilgisi, token_yolu)
            return kimlik_bilgisi

    if not client_secret_yolu.is_file():
        raise OAuthYapilandirmaHatasi(
            f"client secret dosyası yok: {client_secret_yolu}. "
            "Google Cloud Console → Credentials'tan indirip yolu "
            "YT_CLIENT_SECRET_PATH'e yazın."
        )

    # İlk yetkilendirme: tarayıcı açılır, kullanıcı bir kez izin verir.
    # Uygulama Testing'te kalırsa refresh token 7 günde dolar (yukarıdaki
    # modül notu) — kod bunu doğrulayamaz, Cloud Console'da tek seferlik
    # manuel adım.
    akis = InstalledAppFlow.from_client_secrets_file(str(client_secret_yolu), KAPSAMLAR)
    kimlik_bilgisi = akis.run_local_server(port=0)
    _kaydet(kimlik_bilgisi, token_yolu)
    return kimlik_bilgisi


def servis_olustur() -> Resource:
    """Yetkilendirilmiş bir YouTube Data API istemcisi döndürür.

    Token dosyası varsa ve geçerliyse doğrudan kullanılır. Süresi dolmuş
    ama yenilenebilirse sessizce yenilenir. Hiç yoksa tarayıcı tabanlı
    tek seferlik yetkilendirme akışı başlar ve sonucu diske yazar.
    """
    client_secret_yolu = _yol("YT_CLIENT_SECRET_PATH")
    token_yolu = _yol("YT_TOKEN_PATH")
    kimlik_bilgisi = _yenile_veya_yetkilendir(client_secret_yolu, token_yolu)
    return build(API_ADI, API_SURUMU, credentials=kimlik_bilgisi)
