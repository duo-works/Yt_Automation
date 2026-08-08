"""Üretilen videoları Google Drive'a yükler — inceleme yüzeyi.

Neden gerekiyor: video hattı `private` yüklüyor ve YouTube Studio'dan bakmak
telefonda zahmetli. Daha kötüsü, kanal kapanırsa (2026-08-06'da oldu)
çıktılar erişilemez hâle geliyor — 6 videonun tamamı yalnızca yerel diskte
kaldı. Drive, YouTube'dan bağımsız ikinci bir kopya ve paylaşılabilir tek bir
bağlantı demek.

⚠️ **Kapsam bilinçli olarak `drive.file`.** Bu kapsam yalnızca bu uygulamanın
**kendi oluşturduğu** dosyalara erişim veriyor; kullanıcının Drive'ının geri
kalanını göremiyor. `drive` (tam erişim) istemek gereksiz ve geri alınması zor
bir yetki olurdu.

⚠️ **Token dosyası YouTube'unkinden AYRI.** Ölçüldü (2026-08-06): iki hattın
aynı token dosyasını paylaşması, dar kapsamlı olanın geniş kapsamlıyı üzerine
yazmasına yol açtı ve kanal doğrulaması sessizce bozuldu. Ayrı dosya, ayrı
ömür.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

KAPSAMLAR = ["https://www.googleapis.com/auth/drive.file"]
"""Yalnızca bu uygulamanın oluşturduğu dosyalar — bkz. modül başlığı."""

VARSAYILAN_TOKEN = Path.home() / ".yt-otomasyon" / "drive-token.json"
KLASOR_TURU = "application/vnd.google-apps.folder"


class DriveHatasi(RuntimeError):
    """Drive tarafı anlaşılır bir sebeple çalışmadı."""


@dataclass(frozen=True)
class Yukleme:
    ad: str
    dosya_kimligi: str
    baglanti: str


def _token_yaz(kimlik, yol: Path) -> None:
    """Token'ı yalnızca sahibinin okuyabileceği izinle yazar.

    İçinde yenileme jetonu var; düz `write_text` dosyayı umask'a bırakıyor ve
    pratikte 0644 çıkıyor (DW-84'te ölçüldü).
    """
    yol.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    yol.write_text(kimlik.to_json(), encoding="utf-8")
    os.chmod(yol, 0o600)


def kimlik_al(*, client_secret: Path, token_yolu: Path = VARSAYILAN_TOKEN):
    """Drive kimliğini getirir; gerekirse tarayıcıda onay akışını başlatır."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    kimlik = None
    if token_yolu.exists():
        kimlik = Credentials.from_authorized_user_file(str(token_yolu), KAPSAMLAR)
        # `valid` kapsamı DENETLEMİYOR; dar kapsamlı bir token "geçerli"
        # görünüp ilk çağrıda 403 veriyor (DW-84).
        if kimlik and not kimlik.has_scopes(KAPSAMLAR):
            kimlik = None
        elif kimlik and kimlik.expired and kimlik.refresh_token:
            try:
                kimlik.refresh(Request())
            except RefreshError:
                # Onay ekranı "Testing" modundayken yenileme jetonu 7 günde
                # ölüyor. Bayat token'ı silip baştan onay almak, anlaşılmaz
                # bir hatayla durmaktan iyi.
                token_yolu.unlink(missing_ok=True)
                kimlik = None

    if kimlik and kimlik.valid:
        return kimlik

    if not client_secret.exists():
        raise DriveHatasi(
            f"client_secret.json bulunamadı: {client_secret}\n"
            "Google Cloud Console → APIs & Services → Credentials → OAuth "
            "client ID (Desktop app) ile indirin."
        )
    akis = InstalledAppFlow.from_client_secrets_file(str(client_secret), KAPSAMLAR)
    kimlik = akis.run_local_server(port=0)
    _token_yaz(kimlik, token_yolu)
    return kimlik


def _servis(kimlik):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=kimlik, cache_discovery=False)


