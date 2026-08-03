"""Niş kanal izleme — bir videonun **kendi kanalına göre** aşırı performansı.

50–150 tarih/bilim kanalının yükleme listesi izleniyor. Ölçü mutlak izlenme
değil, videonun kendi kanalının tabanına göre kaç katı olduğu.

Bu, kanal büyüklüğü etkisini temizliyor: 5 milyonluk kanalın 2 milyon izlenen
videosu sıradan, 50 binlik kanalın 400 bin izlenen videosu **sinyal**.

## Neden değerli

- **Tanım gereği nişe filtreli** — sınıflandırıcıya gerek yok, kanalları
  zaten biz seçiyoruz.
- Ucuz: kanal başına 2 birim (`playlistItems.list` + `videos.list`).
- Yalnızca konu değil **format** öğretiyor: hangi süre, hangi başlık kalıbı.

## ⚠️ Bu sinyal takipçi yapar, lider değil

Yapılmış olanı gösteriyor. Talep-arz skoruyla (DW-35) birlikte kullanılmalı,
tek başına değil: burada zirveye çıkan konu, tanımı gereği arzı **var** olan
konudur.

## Kanal listesi handle ile tutuluyor, UC kimliğiyle değil

`IZLENEN_KANALLAR` insan tarafından küre edilecek bir config. Handle (`@ad`)
tutuluyor çünkü:

- İnsan okuyabiliyor ve doğrulayabiliyor; `UCsXVk37bltHxD1rDPwtNM8Q` okunmaz.
- Liste büyüdüğünde neyin izlendiği listeye bakılarak anlaşılıyor.
- `channels.list?forHandle=` bir kez 1 birim harcayıp kimliği çözüyor ve
  sonuç `nis_kanal` tablosunda kalıcı — tekrar ödenmiyor.

Handle yanlışsa çözüm başarısız olur ve **açık hata** verir. Sessiz bir
bozulma yok.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from .. import depo, kota
from . import hiz, toplayici

LISTE = "playlistItems.list"
ISTATISTIK = "videos.list"
KANAL = "channels.list"

# `playlistItems.list` tek çağrıda en fazla 50 öğe döndürüyor ve sayfalama
# birim başına ücretli. 50 son yükleme, taban için de karşılaştırma için de
# yeterli — bir kanalın 4 yıl önceki dönemi bugünkü videosuyla kıyaslanmaz.
LISTE_BOYUTU = 50

# Bir videonun izlenmesinin "oturduğu" kabul edilen yaş.
#
# Taban yalnızca bu yaşı geçmiş videolardan hesaplanıyor: henüz tırmanan bir
# video tabanı aşağı çeker ve o kanaldaki her şey aşırı performanslı görünür.
OLGUNLASMA_GUN = 30

# Taban için gereken asgari olgun video sayısı. 5'in altında medyan gürültü:
# tek bir viral video tabanı ikiye katlar ve kanalın geri kalanı sönük görünür.
ASGARI_OLGUN_VIDEO = 5

# Erken sinyal hesabında bölenin tabanı — DW-29'daki `ASGARI_YAS_SAAT` ile
# aynı tuzak: 2 saatlik bir video 5.000 izlenmeyle günde 60.000 gösterir.
ASGARI_YAS_GUN = 1.0

# Sıralamaya girecek videoların yaş penceresi.
#
# ⚠️ İlk canlı koşumda bulundu: pencere olmadan listenin tepesi **1.428 günlük**
# bir minutephysics videosuydu (29,42×). Ölçüm doğru ama soruya cevap değil —
# 4 yıllık bir tüm zamanlar hiti "şimdi ne yapmalıyım" sorusuna bir şey
# söylemiyor.
#
# `OLGUNLASMA_GUN` ile birlikte bir bant açıyor: 30–90 gün. Yargılanacak kadar
# oturmuş, harekete geçilecek kadar yeni. Taban yine **bütün** olgun
# videolardan hesaplanıyor; pencere yalnızca sıralamaya giren kümeyi daraltıyor.
PENCERE_GUN = 90

# Niş izlemenin günlük kota payı. Kanal başına 2 birim; 150 kanal = 300 birim.
# Kimlik çözümü bir kereye mahsus ve 50 handle tek çağrıda çözülüyor.
NIS_KOTA_TAVANI = 500
SUREC = "nis"

# ⚠️ **Elle küre edilen liste — kod değil, config.** `kanal.py` deseni.
#
# `(handle, beklenen_sinif)`. Sınıf yalnızca raporu gruplamak için; bu hattın
# sınıflandırıcıya ihtiyacı yok çünkü kanalları biz seçiyoruz.
#
# Liste başlangıç noktası: uluslararası, iyi bilinen tarih/bilim kanalları.
# Türkçe kanallar eklenmeli — projenin hedef dilleri arasında Türkçe var ve
# bu listede henüz Türkçe kanal yok. Bu bilinen bir eksiklik.
IZLENEN_KANALLAR: tuple[tuple[str, str], ...] = (
    ("@kurzgesagt", "bilim"),
    ("@veritasium", "bilim"),
    ("@SmarterEveryDay", "bilim"),
    ("@TEDEd", "bilim"),
    ("@crashcourse", "bilim"),
    ("@Vsauce", "bilim"),
    ("@SciShow", "bilim"),
    ("@numberphile", "bilim"),
    ("@3blue1brown", "bilim"),
    ("@minutephysics", "bilim"),
    ("@sixtysymbols", "bilim"),
    ("@PBSSpaceTime", "bilim"),
    ("@AsapSCIENCE", "bilim"),
    ("@Computerphile", "bilim"),
    ("@OverSimplified", "tarih"),
    ("@KingsandGenerals", "tarih"),
    ("@extrahistory", "tarih"),
    ("@HistoryMatters", "tarih"),
    ("@thegreatwar", "tarih"),
    ("@Fallofcivilizations", "tarih"),
    ("@TimelineChannel", "tarih"),
    ("@HistoriaCivilis", "tarih"),
    ("@ToldinStone", "tarih"),
    ("@voicesofthepast", "tarih"),
    ("@SimpleHistory", "tarih"),
)


class NisHatasi(RuntimeError):
    """Kanal çözülemedi ya da izlenemedi."""


# --- Kimlik çözümü -------------------------------------------------------


@dataclass
class CozumSonucu:
    cozulen: int = 0
    zaten_vardi: int = 0
    harcanan: int = 0
    bulunamayan: list[str] = field(default_factory=list)

    def ozet(self) -> str:
        satir = (
            f"{self.cozulen} kanal çözüldü · {self.zaten_vardi} zaten kayıtlı · "
            f"{self.harcanan} birim"
        )
        if self.bulunamayan:
            satir += f" · {len(self.bulunamayan)} handle bulunamadı"
        return satir


def kayitli_handleler(yol: Path) -> set[str]:
    baglanti = depo.baglan(yol)
    try:
        return {s["handle"] for s in baglanti.execute("SELECT handle FROM nis_kanal")}
    finally:
        baglanti.close()


def _kanali_coz(istemci, handle: str) -> dict | None:
    """`channels.list?forHandle=` — 1 birim, kimlik + yükleme listesi + abone.

    Yükleme listesi kimliğini `UC…` → `UU…` dönüşümüyle türetmek yaygın bir
    kestirme ama **belgelenmiş değil**. Bir birim ödeyip API'nin verdiğini
    kullanmak, belgelenmemiş bir varsayıma güvenmekten iyi.
    """
    yanit = (
        istemci.channels()
        .list(part="snippet,contentDetails,statistics", forHandle=handle)
        .execute()
    )
    ogeler = yanit.get("items") or []
    if not ogeler:
        return None
    oge = ogeler[0]
    listeler = (oge.get("contentDetails") or {}).get("relatedPlaylists") or {}
    istatistik = oge.get("statistics") or {}
    gizli = istatistik.get("hiddenSubscriberCount")
    return {
        "kanal_id": oge["id"],
        "ad": (oge.get("snippet") or {}).get("title"),
        "yukleme_listesi": listeler.get("uploads"),
        "abone": None if gizli else _tam_sayi(istatistik.get("subscriberCount")),
        "video_sayisi": _tam_sayi(istatistik.get("videoCount")),
    }


def kanallari_coz(
    istemci,
    sayac: kota.KaliciSayac,
    yol: Path,
    *,
    kanallar: tuple[tuple[str, str], ...] = IZLENEN_KANALLAR,
) -> CozumSonucu:
    """Handle'ları kimliğe çevirir ve `nis_kanal`'a yazar.

    Zaten kayıtlı olanlar için çağrı yapılmaz — bu, tekrarlanan koşumların
    bedava olmasını sağlıyor.
    """
    sonuc = CozumSonucu()
    kayitli = kayitli_handleler(yol)
    simdi = datetime.now(UTC).isoformat()

    for handle, sinif in kanallar:
        if handle in kayitli:
            sonuc.zaten_vardi += 1
            continue
        sayac.harca(KANAL, rezerve=kota.video_basina_maliyet())
        sonuc.harcanan += kota.MALIYET[KANAL]
        try:
            bilgi = _kanali_coz(istemci, handle)
        except Exception as hata:  # noqa: BLE001 — bir handle diğerlerini düşürmemeli
            sonuc.bulunamayan.append(f"{handle}: {hata}")
            continue
        if not bilgi or not bilgi["yukleme_listesi"]:
            sonuc.bulunamayan.append(handle)
            continue

        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                """
                INSERT INTO nis_kanal (kanal_id, handle, ad, sinif, yukleme_listesi,
                                       abone, video_sayisi, guncelleme)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kanal_id) DO UPDATE SET
                    handle          = excluded.handle,
                    ad              = excluded.ad,
                    yukleme_listesi = excluded.yukleme_listesi,
                    abone           = excluded.abone,
                    video_sayisi    = excluded.video_sayisi,
                    guncelleme      = excluded.guncelleme
                """,
                (
                    bilgi["kanal_id"],
                    handle,
                    bilgi["ad"],
                    sinif,
                    bilgi["yukleme_listesi"],
                    bilgi["abone"],
                    bilgi["video_sayisi"],
                    simdi,
                ),
            )
        sonuc.cozulen += 1
    return sonuc


# --- İzleme --------------------------------------------------------------


def _tam_sayi(deger) -> int | None:
    try:
        return int(deger)
    except (TypeError, ValueError):
        return None


@dataclass
class IzlemeSonucu:
    kanal_sayisi: int = 0
    video_sayisi: int = 0
    harcanan: int = 0
    kota_bitti: bool = False
    hatalar: list[str] = field(default_factory=list)

    def ozet(self) -> str:
        satir = f"{self.kanal_sayisi} kanal · {self.video_sayisi} video · {self.harcanan} birim"
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        if self.kota_bitti:
            satir += " · KOTA TAVANINDA DURDU"
        return satir


def _liste_kimlikleri(istemci, liste_id: str) -> list[str]:
    yanit = (
        istemci.playlistItems()
        .list(part="contentDetails", playlistId=liste_id, maxResults=LISTE_BOYUTU)
        .execute()
    )
    return [
        vid
        for oge in yanit.get("items", [])
        if (vid := (oge.get("contentDetails") or {}).get("videoId"))
    ]


def _videolari_getir(istemci, kimlikler: list[str]) -> list[dict]:
    yanit = (
        istemci.videos()
        .list(part="snippet,statistics,contentDetails", id=",".join(kimlikler))
        .execute()
    )
    return yanit.get("items", [])


def izle(
    istemci,
    sayac: kota.KaliciSayac,
    yol: Path,
    *,
    tavan: int = NIS_KOTA_TAVANI,
    an: datetime | None = None,
) -> IzlemeSonucu:
    """Kayıtlı kanalların son yüklemelerini çeker ve ölçümleri yazar.

    Kanal başına 2 birim. Bir kanalın hatası izlemeyi bitirmez.
    """
    an = an or datetime.now(UTC)
    damga = an.isoformat()
    sonuc = IzlemeSonucu()
    rezerve = kota.video_basina_maliyet()

    baglanti = depo.baglan(yol)
    try:
        kanallar = baglanti.execute(
            "SELECT kanal_id, ad, yukleme_listesi FROM nis_kanal "
            "WHERE yukleme_listesi IS NOT NULL ORDER BY handle"
        ).fetchall()
    finally:
        baglanti.close()

    kanal_maliyeti = kota.MALIYET[LISTE] + kota.MALIYET[ISTATISTIK]
    for kanal in kanallar:
        if sayac.surec_harcamasi + kanal_maliyeti > tavan:
            sonuc.kota_bitti = True
            break
        try:
            sayac.harca(LISTE, rezerve=rezerve)
            sonuc.harcanan += kota.MALIYET[LISTE]
            kimlikler = _liste_kimlikleri(istemci, kanal["yukleme_listesi"])
            if not kimlikler:
                continue
            sayac.harca(ISTATISTIK, rezerve=rezerve)
            sonuc.harcanan += kota.MALIYET[ISTATISTIK]
            videolar = _videolari_getir(istemci, kimlikler)
        except kota.KotaAsimi:
            sonuc.kota_bitti = True
            break
        except Exception as hata:  # noqa: BLE001 — tek kanal izlemeyi bitirmemeli
            sonuc.hatalar.append(f"{kanal['ad'] or kanal['kanal_id']}: {hata}")
            continue

        with depo.yazma_islemi(yol) as baglanti:
            for video in videolar:
                _videoyu_yaz(baglanti, video, kanal["kanal_id"], damga)
                sonuc.video_sayisi += 1
        sonuc.kanal_sayisi += 1

    return sonuc


def _videoyu_yaz(baglanti, video: dict, kanal_id: str, damga: str) -> None:
    """Metadata ortak `video` tablosuna, ölçüm `nis_olcum`'a.

    `olcum` tablosu kullanılmıyor: orada `bolge` anahtarın parçası ve niş
    videoların bölgesi yok. Yapay bir bölge kodu koymak DW-29'un
    `COUNT(DISTINCT bolge)` yayılım hesabını kirletirdi.
    """
    snippet = video.get("snippet") or {}
    istatistik = video.get("statistics") or {}
    baglanti.execute(
        """
        INSERT INTO video (video_id, baslik, kanal_id, kanal_adi, yayin_zamani,
                           kategori_id, sure_sn, ilk_gorulme)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            baslik    = excluded.baslik,
            kanal_adi = excluded.kanal_adi,
            sure_sn   = COALESCE(excluded.sure_sn, video.sure_sn)
        """,
        (
            video["id"],
            snippet.get("title") or "(başlıksız)",
            snippet.get("channelId") or kanal_id,
            snippet.get("channelTitle"),
            snippet.get("publishedAt"),
            _tam_sayi(snippet.get("categoryId")),
            # contentDetails zaten part'ta istenmişti ama süre yazılmıyordu
            # (DW-52'de bulunan tuzak): niş yoluyla giren video kalıcı NULL
            # kalıyor ve Shorts/uzun kırılımının dışında görünmez oluyordu.
            toplayici.sure_saniye((video.get("contentDetails") or {}).get("duration")),
            damga,
        ),
    )
    baglanti.execute(
        """
        INSERT INTO nis_olcum (video_id, kanal_id, an, izlenme, begeni, yorum)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id, an) DO UPDATE SET
            izlenme = excluded.izlenme,
            begeni  = excluded.begeni,
            yorum   = excluded.yorum
        """,
        (
            video["id"],
            kanal_id,
            damga,
            _tam_sayi(istatistik.get("viewCount")),
            _tam_sayi(istatistik.get("likeCount")),
            _tam_sayi(istatistik.get("commentCount")),
        ),
    )


# --- Aşırı performans ----------------------------------------------------


@dataclass
class AsiriPerformans:
    video_id: str
    baslik: str
    kanal_id: str
    kanal_adi: str | None
    kanal_sinif: str | None
    abone: int | None
    izlenme: int
    yas_gun: float
    taban: int
    oran: float
    """İzlenme ÷ kanal tabanı. Kanal büyüklüğünden bağımsız."""

    gunluk_oran: float
    """Günlük hıza göre oran — erken sinyal, gürültülü."""

    olgun: bool
    """Yaşı `OLGUNLASMA_GUN`'ü geçti mi. Geçmediyse `oran` düşük çıkar."""

    def satir(self, *, erken: bool = False) -> str:
        """Rapor satırı.

        ⚠️ Basılan sayı **sıralamaya giren sayı** olmalı. İlk canlı koşumda
        `--erken` kipinde sıralama `gunluk_oran`a göre yapılıp ekrana `oran`
        basılıyordu; sonuç, 15,03× bir satırın 1,94× ile 2,12× arasında
        durmasıydı. Rapor kendi sıralamasını yanlış gösteriyordu.
        """
        oran = self.gunluk_oran if erken else self.oran
        yas = f"{self.yas_gun:,.1f} gün"
        etiket = "" if self.olgun else " ⚠️ HENÜZ OTURMADI"
        abone = f"{self.abone:,} abone" if self.abone else "abone bilinmiyor"
        return (
            f"{oran:>6.2f}×  {self.baslik}\n"
            f"          {self.kanal_adi or self.kanal_id} ({abone}) · "
            f"{self.izlenme:,} izlenme · taban {self.taban:,} · {yas}{etiket}"
        )


