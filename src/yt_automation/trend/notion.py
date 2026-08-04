"""Trend çıktısını Notion'a aktarır — 📈 Trend Adayları database'i.

**Ömer'e devir noktası burası.** Ham zaman serisi SQLite'ta kalıyor (gerçeğin
kaynağı); Notion'a günlük ilk-N adayın özeti yazılıyor ve içerik üretimi
oradan besleniyor.

## Neden özet, ham veri değil

Hız hesabı geçmiş anları sorgulamayı gerektiriyor ve Notion'un okuma tarafı
ücretsiz planda saatlik kotalı. Kotayı hesaplama yoluna sokmak riskli — PRD
aynı gerekçeyle Notion'ı yükleme kuyruğu olarak reddetmişti. Yazma tarafı
kotasız, o yüzden sorun değil.

## Tekrar yazmama SQLite'ta tutuluyor, Notion'a sorularak değil

"Bu video daha önce aktarıldı mı?" sorusunun ucuz cevabı yerel: `aktarim`
tablosu. Notion'a sormak her koşuda bir okuma çağrısı demek olurdu ve
kaçındığımız şey tam olarak o.

Yan etki bilinçli: Ömer bir adayı Notion'dan **silerse** yeniden yazılmaz.
Doğru davranış bu — silmek "bunu görmek istemiyorum" demek. Yeniden istemek
için `--zorla` var.

## Sırlar

`NOTION_TOKEN` ortam değişkeninden okunuyor. Token bir **iç entegrasyon**
tokenı olmalı ve database `duo-works` hub'ı altında ona paylaşılmış olmalı;
yoksa API 404 döner (403 değil — Notion var olmayan ve erişilemeyen kaynağı
ayırt etmiyor). Hata mesajı bu tuzağı açıkça söylüyor.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import depo
from . import bosluk, hiz, kaynak

TOKEN_DEGISKENI = "NOTION_TOKEN"
DATABASE_DEGISKENI = "NOTION_TREND_DB"

# Notion REST API. Sürüm başlığı zorunlu ve sabitlenmesi gerekiyor: Notion
# yayımlanmış sürümleri kırmıyor ama sürüm göndermeyen isteği reddediyor.
TABAN = "https://api.notion.com/v1"
SURUM = "2022-06-28"

# Aktarılacak varsayılan aday sayısı. Günde 1 video üretiliyor; 20 aday
# seçmek için bol, gözle taranacak kadar az.
VARSAYILAN_ADET = 20

# Notion başlık alanının sert sınırı 2000 karakter. YouTube başlıkları 100
# karakterle sınırlı ama kanal adı + başlık birleştirmesi yapmıyoruz diye
# yine de kırpıyoruz — sessiz 400 hatası almaktan iyi.
BASLIK_SINIRI = 2_000

IZLENME_ESIGI = 0


class NotionHatasi(RuntimeError):
    """Notion'a yazılamadı."""


def token_al() -> str:
    token = os.environ.get(TOKEN_DEGISKENI)
    if not token:
        raise NotionHatasi(
            f"{TOKEN_DEGISKENI} tanımlı değil. notion.so/my-integrations → "
            "New integration ile iç entegrasyon açın, tokenı `.env`'e koyun ve "
            "kabuğa aktarın: set -a; source .env; set +a"
        )
    return token


def database_al() -> str:
    kimlik = os.environ.get(DATABASE_DEGISKENI)
    if not kimlik:
        raise NotionHatasi(
            f"{DATABASE_DEGISKENI} tanımlı değil. 📈 Trend Adayları database'inin "
            "kimliği gerekiyor; `.env.example`'daki not bunu anlatıyor."
        )
    return kimlik


