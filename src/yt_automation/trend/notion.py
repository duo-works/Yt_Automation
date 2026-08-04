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


def _istek(yol: str, govde: dict, token: str) -> dict:
    istek = urllib.request.Request(
        f"{TABAN}{yol}",
        data=json.dumps(govde).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": SURUM,
            "Content-Type": "application/json",
        },
        method="POST",
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


def govde_metni(sinyal: hiz.Sinyal) -> list[dict]:
    """Sayfa gövdesi — kabul ölçütü "Ömer içerik üretimine başlayabilecek kadar
    bağlam buluyor" burada karşılanıyor.

    Özellikler sayıları taşıyor; gövde **sayıların ne anlama geldiğini** ve
    hangi uyarılarla okunması gerektiğini taşıyor. Ömer'in bu dosyaları
    okumadan çalışması gerekiyor.
    """
    satirlar = [f"**{sinyal.baslik}**", ""]
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
    satirlar += [
        "",
        "⚠️ Bu bir **talep** sinyali, arz sinyali değil: burada trend olan konuyu "
        "büyük kanallar zaten yapmış olabilir. Üretime almadan önce "
        "`ytoto bosluk rapor` çıktısına bakın.",
        "",
        f"Kaynak: `ytoto trend aktar` · video kimliği `{sinyal.video_id}`",
    ]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": satir}}]},
        }
        for satir in satirlar
        if satir
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
    """Arzı ölçülmüş, boşluk skoruna göre sıralı, henüz aktarılmamış adaylar."""
    kayitlar = bosluk.bosluklar(yol)
    if not zorla:
        gonderilmis = _aktarilanlar(yol)
        kayitlar = [k for k in kayitlar if _bosluk_anahtari(k) not in gonderilmis]
    return kayitlar[:adet]


def _bosluk_anahtari(kayit: bosluk.Bosluk) -> str:
    """`aktarim` tablosunun anahtarı video kimliği üzerine kurulu; Wikipedia
    adayının video kimliği yok, o yüzden (qid, dil) birleştiriliyor.

    Ayrı bir tablo açmak yerine aynı deftere yazmak bilinçli: "bu daha önce
    gönderildi mi" sorusu tek yerde cevaplanmalı.
    """
    return f"wiki:{kayit.qid}:{kayit.dil}"


def bosluk_ozellikleri(kayit: bosluk.Bosluk, *, gun: str, kaynak_sayisi: int | None) -> dict:
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
        "Kaynak sayısı": _sayi(kaynak_sayisi),
        "Tespit tarihi": {"date": {"start": gun}},
        "Durum": {"select": {"name": "Yeni"}},
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
    satirlar = [
        f"**{baslik}** · {kayit.dil}.wikipedia · [{kayit.sinif}]",
        "",
        f"TALEP — {kayit.talep:,} günlük okunma",
        f"ARZ — {kayit.olcum.ozet()}",
        f"BOŞLUK SKORU — {skor}",
        "",
        "⚠️ Skor bir **sıralamadır, eşik değildir**: Wikipedia okunması ile YouTube "
        "izlenmesi farklı ölçeklerde olduğu için işaret kalibre edilmedi. Adayları "
        "birbirine göre karşılaştırın, sıfırı sınır saymayın.",
        "",
    ]

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
            "KAYNAK DOSYASI — **yok.** `ytoto konu kaynak` çalıştırılmadan bu konu "
            "videoya dönüşmemeli: iddiaların dayanağı ve görsellerin lisansı eksik."
        )

    satirlar += ["", f"Kaynak: `ytoto trend aktar --kaynak wikipedia` · Wikidata `{kayit.qid}`"]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": satir[:BASLIK_SINIRI]}}]},
        }
        for satir in satirlar
        if satir
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
) -> AktarimSonucu:
    """Wikipedia adaylarını kaynak dosyalarıyla birlikte Notion'a yazar."""
    an = an or datetime.now(UTC)
    sonuc = AktarimSonucu()
    gun = an.date().isoformat()

    for kayit in adaylar:
        dosya = kaynak.dosyayi_oku(yol, kayit.qid)
        sayi = _kaynak_sayisi(dosya)
        try:
            yanit = _istek(
                "/pages",
                {
                    "parent": {"database_id": database},
                    "properties": bosluk_ozellikleri(kayit, gun=gun, kaynak_sayisi=sayi),
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
