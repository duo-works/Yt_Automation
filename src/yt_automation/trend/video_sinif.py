"""Videoların ücretsiz sınıflandırması — kategori ve konu etiketleri.

DW-30 "kategori → konu → LLM" diye kademeli bir sınıflandırıcı tarif ediyordu.
LLM kademesi Wikipedia makaleleri için yazıldı (`siniflandirici.py`); bu dosya
**videolar** için ilk iki kademeyi yapıyor. `video.sinif` sütunu o güne kadar
hiç dolmamıştı ve Notion aktarımı (DW-31) ona bakıyor.

Hiç çağrı yapmıyor: iki sinyal de toplama sırasında zaten çekiliyor.

## LLM kademesi videolar için bilinçli olarak YOK

Aşağıdaki ölçüm sebebini gösteriyor. 4.905 çart videosunda `topicCategories`
dağılımı (2026-07-30):

    1233  Music              364  Hip_hop_music
    1164  Video_game_culture 353  Lifestyle
    1070  Technology         291  Entertainment
     740  Pop_music          270  Film
     ...
      19  Knowledge      ← nişimize en yakın etiket

**Tarih ya da bilim etiketi hiç yok.** En yakını "Knowledge" ve o da 4.905'te
19 (%0,4). Bu videoların her birine LLM sorgusu göndermek, %99,6'sı için
"diger" cevabını satın almak olurdu.

Bu, DW-28'in bulgusunun üçüncü kez doğrulanması: çart bu iş için kaynak değil.
Aday üretimi Wikipedia'da (DW-34), çart yalnızca ikincil bir sinyal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import depo

# YouTube kategorileri. 27 = Eğitim, 28 = Bilim & Teknoloji.
#
# ⚠️ Kategori tek başına zayıf bir sinyal ve bunu ölçtük: DW-28'in canlı
# taramasında "Bilim & Teknoloji" listesinin en çok izlenen on iki videosunun
# on ikisi telefon incelemesiydi. O yüzden kategori yalnızca konu etiketi
# yokken ve sonuç `belirsiz` olarak kullanılıyor — "bilim" olarak değil.
EGITIM_KATEGORISI = 27
BILIM_TEKNOLOJI_KATEGORISI = 28

# `topicDetails.topicCategories` Wikipedia URL'leri döndürüyor; son parça
# alınıyor. Bunlar Google'ın Knowledge Graph eşlemesi, bizim tahminimiz değil.
TARIH_ETIKETLERI = frozenset({"History", "Military_history", "Archaeology"})
BILIM_ETIKETLERI = frozenset(
    {
        "Science",
        "Knowledge",
        "Physics",
        "Biology",
        "Chemistry",
        "Astronomy",
        "Medicine",
        "Mathematics",
        "Engineering",
    }
)

# Bu etiketlerden biri varsa video kesin `diger` — tarih/bilim etiketi de
# taşısa. Sebep: bir müzik videosunun "Knowledge" etiketi taşıması onu bilim
# içeriği yapmıyor, Knowledge Graph'ın geniş eşlemesini gösteriyor.
DISLAYAN_ETIKETLER = frozenset(
    {
        "Music",
        "Pop_music",
        "Hip_hop_music",
        "Electronic_music",
        "Rock_music",
        "Reggae",
        "Christian_music",
        "Independent_music",
        "Rhythm_and_blues",
        "Music_of_Asia",
        "Music_of_Latin_America",
        "Video_game_culture",
        "Action-adventure_game",
        "Role-playing_video_game",
        "Action_game",
        "Simulation_video_game",
        "Sports_game",
        "Strategy_video_game",
        "Casual_game",
        "Racing_video_game",
        "Sport",
        "Film",
        "Television_program",
        "Entertainment",
        "Lifestyle_(sociology)",
        "Fashion",
        "Politics",
    }
)

KAYNAK = "konu"


def etiketleri_ayikla(konu_etiketleri: str | None) -> set[str]:
    """JSON dizideki Wikipedia URL'lerinden son parçaları çıkarır."""
    if not konu_etiketleri:
        return set()
    try:
        urller = json.loads(konu_etiketleri)
    except (TypeError, ValueError):
        return set()
    return {str(u).rstrip("/").rsplit("/", 1)[-1] for u in urller if u}


def siniflandir(kategori_id: int | None, konu_etiketleri: str | None) -> str:
    """Bir videonun sınıfı: `tarih` | `bilim` | `belirsiz` | `diger`.

    Sıra önemli ve dışlama **önce** geliyor — `konu.siniflandir()` ile aynı
    desen. Bir "Knowledge" etiketi taşıyan pop şarkısı bilim değil.
    """
    etiketler = etiketleri_ayikla(konu_etiketleri)

    if etiketler & DISLAYAN_ETIKETLER:
        return "diger"
    if etiketler & TARIH_ETIKETLERI:
        return "tarih"
    if etiketler & BILIM_ETIKETLERI:
        return "bilim"
    if etiketler:
        # Etiket var ama tanımadığımız bir şey: karar vermiyoruz.
        return "belirsiz"

    # Etiket yok. Kategori tek başına "bilim" demeye yetmiyor (telefon
    # incelemeleri 28'de yaşıyor), ama ilgisiz olduğunu da söylemiyor.
    if kategori_id in (EGITIM_KATEGORISI, BILIM_TEKNOLOJI_KATEGORISI):
        return "belirsiz"
    return "diger"


@dataclass
class SiniflandirmaSonucu:
    islenen: int = 0
    siniflar: dict[str, int] = field(default_factory=dict)

    def ozet(self) -> str:
        dagilim = " · ".join(f"{k}:{v}" for k, v in sorted(self.siniflar.items()))
        return f"{self.islenen} video sınıflandırıldı · {dagilim or 'boş'}"


def uygula(yol: Path, *, yeniden: bool = False) -> SiniflandirmaSonucu:
    """`video.sinif` boş olan satırları doldurur. Kota harcamaz.

    `yeniden=True` LLM kararlarını **korur** ama kategori/konu kararlarını
    yeniden hesaplar — etiket kümesi genişletildiğinde gereken şey bu.
    """
    sonuc = SiniflandirmaSonucu()
    kosul = "WHERE sinif IS NULL OR sinif_kaynagi != 'llm'" if yeniden else "WHERE sinif IS NULL"

    with depo.yazma_islemi(yol) as baglanti:
        satirlar = baglanti.execute(
            f"SELECT video_id, kategori_id, konu_etiketleri FROM video {kosul}"
        ).fetchall()
        for satir in satirlar:
            sinif = siniflandir(satir["kategori_id"], satir["konu_etiketleri"])
            baglanti.execute(
                "UPDATE video SET sinif = ?, sinif_kaynagi = ? WHERE video_id = ?",
                (sinif, KAYNAK, satir["video_id"]),
            )
            sonuc.islenen += 1
            sonuc.siniflar[sinif] = sonuc.siniflar.get(sinif, 0) + 1
    return sonuc