def _istek(yol: str, govde: dict | None, token: str, *, yontem: str = "POST") -> dict:
    istek = urllib.request.Request(
        f"{TABAN}{yol}",
        data=json.dumps(govde).encode() if govde is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": SURUM,
            "Content-Type": "application/json",
        },
        method=yontem,
    )
    try:
        with urllib.request.urlopen(istek, timeout=30) as yanit:
            return json.load(yanit)
    except urllib.error.HTTPError as hata:
        ayrinti = hata.read().decode(errors="replace")[:400]
        if hata.code == 404:
            raise NotionHatasi(
                "Notion 404 döndü. Genellikle sebep eksik erişim, eksik kaynak "
                "değil: database'i entegrasyona paylaşın (database sayfası → ⋯ → "
                f"Connections → entegrasyonu ekleyin). Ayrıntı: {ayrinti}"
            ) from hata
        raise NotionHatasi(f"Notion HTTP {hata.code}: {ayrinti}") from hata
    except urllib.error.URLError as hata:
        raise NotionHatasi(f"Notion'a ulaşılamadı: {hata.reason}") from hata


# --- Aday seçimi ---------------------------------------------------------


def aktarilmamis_adaylar(
    yol: Path,
    *,
    adet: int = VARSAYILAN_ADET,
    siniflar: tuple[str, ...] = ("tarih", "bilim"),
    sirala: str = "ivme",
    zorla: bool = False,
) -> list[hiz.Sinyal]:
    """İvmeye göre en iyi, henüz aktarılmamış adaylar.

    Sınıf filtresi varsayılan olarak **açık** — burası Ömer'in göreceği liste
    ve projenin amacı tarih/bilim. `trend rapor`'da filtre kapalıydı çünkü
    orası teşhis çıktısı.
    """
    sinyaller = hiz.hesapla(yol, siniflar=siniflar, sirala=sirala)
    if not zorla:
        gonderilmis = _aktarilanlar(yol)
        sinyaller = [s for s in sinyaller if s.video_id not in gonderilmis]
    return sinyaller[:adet]


def _aktarilanlar(yol: Path) -> set[str]:
    baglanti = depo.baglan(yol)
    try:
        return {s["video_id"] for s in baglanti.execute("SELECT video_id FROM aktarim")}
    finally:
        baglanti.close()


def _aktarim_sayfalari(yol: Path) -> dict[str, str]:
    """`anahtar → sayfa_url` — daha önce yazılmış sayfaları geri bulmak için."""
    baglanti = depo.baglan(yol)
    try:
        return {
            s["video_id"]: s["sayfa_url"]
            for s in baglanti.execute(
                "SELECT video_id, sayfa_url FROM aktarim "
                "WHERE hedef='notion' AND sayfa_url IS NOT NULL"
            )
            if s["sayfa_url"]
        }
    finally:
        baglanti.close()


def sayfa_kimligi(url: str) -> str | None:
    """Notion sayfa URL'inden 32 haneli kimliği çıkarır.

    URL biçimi `.../Baslik-<32 hane hex>`; başlık kısmı Türkçe karakterlerde
    değişebiliyor ama kimlik sabit. Kimlik bulunamazsa `None` — uydurulmuş bir
    kimliğe PATCH atmak başka bir sayfayı bozabilir.
    """
    son = url.rstrip("/").rsplit("-", 1)[-1].rsplit("/", 1)[-1]
    return son if len(son) == 32 and all(c in "0123456789abcdef" for c in son.lower()) else None


def _aktarimi_yaz(yol: Path, video_id: str, sayfa_url: str, an: str) -> None:
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            """
            INSERT INTO aktarim (video_id, hedef, sayfa_url, an)
            VALUES (?, 'notion', ?, ?)
            ON CONFLICT(video_id, hedef) DO UPDATE SET
                sayfa_url = excluded.sayfa_url,
                an        = excluded.an
            """,
            (video_id, sayfa_url, an),
        )


# --- Yazma ---------------------------------------------------------------


def _metin(deger: str | None) -> dict:
    return {"rich_text": [{"text": {"content": (deger or "")[:BASLIK_SINIRI]}}]}


def _sayi(deger: float | None) -> dict:
    # `None` gönderilebiliyor ve Notion alanı boş bırakıyor — 0 yazmak
    # "hesaplanamadı" ile "sıfır"ı karıştırırdı. Aynı ayrım `hiz.Sinyal`'de de var.
    return {"number": None if deger is None else round(deger, 2)}