def _taban(izlenmeler: list[int]) -> int | None:
    """Kanalın taban çizgisi: olgun videolarının medyan izlenmesi.

    Medyan, ortalama değil: tek bir viral video ortalamayı ikiye katlar ve
    kanalın geri kalanı sönük görünür. Aradığımız şey tam olarak "bu kanalda
    olağandışı olan" olduğu için, taban olağanı temsil etmeli.
    """
    if len(izlenmeler) < ASGARI_OLGUN_VIDEO:
        return None
    return round(median(izlenmeler))


def asiri_performans(
    yol: Path,
    *,
    erken: bool = False,
    asgari_oran: float = 1.0,
    pencere_gun: float = PENCERE_GUN,
    limit: int | None = None,
    an: datetime | None = None,
) -> list[AsiriPerformans]:
    """Kanal tabanına göre aşırı performans gösteren videolar.

    `erken=False` (varsayılan) yalnızca olgun videoları döndürüyor. Sebebi
    kabul ölçütü: yeni yüklenen bir videonun izlenmesi henüz oturmamış olur ve
    günlük hıza normalize edilirse **yanlış pozitif** üretir — 2 saatlik bir
    video 5.000 izlenmeyle günde 60.000 gösterir. Aynı tuzak DW-29'da da vardı.

    `erken=True` o videoları da katıyor ve `gunluk_oran`a göre sıralıyor, ama
    her biri raporda açıkça işaretleniyor. Erken sinyal gürültülüdür; kararı
    onun üstüne kurmak değil, bakılacak yeri göstermek için.

    `pencere_gun=0` pencereyi kapatır ve tüm zamanlar sıralaması verir. Varsayılan
    açık, çünkü canlı koşumda pencere olmadan liste 4 yıllık hitlerle doluyor.
    """
    an = an or datetime.now(UTC)
    baglanti = depo.baglan(yol)
    try:
        satirlar = baglanti.execute(
            """
            SELECT n.video_id, n.kanal_id, n.izlenme, v.baslik, v.yayin_zamani,
                   k.ad AS kanal_adi, k.sinif AS kanal_sinif, k.abone
            FROM nis_olcum n
            JOIN video v ON v.video_id = n.video_id
            LEFT JOIN nis_kanal k ON k.kanal_id = n.kanal_id
            WHERE n.an = (SELECT MAX(m.an) FROM nis_olcum m WHERE m.video_id = n.video_id)
              AND n.izlenme IS NOT NULL
            """
        ).fetchall()
    finally:
        baglanti.close()

    # Kanal başına grupla; taban o kanalın **olgun** videolarından çıkıyor.
    kanal_kayitlari: dict[str, list[dict]] = {}
    for satir in satirlar:
        yayin = hiz.zamana_cevir(satir["yayin_zamani"])
        if yayin is None:
            continue
        kayit = dict(satir)
        kayit["yas_gun"] = max((an - yayin).total_seconds() / 86_400, 0.0)
        kanal_kayitlari.setdefault(satir["kanal_id"], []).append(kayit)

    cikti: list[AsiriPerformans] = []
    for kanal_id, kayitlar in kanal_kayitlari.items():
        olgunlar = [k["izlenme"] for k in kayitlar if k["yas_gun"] >= OLGUNLASMA_GUN]
        taban = _taban(olgunlar)
        if taban is None or taban <= 0:
            # Kanalın olgun video sayısı yetmiyor: taban güvenilmez, o kanalın
            # hiçbir videosu sıralanmıyor. Yanlış taban, yanlış zirve demek.
            continue
        for kayit in kayitlar:
            olgun = kayit["yas_gun"] >= OLGUNLASMA_GUN
            oran = kayit["izlenme"] / taban
            gunluk = kayit["izlenme"] / max(kayit["yas_gun"], ASGARI_YAS_GUN)
            gunluk_oran = gunluk / (taban / OLGUNLASMA_GUN)
            if not olgun and not erken:
                continue
            if pencere_gun and kayit["yas_gun"] > pencere_gun:
                continue
            if (gunluk_oran if erken else oran) < asgari_oran:
                continue
            cikti.append(
                AsiriPerformans(
                    video_id=kayit["video_id"],
                    baslik=kayit["baslik"],
                    kanal_id=kanal_id,
                    kanal_adi=kayit["kanal_adi"],
                    kanal_sinif=kayit["kanal_sinif"],
                    abone=kayit["abone"],
                    izlenme=kayit["izlenme"],
                    yas_gun=kayit["yas_gun"],
                    taban=taban,
                    oran=oran,
                    gunluk_oran=gunluk_oran,
                    olgun=olgun,
                )
            )

    cikti.sort(key=lambda a: a.gunluk_oran if erken else a.oran, reverse=True)
    return cikti[:limit] if limit else cikti
