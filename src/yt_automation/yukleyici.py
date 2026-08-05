"""Resumable YouTube yükleme hattı ve yükleme sonrası bayrak doğrulaması."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from googleapiclient.http import MediaFileUpload

from .kanal import Kanal
from .kota import KaliciSayac, Sayac
from .video import Video, yayin_tarihini_utc

YUKLEME_TEKRAR_SAYISI = 3


class YuklemeDogrulamaHatasi(RuntimeError):
    """Yüklenen videonun durumu gönderilen beyanlarla eşleşmiyor."""


class YanlisKanalHatasi(RuntimeError):
    """Token beklenen kanaldan başka bir kanala bağlı."""


def kanali_dogrula(
    servis: Any,
    kanal: Kanal,
    sayac: Sayac | KaliciSayac,
    *,
    uyar: Callable[[str], None] | None = None,
) -> str | None:
    """Token'ın gerçekten beklenen kanala bağlı olduğunu doğrular.

    **Yüklemeden önce çağrılmalı.** `videos.insert` videoyu token'ın kanalına
    yüklüyor ve o kanalın hangisi olduğunu hiçbir yerde sormuyorduk.

    Ölçüldü (2026-08-05): ilk yetkilendirmede token beklenen kanal yerine
    kişisel bir kanala bağlandı — kullanıcı kendi Google hesabıyla giriş yaptı,
    Google da onun kanalını seçti. Yükleme yapılsaydı video yanlış kanala
    giderdi; geri alması YouTube tarafında elle iş.

    Maliyet 1 birim (`channels.list`). Video başına 1.651 birim harcayan bir
    hatta bu ölçülemeyecek kadar küçük ve yanlış kanala yüklemenin bedeli
    kotayla ölçülmüyor.

    Profilde `youtube_kanal_id` yoksa doğrulama **atlanır ama uyarılır** —
    sessiz atlama, korumanın hiç olmamasıyla aynı şey olurdu.
    """
    if kanal.youtube_kanal_id is None:
        if uyar is not None:
            uyar(
                f"{kanal.kimlik}: profilde `youtube_kanal_id` yok, hangi kanala "
                "yüklendiği doğrulanamıyor. `channels.list?mine=true` ile ölçüp "
                "profile ekleyin."
            )
        return None

    sayac.harca("channels.list")
    yanit = servis.channels().list(part="snippet", mine=True).execute()
    ogeler = yanit.get("items", [])
    if not ogeler:
        raise YanlisKanalHatasi(
            "Yetkilendirilmiş hesaba bağlı kanal bulunamadı. Token doğru hesapla mı alındı?"
        )

    gercek = ogeler[0].get("id", "")
    if gercek != kanal.youtube_kanal_id:
        ad = ogeler[0].get("snippet", {}).get("title", "?")
        raise YanlisKanalHatasi(
            f"Token yanlış kanala bağlı: {ad!r} ({gercek}). "
            f"Beklenen: {kanal.ad!r} ({kanal.youtube_kanal_id}). "
            "Hiçbir şey yüklenmedi. Token'ı silip doğru hesapla yeniden "
            "yetkilendirin."
        )
    return gercek


def _rfc3339_utc(video: Video) -> str | None:
    if video.yayin_tarihi is None:
        return None
    return yayin_tarihini_utc(video.yayin_tarihi).isoformat().replace("+00:00", "Z")


def yukleme_govdesi(video: Video, kanal: Kanal) -> dict[str, Any]:
    """``videos.insert`` için snippet ve status nesnesini üretir."""
    if video.cocuk_icerigi != kanal.cocuk_icerigi:
        raise ValueError("video çocuk içeriği bayrağı kanal profiliyle çelişiyor")

    yayin = _rfc3339_utc(video)
    # ⚠️ Gizlilik HER ZAMAN `private`. Yayın tarihi varsa `publishAt` ile
    # zamanlanır; yoksa video yüklenir ama yayına çıkmaz.
    #
    # Önceki hâli tersiydi (tarih yoksa `public`) ve PRD'nin *v1'de
    # OLMAYACAKLAR* listesindeki "otomatik yayın kararı" maddesiyle doğrudan
    # çelişiyordu — üstelik VARSAYILAN yol olarak, yani metadata'da bir satırı
    # unutmanın cezası "yayında" oluyordu.
    #
    # Yanlış yöne düşmenin bedeli asimetrik: erken yayınlanan videoyu geri
    # almak izlenme, öneri sinyali ve çocuk içeriğinde uyum riski demek; geç
    # yayınlanan videoyu yayınlamak bir tık. Yayınlama insanın açık eylemi.
    status: dict[str, Any] = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": kanal.cocuk_icerigi,
        "containsSyntheticMedia": video.sentetik_medya,
    }
    if yayin:
        status["publishAt"] = yayin

    return {
        "snippet": {
            "title": video.baslik,
            "description": video.aciklama,
            "tags": list(video.etiketler),
            "defaultLanguage": kanal.varsayilan_dil,
        },
        "status": status,
    }


def _bayraklari_dogrula(beklenen: dict[str, Any], gercek: dict[str, Any]) -> list[str]:
    """Beyanları YouTube'un döndürdüğüyle karşılaştırır.

    **Üç durum var, ikisi karıştırılmamalı:**

    - alan döndü ve eşleşiyor → doğrulandı
    - alan döndü ama farklı → beyan tutmadı, **hata**
    - alan hiç dönmedi → doğrulanamadı; hata DEĞİL, döndürülüp raporlanır

    Üçüncüsü ayrılmazsa `gercek.get(alan)` `None` verir, beklenen `True` ile
    eşleşmez ve **her başarılı yüklemeden sonra** hata atılır: video YouTube'da,
    1.651 birim harcanmış, çağıran taraf yüklemenin başarısız olduğunu sanıyor
    ve muhtemelen tekrar deniyor — bedel iki katına çıkıyor.

    Ölçüldü (2026-08-05, `videos.list?part=status`, anahtarla okuma):
    `containsSyntheticMedia`, `selfDeclaredMadeForKids` ve `publishAt` yanıtta
    **yok**; yalnızca `privacyStatus` ve `madeForKids` dönüyor. Bu okuma
    sahibi olmayan bir okumaydı — belgelere göre `selfDeclaredMadeForKids`
    yalnızca sahibine dönüyor, dolayısıyla OAuth'lu okumada bazıları gelebilir.
    Kesin cevabı ilk gerçek yükleme verecek; kod o zamana kadar iki yönde de
    doğru davranıyor: gelen alan denetleniyor, gelmeyen alan sessizce
    "başarısız" sayılmıyor.

    Yön asimetriktir: dönmeyen alanı hata saymak pahalı ve yanlış; gerçekten
    tutmayan bir beyanı kaçırmak ise ancak alan hiç dönmediğinde mümkün — o da
    zaten doğrulanamaz durum.
    """
    dogrulanamayan: list[str] = []
    for alan in (
        "privacyStatus",
        "publishAt",
        "selfDeclaredMadeForKids",
        "containsSyntheticMedia",
    ):
        if alan not in beklenen:
            continue
        if alan not in gercek:
            dogrulanamayan.append(alan)
            continue
        if gercek[alan] != beklenen[alan]:
            raise YuklemeDogrulamaHatasi(
                f"{alan}: beklenen {beklenen[alan]!r}, YouTube {gercek[alan]!r} döndürdü"
            )
    return dogrulanamayan


def yukle_ve_dogrula(
    video: Video,
    kanal: Kanal,
    servis: Any,
    # Union bilerek: üretimde `KaliciSayac` (süreçler arası defter, DW-24),
    # testlerde `Sayac` (bellekte). İkisi de `harca()` sunuyor ve bu modül
    # yalnızca onu kullanıyor.
    sayac: Sayac | KaliciSayac,
    *,
    medya_fabrikasi: Callable[..., Any] = MediaFileUpload,
    # Doğrulanamayan bayrakları bildiren geri çağırım. Sessiz atlamak bu
    # repoda kabul edilen bir şey değil: "doğrulandı" ile "doğrulanamadı"
    # operatöre görünmeli, yoksa beyanların gerçekten yazıldığı sanılır.
    uyar: Callable[[str], None] | None = None,
) -> str:
    """Videoyu resumable yükler, thumbnail'i gönderir ve beyanları doğrular.

    Kota her API isteğinden önce düşülür. ``next_chunk`` aynı resumable
    oturumu üzerinde tekrarlandığı için kesinti sonrası yükleme baştan başlamaz.
    """
    govde = yukleme_govdesi(video, kanal)
    sayac.harca("videos.insert")
    medya = medya_fabrikasi(str(video.dosya), resumable=True)
    istek = servis.videos().insert(
        part="snippet,status",
        body=govde,
        media_body=medya,
        notifySubscribers=False,
    )

    yanit = None
    while yanit is None:
        _, yanit = istek.next_chunk(num_retries=YUKLEME_TEKRAR_SAYISI)
    video_id = str(yanit.get("id", ""))
    if not video_id:
        raise YuklemeDogrulamaHatasi("videos.insert yanıtında video kimliği yok")

    if video.thumbnail is not None:
        sayac.harca("thumbnails.set")
        thumbnail = medya_fabrikasi(str(video.thumbnail), resumable=False)
        servis.thumbnails().set(videoId=video_id, media_body=thumbnail).execute()

    sayac.harca("videos.list")
    dogrulama = servis.videos().list(part="status", id=video_id).execute()
    ogeler = dogrulama.get("items", [])
    if not ogeler:
        raise YuklemeDogrulamaHatasi(f"yüklenen video doğrulamada bulunamadı: {video_id}")
    dogrulanamayan = _bayraklari_dogrula(govde["status"], ogeler[0].get("status", {}))
    if dogrulanamayan and uyar is not None:
        uyar(
            f"{video_id}: YouTube şu alanları geri döndürmedi, beyan "
            f"doğrulanamadı — {', '.join(dogrulanamayan)}. Beyan gönderildi; "
            "yalnızca geri okunamıyor."
        )
    return video_id