def ozellikler(sinyal: hiz.Sinyal, *, bolge: str | None, gun: str) -> dict:
    """`hiz.Sinyal`'i Notion özellik sözlüğüne çevirir."""
    return {
        "Başlık": {"title": [{"text": {"content": sinyal.baslik[:BASLIK_SINIRI]}}]},
        "Kaynak": {"select": {"name": "youtube-chart"}},
        "Bağlantı": {"url": f"https://www.youtube.com/watch?v={sinyal.video_id}"},
        "Kanal": _metin(sinyal.kanal_adi),
        "Ülke": _metin(bolge),
        "Dil": _metin(None),
        "Sınıf": {"select": {"name": sinyal.sinif} if sinyal.sinif else None},
        "İzlenme": _sayi(sinyal.izlenme),
        "Hız": _sayi(sinyal.hiz),
        "İvme": _sayi(sinyal.ivme),
        "Yaş (saat)": _sayi(sinyal.yas_saat),
        "Kategori": _sayi(sinyal.kategori_id),
        "Tespit tarihi": {"date": {"start": gun}},
        "Durum": {"select": {"name": "Yeni"}},
    }


# ⚠️ **Notion `rich_text.content` markdown YORUMLAMIYOR.** İçerik literal
# alınıyor, yani `**kalın**` ekranda yıldızlarıyla birlikte görünüyor. İlk
# canlı aktarımda tam bu oldu:
#
#     \*\*Great Zimbabwe\*\* · en.wikipedia · \[tarih\]
#     Kaynak: \`ytoto trend aktar\`
#
# Vurgu `annotations` alanıyla veriliyor, işaretle değil. Bu yüzden gövde
# metinlerinde markdown sözdizimi kullanılmıyor.
def _blok(metin: str, *, tur: str = "paragraph", **bicim) -> dict:
    """Tek bir Notion bloğu. `bicim`: bold, code, italic…"""
    parca: dict = {"text": {"content": metin[:BASLIK_SINIRI]}}
    if bicim:
        parca["annotations"] = bicim
    return {"object": "block", "type": tur, tur: {"rich_text": [parca]}}


def govde_metni(sinyal: hiz.Sinyal) -> list[dict]:
    """Sayfa gövdesi — kabul ölçütü "Ömer içerik üretimine başlayabilecek kadar
    bağlam buluyor" burada karşılanıyor.

    Özellikler sayıları taşıyor; gövde **sayıların ne anlama geldiğini** ve
    hangi uyarılarla okunması gerektiğini taşıyor. Ömer'in bu dosyaları
    okumadan çalışması gerekiyor.
    """
    satirlar = []
    if sinyal.kanal_adi:
        satirlar.append(f"Kanal: {sinyal.kanal_adi}")
    satirlar.append(f"İzlenme: {sinyal.izlenme:,}")
    if sinyal.hiz is not None:
        satirlar.append(f"Hız: {sinyal.hiz:+,.0f} izlenme/saat")
    if sinyal.ivme is not None:
        satirlar.append(
            f"İvme: {sinyal.ivme:+,.0f} izlenme/saat² "
            f"({'hızlanıyor' if sinyal.ivme > 0 else 'yavaşlıyor'})"
        )
    else:
        satirlar.append("İvme: hesaplanamadı (en az üç ölçüm gerekiyor)")
    if sinyal.yas_saat is not None:
        satirlar.append(f"Yaş: {sinyal.yas_saat:,.0f} saat · yaşa göre {sinyal.yasa_gore:,.0f}/sa")
    if sinyal.en_iyi_sira is not None:
        satirlar.append(f"En iyi sıra: #{sinyal.en_iyi_sira} · {sinyal.bolge_sayisi} bölgede")
    if sinyal.yeni_giren:
        satirlar.append("🆕 Listeye bu taramada yeni girdi.")
    satirlar.append(
        "⚠️ Bu bir TALEP sinyali, arz sinyali değil: burada trend olan konuyu "
        "büyük kanallar zaten yapmış olabilir. Üretime almadan önce "
        "ytoto bosluk rapor çıktısına bakın."
    )
    return [
        _blok(sinyal.baslik, tur="heading_3"),
        *[_blok(s) for s in satirlar if s],
        _blok(f"ytoto trend aktar · video kimliği {sinyal.video_id}", code=True),
    ]