def klasor_bul_ya_da_ac(servis, ad: str) -> str:
    """Aynı adlı klasör varsa onu kullanır — her koşumda yenisi açılmasın.

    Sorgu `trashed=false` içeriyor: çöpteki bir klasör bulunursa dosyalar
    görünmez bir yere yüklenir ve bağlantı boş görünür.
    """
    kacis = ad.replace("'", "\\'")
    sorgu = f"name = '{kacis}' and mimeType = '{KLASOR_TURU}' and trashed = false"
    yanit = servis.files().list(q=sorgu, fields="files(id,name)", pageSize=1).execute()
    mevcut = yanit.get("files") or []
    if mevcut:
        return mevcut[0]["id"]

    olusan = (
        servis.files().create(body={"name": ad, "mimeType": KLASOR_TURU}, fields="id").execute()
    )
    return olusan["id"]


def baglanti_ac(servis, klasor_kimligi: str) -> str:
    """Klasörü 'bağlantısı olan görebilir' yapar ve bağlantıyı döndürür.

    ⚠️ Bu bir **paylaşım** eylemi: bağlantıyı bilen herkes içeriği görebilir.
    Videolar YouTube'da zaten `private`; Drive'daki kopya inceleme içindir ve
    bağlantı paylaşılmadıkça kimse ulaşamaz. Yine de yazma yetkisi
    verilmiyor — yalnızca `reader`.
    """
    from googleapiclient.errors import HttpError

    try:
        servis.permissions().create(
            fileId=klasor_kimligi,
            body={"role": "reader", "type": "anyone"},
            fields="id",
        ).execute()
    except HttpError as hata:
        # ⚠️ Ölçüldü (2026-08-08): klasörde bizim uygulamamızın oluşturmadığı
        # bir dosya varsa `drive.file` kapsamı bu çağrıyı 403
        # `appNotAuthorizedToChild` ile reddediyor — klasörün izni çocuğu da
        # etkileyeceği için.
        #
        # Bu hata YÜKLEMEDEN SONRA geliyordu ve bütün koşumu düşürüyordu:
        # video Drive'a çıkmış olmasına rağmen çağıran taraf hata görüyor ve
        # bağlantıyı alamıyordu. Paylaşım bir YAN İŞ; klasör zaten paylaşılmış
        # olabilir ve bağlantı her hâlükârda geçerli.
        if hata.resp.status != 403:
            raise
    return f"https://drive.google.com/drive/folders/{klasor_kimligi}"


def videolari_yukle(
    dosyalar: list[Path],
    *,
    klasor_adi: str,
    client_secret: Path,
    token_yolu: Path = VARSAYILAN_TOKEN,
    paylas: bool = True,
) -> tuple[str, list[Yukleme]]:
    """Videoları klasöre yükler; (klasör bağlantısı, yüklenenler) döndürür.

    Aynı adlı dosya klasörde varsa **atlanır**: betik her gece koşacak ve
    aynı stoğun tekrar tekrar yüklenmesi hem kotayı hem depolamayı yiyor.
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    eksik = [d for d in dosyalar if not d.exists()]
    if eksik:
        raise DriveHatasi(f"dosya bulunamadı: {', '.join(str(d) for d in eksik)}")

    kimlik = kimlik_al(client_secret=client_secret, token_yolu=token_yolu)
    servis = _servis(kimlik)

    try:
        klasor = klasor_bul_ya_da_ac(servis, klasor_adi)
    except HttpError as hata:
        if hata.resp.status == 403 and "accessNotConfigured" in str(hata):
            raise DriveHatasi(
                "Google Drive API bu projede açık değil. Google Cloud Console → "
                "APIs & Services → Library → 'Google Drive API' → Enable."
            ) from hata
        raise

    mevcut_adlar = {
        d["name"]
        for d in servis.files()
        .list(
            q=f"'{klasor}' in parents and trashed = false",
            fields="files(name)",
            pageSize=1000,
        )
        .execute()
        .get("files", [])
    }

    yuklenenler: list[Yukleme] = []
    for dosya in dosyalar:
        if dosya.name in mevcut_adlar:
            continue
        medya = MediaFileUpload(str(dosya), mimetype="video/mp4", resumable=True)
        sonuc = (
            servis.files()
            .create(
                body={"name": dosya.name, "parents": [klasor]},
                media_body=medya,
                fields="id,name,webViewLink",
            )
            .execute()
        )
        yuklenenler.append(
            Yukleme(
                ad=sonuc["name"],
                dosya_kimligi=sonuc["id"],
                baglanti=sonuc.get("webViewLink", ""),
            )
        )

    baglanti = (
        baglanti_ac(servis, klasor)
        if paylas
        else f"https://drive.google.com/drive/folders/{klasor}"
    )
    return baglanti, yuklenenler
