"""Wikipedia okunma verisi — dil bazında aday üretimi.

Neden YouTube trend çartı değil de burası: DW-28'in canlı taraması çartın bu
iş için kullanılamaz olduğunu gösterdi. "Bilim & Teknoloji" listesinde en çok
izlenen on iki videonun on ikisi telefon incelemesiydi, "Eğitim" kategorisinin
`mostPopular` çartı **hiç yok** (111 bölgede de HTTP 404), ve çart ortalama
6,7 gün gecikmeli çalışıyor.

Wikipedia üçünü de çözüyor: dil bazında günlük ilk 1000 makale, makale bazında
zaman serisi, gerçek kategori yapısı. Üstelik **öncü** gösterge — insanlar bir
konuyu YouTube'da aramadan önce burada okuyor.

Maliyet sıfır: bu API kotasız ve anahtarsız. Karşılığında Wikimedia tanımlayıcı
bir `User-Agent` istiyor (politika gereği), onu gönderiyoruz.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

TABAN = "https://wikimedia.org/api/rest_v1/metrics/pageviews"

# Wikimedia politikası tanımlayıcı bir User-Agent şart koşuyor; anonim
# istekler kısıtlanabiliyor. Sürüm ve iletişim bilgisi içermesi bekleniyor.
KULLANICI_AJANI = "duo-works-yt-automation/0.1 (https://github.com/duo-works/Yt_Automation)"

# Liste tepesindeki yapısal gürültü. Bunlar makale değil; ad alanı önekleri
# dile göre değiştiği için ayrıca `:` içeren başlıklar da eleniyor.
ELENEN_BASLIKLAR = frozenset(
    {"Main_Page", "Ana_Sayfa", "Anasayfa", "Hauptseite", "Portada", "-", "Special:Search"}
)

VARSAYILAN_DILLER = ("tr", "en", "de", "es", "ar", "hi")


class WikipediaHatasi(RuntimeError):
    """Wikimedia API'sinden veri alınamadı."""


@dataclass(frozen=True)
class Okunma:
    dil: str
    baslik: str
    gun: str
    okunma: int
    sira: int | None = None


def _cek(url: str) -> dict:
    istek = urllib.request.Request(url, headers={"User-Agent": KULLANICI_AJANI})
    try:
        with urllib.request.urlopen(istek, timeout=30) as yanit:
            return json.load(yanit)
    except urllib.error.HTTPError as hata:
        if hata.code == 404:
            # Wikimedia henüz o günü yayımlamamış olabilir — veri yokluğu,
            # arıza değil. Çağıran boş listeyi normal karşılamalı.
            raise WikipediaHatasi(f"veri yok (HTTP 404): {url}") from None
        raise WikipediaHatasi(f"HTTP {hata.code}: {url}") from None
    except OSError as hata:
        raise WikipediaHatasi(f"bağlantı hatası: {hata}") from None


def _makale_mi(baslik: str) -> bool:
    """Ad alanı sayfalarını ve ana sayfayı eler.

    `Özel:Ara`, `Special:Search`, `Kategori:...` gibi başlıklar listede
    üst sıralarda çıkıyor ama makale değiller. Ad alanı öneki her dilde
    farklı olduğu için isim listesi yerine iki nokta üst üste aranıyor.
    """
    return baslik not in ELENEN_BASLIKLAR and ":" not in baslik


def gunluk_liste(dil: str, gun: date, *, adet: int = 200) -> list[Okunma]:
    """Bir dilin bir gündeki en çok okunan makaleleri.

    `adet` bilerek 1000'in altında: liste kuyruğu uzun ve seyrek, ilk birkaç
    yüz dışında sinyal yok. Daha azını almak sonraki adımların (Wikidata
    sorguları) maliyetini doğrudan düşürüyor.
    """
    url = f"{TABAN}/top/{dil}.wikipedia/all-access/{gun.year}/{gun.month:02d}/{gun.day:02d}"
    veri = _cek(url)
    ogeler = veri.get("items", [{}])[0].get("articles", [])
    sonuc: list[Okunma] = []
    for oge in ogeler:
        baslik = oge.get("article", "")
        if not _makale_mi(baslik):
            continue
        sonuc.append(
            Okunma(
                dil=dil,
                baslik=baslik,
                gun=gun.isoformat(),
                okunma=int(oge.get("views", 0)),
                sira=int(oge.get("rank", 0)) or None,
            )
        )
        if len(sonuc) >= adet:
            break
    return sonuc


def makale_serisi(dil: str, baslik: str, bas: date, son: date) -> list[Okunma]:
    """Tek bir makalenin günlük okunma serisi.

    `user` erişim türü seçili: bot ve tarayıcı ön yüklemeleri hariç. Ham
    `all-agents` sayısı bot trafiğiyle şişiyor ve sıçramaları taklit ediyor.
    """
    url = (
        f"{TABAN}/per-article/{dil}.wikipedia/all-access/user/"
        f"{urllib.parse.quote(baslik, safe='')}/daily/"
        f"{bas.strftime('%Y%m%d')}/{son.strftime('%Y%m%d')}"
    )
    try:
        veri = _cek(url)
    except WikipediaHatasi:
        return []  # Hiç okunmamış makale 404 döner — sıfır seri demektir.
    return [
        Okunma(
            dil=dil,
            baslik=baslik,
            gun=f"{o['timestamp'][:4]}-{o['timestamp'][4:6]}-{o['timestamp'][6:8]}",
            okunma=int(o.get("views", 0)),
        )
        for o in veri.get("items", [])
    ]


def ozetleri_getir(dil: str, basliklar: list[str]) -> dict[str, str]:
    """Makale başlığı → giriş paragrafı. Toplu, 20'lik gruplar.

    Sınıflandırma için başlık tek başına yetmiyor: "Homer" antik Yunan şairi
    de olabilir Simpson da, "Paul Newman" ismi mesleğini söylemiyor. Giriş
    paragrafı ikisini de tek cümlede çözüyor ve **ücretsiz** — LLM'e giden
    isteme bu bağlamı eklemek, doğruluğu kayda değer artırıyor.
    """
    ozetler: dict[str, str] = {}
    for i in range(0, len(basliklar), 20):  # `exlimit` üst sınırı 20
        grup = basliklar[i : i + 20]
        url = (
            f"https://{dil}.wikipedia.org/w/api.php?action=query&prop=extracts"
            f"&exintro=1&explaintext=1&exlimit=20&format=json&redirects=1&titles="
            + urllib.parse.quote("|".join(grup), safe="|")
        )
        try:
            veri = _cek(url).get("query", {})
        except WikipediaHatasi:
            continue  # Özet olmadan da sınıflandırılabilir, sadece daha zor.

        takma: dict[str, str] = {}
        for anahtar in ("normalized", "redirects"):
            for kayit in veri.get(anahtar, []):
                takma[kayit["to"]] = takma.get(kayit["from"], kayit["from"])

        for sayfa in veri.get("pages", {}).values():
            if metin := (sayfa.get("extract") or "").strip():
                baslik = sayfa.get("title", "")
                ozetler[takma.get(baslik, baslik)] = metin
    return ozetler


def son_yayimlanan_gun(bugun: date | None = None) -> date:
    """Verisi hazır olması beklenen en son gün.

    Wikimedia günlük toplamı ertesi gün yayımlıyor ve gecikme olabiliyor;
    iki gün geriden başlamak boşuna 404 almayı önlüyor.
    """
    return (bugun or date.today()) - timedelta(days=2)