# --- Wikipedia adayları: asıl devir noktası ------------------------------
#
# ⚠️ Görev DW-31 çart videolarını aktarmak üzere yazılmıştı. Canlı ölçüm o
# yolun boş olduğunu gösterdi: 4.905 çart videosunda **sıfır** tarih, 19 bilim
# ve o 19'un hepsi VS Code dersi, drone incelemesi, Python kursu. Ömer'e
# gönderilecek liste bu değil.
#
# Huninin gerçekten ürettiği şey Wikipedia adayları + arz ölçümü + kaynak
# dosyası. Aktarım ikisini de destekliyor; `Kaynak` alanı hangisi olduğunu
# söylüyor.


def aktarilmamis_bosluklar(
    yol: Path, *, adet: int = VARSAYILAN_ADET, zorla: bool = False
) -> list[bosluk.Bosluk]:
    """Kapıları geçmiş, kalibre skora göre sıralı, henüz aktarılmamış adaylar.

    ⚠️ `zorla` **kapıları da** açıyor, yalnızca "daha önce gönderildi" filtresini
    değil. Sebebi: iki farklı "hepsini göster" anlamı taşımak kafa karıştırır ve
    kapının elediğini elle görmek isteyen birinin başka bir bayrağı yok.
    """
    kayitlar = bosluk.bosluklar(yol)
    if not zorla:
        kayitlar = [k for k in kayitlar if bosluk.red_gerekcesi(k) is None]
        gonderilmis = _aktarilanlar(yol)
        kayitlar = [k for k in kayitlar if _bosluk_anahtari(k) not in gonderilmis]
    return kayitlar[:adet]


def bosluk_kapi_ozeti(yol: Path) -> tuple[int, dict[str, int]]:
    """`(kapıyı geçen sayısı, gerekçe başına elenen sayısı)`.

    İkisi birlikte dönüyor çünkü **ayrı ayrı yanıltıcılar**: "aktarılacak aday
    yok" iki bambaşka duruma karşılık gelebiliyor — kapı hepsini eledi, ya da
    kapıyı geçenlerin hepsi zaten gönderilmiş. İlkinde huni bilerek boş geçmiş,
    ikincisinde yeni ölçüm gerekiyor. Yalnızca eleme sayısına bakan bir rapor
    ikincisini birincisi gibi gösterir.

    Rapor için: kaç adayın **neden** düştüğünü basmayan bir kapı, sessizce
    çalışan bir kapıdır ve eşikleri kimse revize edemez.
    """
    gecen = 0
    sayim: dict[str, int] = {}
    for kayit in bosluk.bosluklar(yol):
        gerekce = bosluk.red_gerekcesi(kayit)
        if gerekce:
            sayim[gerekce] = sayim.get(gerekce, 0) + 1
        else:
            gecen += 1
    return gecen, sayim


def _bosluk_anahtari(kayit: bosluk.Bosluk) -> str:
    """`aktarim` tablosunun anahtarı video kimliği üzerine kurulu; Wikipedia
    adayının video kimliği yok, o yüzden (qid, dil) birleştiriliyor.

    Ayrı bir tablo açmak yerine aynı deftere yazmak bilinçli: "bu daha önce
    gönderildi mi" sorusu tek yerde cevaplanmalı.
    """
    return f"wiki:{kayit.qid}:{kayit.dil}"


def bosluk_ozellikleri(
    kayit: bosluk.Bosluk, *, gun: str, kaynak_sayisi: int | None, durum: str = "Yeni"
) -> dict:
    baslik = kayit.baslik.replace("_", " ")
    return {
        "Başlık": {"title": [{"text": {"content": baslik[:BASLIK_SINIRI]}}]},
        "Kaynak": {"select": {"name": "wikipedia"}},
        "Bağlantı": {
            "url": f"https://{kayit.dil}.wikipedia.org/wiki/{kayit.baslik}",
        },
        "Dil": _metin(kayit.dil),
        "Sınıf": {"select": {"name": kayit.sinif} if kayit.sinif else None},
        "Talep (okunma)": _sayi(kayit.talep),
        "Boşluk skoru": _sayi(kayit.skor),
        "Arz": _metin(kayit.olcum.ozet()),
        # "Belirsiz" iki durumu birden taşıyor: kırılım ölçülmedi ya da iki
        # format ayırt edilemeyecek kadar yakın. İkisinde de karar insanda —
        # ayrım gövdedeki arz özetinden okunuyor.
        "Önerilen format": {
            "select": {
                "name": {"shorts": "Shorts", "uzun": "Uzun"}.get(kayit.onerilen_format, "Belirsiz")
            }
        },
        # Hedef kanal yalnızca **kapının tamamını** geçen adaya yazılıyor.
        # `Önerilen format` sıralama bilgisi de taşıyabiliyor (kapıyı hiçbiri
        # geçmese bile en iyisini gösteriyor); kanal ataması ise bir karar ve
        # eşiği geçmemiş bir adayı kanala yazmak o kararı uydurmak olurdu.
        #
        # ⚠️ Burada `gecen_formatlar` TEK BAŞINA yetmiyor ve bu ölçüldü
        # (2026-08-04): geçen formatı olan 8 adayın 5'i mutlak talep kapısında
        # eleniyordu ve yine de kanal ataması alıyordu. Aktarım yolunda hiç
        # görünmedi çünkü oraya zaten yalnızca kapıyı geçen aday giriyor;
        # `bosluklari_guncelle` elenmişlere de dokununca ortaya çıktı.
        "Hedef kanal": {
            "select": (
                {"name": {"shorts": "Shorts kanal", "uzun": "Uzun kanal"}[gecen[0]]}
                if (gecen := kayit.gecen_formatlar) and bosluk.red_gerekcesi(kayit) is None
                else None
            )
        },
        "Kaynak sayısı": _sayi(kaynak_sayisi),
        "Tespit tarihi": {"date": {"start": gun}},
        "Durum": {"select": {"name": durum}},
    }


def dosya_dolu(dosya: dict | None) -> bool:
    """`kaynak.dosyayi_oku` hiç kayıt yokken de üç boş liste döndürüyor.

    Yani `if dosya:` her zaman doğru. Bu ayrımı kaçırmak "kaynak dosyası yok"
    uyarısını sessizce yok eder — kaynaksız bir konunun videoya dönmesinin
    önündeki tek engel o uyarı.
    """
    return bool(dosya) and any(dosya.get(t) for t in ("referans", "olgu", "gorsel"))


def _kaynak_sayisi(dosya: dict | None) -> int | None:
    if not dosya_dolu(dosya):
        return None
    return sum(len(dosya.get(t) or []) for t in ("referans", "olgu", "gorsel"))


def bosluk_govdesi(kayit: bosluk.Bosluk, dosya: dict | None) -> list[dict]:
    """Ömer'in üretime başlaması için gereken her şey tek sayfada.

    Üç blok: ne kadar talep var, karşısında ne var, neye dayanarak anlatılacak.
    Kaynak dosyası olmadan bir video **yapılmamalı** — PRD'nin YPP karşı
    önlemlerinin birincisi bu.
    """
    baslik = kayit.baslik.replace("_", " ")
    skor = "hesaplanamadı" if kayit.skor is None else f"{kayit.skor:+.2f}"
    kalibre = "hesaplanamadı" if kayit.kalibre is None else f"{kayit.kalibre:+.2f} MAD"
    satirlar = [
        f"{kayit.dil}.wikipedia · [{kayit.sinif}]",
        f"TALEP — {kayit.talep:,} günlük okunma",
        f"ARZ — {kayit.olcum.ozet()}",
        f"BOŞLUK SKORU — {kalibre} (ham {skor})",
    ]

    # ⚠️ Kapı DW-58'den beri format başına çalışıyor, yani aday **birleşik**
    # kalibresi eşiğin altındayken de geçmiş olabilir — tek bir formatta
    # parlıyorsa. Yalnızca birleşik değeri göstermek operatöre eşiğin altında
    # bir sayı gösterip "bu aday neden burada?" dedirtirdi. Geçen format ve
    # onun kendi kalibresi bu yüzden ayrıca yazılıyor.
    if kalibreler := kayit.format_kalibreleri:
        ayrinti = " · ".join(
            f"{'Shorts' if ad == 'shorts' else 'Uzun'} {deger:+.2f} MAD"
            for ad, deger in sorted(kalibreler.items())
        )
        satirlar.append(f"FORMAT BAŞINA — {ayrinti}")
        if gecen := kayit.gecen_formatlar:
            adlar = ", ".join("Shorts" if a == "shorts" else "Uzun" for a in gecen)
            satirlar.append(
                f"Bu aday {adlar} formatında eşiği geçti. Her format kendi taban "
                "çizgisine göre ölçülüyor: Shorts sistematik olarak uzun videodan "
                "daha çok izlenme aldığı için ikisi aynı potada kıyaslanmıyor."
            )
    else:
        satirlar.append(
            f"Bu aday {kayit.dil} pazarının olağanından {kalibre} daha iyi. Ham skorun "
            "mutlak seviyesi fırsatı değil PAZAR BÜYÜKLÜĞÜNÜ kodluyor, o yüzden diller "
            "arası karşılaştırma kalibre değer üzerinden yapılır."
        )

    satirlar.append(
        f"⚠️ Eşikler ({bosluk.ESIK_KALIBRE:.1f} MAD ve {bosluk.ASGARI_TALEP:,} okunma/gün) "
        "gözlenen dağılımdan seçildi, YAYIN SONUÇLARINDAN DEĞİL — henüz tek video "
        "yayınlanmadı. İlk sonuçlar gelince revize edilmeli."
    )

    if dosya_dolu(dosya):
        satirlar.append(
            f"KAYNAK DOSYASI — {len(dosya['referans'])} referans · "
            f"{len(dosya['olgu'])} olgu · {len(dosya['gorsel'])} görsel"
        )
        for olgu in dosya["olgu"][:8]:
            satirlar.append(f"  · {olgu['etiket']}: {olgu['deger']}")
        for ref in dosya["referans"][:5]:
            satirlar.append(f"  → {ref['deger']}")
        for gorsel in dosya["gorsel"][:3]:
            satirlar.append(f"  🖼 {gorsel['deger']} — {gorsel['lisans']} (atıf: {gorsel['atif']})")
    else:
        satirlar.append(
            "KAYNAK DOSYASI — YOK. `ytoto konu kaynak` çalıştırılmadan bu konu "
            "videoya dönüşmemeli: iddiaların dayanağı ve görsellerin lisansı eksik."
        )

    return [
        _blok(baslik, tur="heading_3"),
        *[_blok(s) for s in satirlar if s],
        _blok(f"ytoto trend aktar --kaynak wikipedia · Wikidata {kayit.qid}", code=True),
    ]


@dataclass
class AktarimSonucu:
    yazilan: int = 0
    atlanan: int = 0
    hatalar: list[str] = field(default_factory=list)
    sayfalar: list[str] = field(default_factory=list)

    def ozet(self) -> str:
        satir = f"{self.yazilan} aday Notion'a yazıldı"
        if self.atlanan:
            satir += f" · {self.atlanan} zaten aktarılmış"
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        return satir


def aktar(
    yol: Path,
    *,
    adaylar: list[hiz.Sinyal],
    database: str,
    token: str,
    bolge: str | None = None,
    an: datetime | None = None,
) -> AktarimSonucu:
    """Adayları Notion'a yazar ve her birini `aktarim` tablosuna işler.

    Bir adayın hatası aktarımı bitirmez — aynı karar bölgeler (DW-28), diller
    (DW-34) ve kanallar (DW-36) için de verildi.
    """
    an = an or datetime.now(UTC)
    sonuc = AktarimSonucu()
    gun = an.date().isoformat()

    for sinyal in adaylar:
        try:
            yanit = _istek(
                "/pages",
                {
                    "parent": {"database_id": database},
                    "properties": ozellikler(sinyal, bolge=bolge, gun=gun),
                    "children": govde_metni(sinyal),
                },
                token,
            )
        except NotionHatasi as hata:
            sonuc.hatalar.append(f"{sinyal.baslik[:60]}: {hata}")
            continue
        sayfa_url = yanit.get("url") or ""
        # Kayıt yazma **başarıdan sonra**: önce yazılsa ve istek patlasa, aday
        # bir daha hiç aktarılmazdı ve kimse fark etmezdi.
        _aktarimi_yaz(yol, sinyal.video_id, sayfa_url, an.isoformat())
        sonuc.yazilan += 1
        sonuc.sayfalar.append(sayfa_url)

    return sonuc


def bosluklari_aktar(
    yol: Path,
    *,
    adaylar: list[bosluk.Bosluk],
    database: str,
    token: str,
    an: datetime | None = None,
    acil_qidler: set[str] | None = None,
) -> AktarimSonucu:
    """Wikipedia adaylarını kaynak dosyalarıyla birlikte Notion'a yazar.

    `acil_qidler` (DW-54): sıçrama detektörünün işaretledikleri `🔥 Acil`
    durumuyla düşer — Notion bildirim aboneliği o durumu telefona taşır.
    """
    an = an or datetime.now(UTC)
    sonuc = AktarimSonucu()
    gun = an.date().isoformat()
    acil_qidler = acil_qidler or set()

    for kayit in adaylar:
        dosya = kaynak.dosyayi_oku(yol, kayit.qid)
        sayi = _kaynak_sayisi(dosya)
        try:
            yanit = _istek(
                "/pages",
                {
                    "parent": {"database_id": database},
                    "properties": bosluk_ozellikleri(
                        kayit,
                        gun=gun,
                        kaynak_sayisi=sayi,
                        durum="🔥 Acil" if kayit.qid in acil_qidler else "Yeni",
                    ),
                    "children": bosluk_govdesi(kayit, dosya),
                },
                token,
            )
        except NotionHatasi as hata:
            sonuc.hatalar.append(f"{kayit.baslik[:60]}: {hata}")
            continue
        sayfa_url = yanit.get("url") or ""
        _aktarimi_yaz(yol, _bosluk_anahtari(kayit), sayfa_url, an.isoformat())
        sonuc.yazilan += 1
        sonuc.sayfalar.append(sayfa_url)

    return sonuc


# Notion API saniyede ~3 istek kabul ediyor; sayfa başına iki çağrı (oku +
# yaz) yapıldığı için araya bekleme konuyor. DW-55'te Wikipedia 429 döndürdüğü
# gün öğrenildi: hız sınırını denemeyle bulmak, çalışan bir işi ortasında
# kaybetmek demek.
BEKLEME_SN = 0.35

# İnsanın dokunmadığı tek durum. Toplu güncelleme yalnızca bunu değiştiriyor:
# birinin "İnceleniyor" ya da "Seçildi" yaptığı bir adayı otomasyon "Elendi"ye
# çekerse insan kararını ezmiş olur ve geri alması elle iş.
DOKUNULMAMIS_DURUM = "Yeni"
ELENDI_DURUMU = "Elendi"


@dataclass
class GuncellemeSonucu:
    guncellenen: int = 0
    elendi: int = 0
    sayfasiz: int = 0
    copte: int = 0
    hatalar: list[str] = field(default_factory=list)


def bosluklari_guncelle(
    yol: Path,
    *,
    adaylar: list[bosluk.Bosluk],
    token: str,
    ele: bool = False,
    bekleme: float = BEKLEME_SN,
) -> GuncellemeSonucu:
    """Daha önce yazılmış sayfaların format ve durum alanlarını tazeler.

    Neden gerekiyor: `Önerilen format` DW-58'de eklendi, ondan önce yazılmış
    sayfalarda alan **boş**. Yeniden ölçüm (`kirilimsiz_adaylar`) kırılımı
    dolduruyor ama Notion'daki sayfa kendiliğinden güncellenmiyor — aktarım
    tek yönlü ve bir kez çalışıyor.

    `ele=True` ise kapıyı geçemeyen aday `Elendi` durumuna çekilir. Yalnızca
    durumu hâlâ `DOKUNULMAMIS_DURUM` olanlar; insanın ellediği satır
    korunuyor.

    Gövde metni **yeniden yazılmıyor**: `children` güncellemesi mevcut blokları
    silip yeniden kurmayı gerektiriyor ve bu, sayfaya insan eliyle eklenmiş
    notları siler. Alan güncellemesi kayıpsız, gövde güncellemesi değil.
    """
    sonuc = GuncellemeSonucu()
    sayfalar = _aktarim_sayfalari(yol)

    for kayit in adaylar:
        url = sayfalar.get(_bosluk_anahtari(kayit))
        if not url:
            sonuc.sayfasiz += 1
            continue
        kimlik = sayfa_kimligi(url)
        if not kimlik:
            sonuc.hatalar.append(f"{kayit.baslik[:60]}: sayfa kimliği okunamadı ({url})")
            continue

        try:
            mevcut = _istek(f"/pages/{kimlik}", None, token, yontem="GET")
            time.sleep(bekleme)
        except NotionHatasi as hata:
            sonuc.hatalar.append(f"{kayit.baslik[:60]}: {hata}")
            continue

        # ⚠️ Çöpe atılmış sayfaya PATCH atmak sessiz bir kayıp: istek başarılı
        # döner, kimse görmez ve defter Notion'dan ayrışmış olur. Ölçüldü
        # (2026-08-04): mükerrer bir sayfa elle silindi, defter silineni
        # gösteriyordu ve görünen sayfa bir daha hiç güncellenmezdi. Sayılıp
        # raporlanıyor — defterin tazelenmesi gerektiğinin işareti.
        if mevcut.get("in_trash") or mevcut.get("archived"):
            sonuc.copte += 1
            continue

        secili = (mevcut.get("properties", {}).get("Durum", {}) or {}).get("select") or {}
        durum = secili.get("name")

        # Alanlar `bosluk_ozellikleri`'nden **seçilerek** alınıyor, elle
        # kurulmuyor: format eşlemesi ("shorts" → "Shorts") tek yerde kalsın,
        # yoksa aktarım ile güncelleme zamanla birbirinden ayrışır. Buradan
        # alınmayan alanlar (Tespit tarihi, Kaynak sayısı, Başlık…) bilerek
        # dokunulmadan bırakılıyor — `gun`/`kaynak_sayisi` bu yüzden boş.
        tam = bosluk_ozellikleri(kayit, gun="", kaynak_sayisi=None, durum=durum or "Yeni")
        ozellikler = {
            "Önerilen format": tam["Önerilen format"],
            "Hedef kanal": tam["Hedef kanal"],
            "Arz": tam["Arz"],
            "Boşluk skoru": tam["Boşluk skoru"],
        }
        elendi = False
        if ele and durum == DOKUNULMAMIS_DURUM and bosluk.red_gerekcesi(kayit) is not None:
            ozellikler["Durum"] = {"select": {"name": ELENDI_DURUMU}}
            elendi = True

        try:
            _istek(f"/pages/{kimlik}", {"properties": ozellikler}, token, yontem="PATCH")
            time.sleep(bekleme)
        except NotionHatasi as hata:
            sonuc.hatalar.append(f"{kayit.baslik[:60]}: {hata}")
            continue

        sonuc.guncellenen += 1
        sonuc.elendi += int(elendi)

    return sonuc
