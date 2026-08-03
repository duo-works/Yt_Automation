"""TikTok trend sinyali — ölçülmüş kısıtlar ve bugün çalışan yol.

TikTok, Shorts kanalı için en değerli sinyal kaynağı: kısa video trendleri
orada doğuyor ve YouTube Shorts'a günler sonra geliyor. Bu yüzden öncelikli
tutuldu (karar: Mirza, 2026-08-03).

## Ölçüm — 2026-08-03, ücretsiz yolların tamamı denendi

    ads.tiktok.com/creative_radar_api/.../hashtag/list
        → HTTP 200 ama gövde: {"code":40101,"msg":"no permission"}
        Tarayıcı benzeri User-Agent ve Referer ile de aynı.

    ads.tiktok.com/business/creativecenter/... (HTML)
        → 21 KB'lık **boş SPA kabuğu**; veri yok, istemci tarafında
          yukarıdaki yetkili API'den çekiliyor.

Yani anonim kazıma çalışmıyor. Çalıştırmanın üç yolu var, üçü de bu görevin
dışında bir karar gerektiriyor:

    1. Headless tarayıcı — ağır bağımlılık, TikTok'un JS imzasına bağımlı,
       her sürümde kırılabilir.
    2. TikTok Research API — resmî ve ücretsiz ama başvuru onayı gerekiyor.
    3. Üçüncü parti API (Apify, EnsembleData…) — çalışıyor, ücretli.

**Kırılgan bir kazıyıcı yazmamak bilinçli bir karar.** Çalışmayan bir kaynak,
çalıştığı sanılan bir kaynaktan iyidir: ikincisi sessizce boş döner ve
"TikTok'a da bakıyoruz" yanılsaması üretir.

## Bugün çalışan yol: elle besleme

`YT_TIKTOK_DOSYA` bir metin dosyasını gösteriyorsa (satır başına bir terim
veya hashtag), o terimler DW-55'in borusuna girer:

    terim → Wikipedia makalesi → Wikidata sınıfı → makale+okunma
          → sıçrama detektörü → sondaj + kapılar → Notion

Creative Center'ı tarayıcıda açıp ilgili hashtag'leri dosyaya yapıştırmak
30 saniye sürüyor ve sinyal gerçek. Otomatik kaynak geldiğinde `terim_getir`
yerine geçiyor; borunun geri kalanı değişmiyor.

## Yumuşak düşme

Dosya yoksa modül **sessizce atlanır** ve huni etkilenmez (ADR-0010). Bu
kaynak hiçbir koşulda ana hattı düşürmüyor.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import gtrends

DOSYA_DEGISKENI = "YT_TIKTOK_DOSYA"

# Hashtag'i terime çevirirken: "#ancientrome" → "ancient rome" olamaz (kelime
# sınırı bilgisi yok), ama "#ancient_rome" ve "#AncientRome" çevrilebilir.
# Wikipedia araması zaten sözcük sınırlarına duyarsız, o yüzden yalnızca
# ayırıcıları boşluğa çeviriyoruz — camelCase'i de bölüyoruz.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def dosya_yolu() -> Path | None:
    ham = os.environ.get(DOSYA_DEGISKENI, "").strip()
    if not ham:
        return None
    yol = Path(ham).expanduser()
    return yol if yol.is_file() else None


def terime_cevir(satir: str) -> str:
    """`#AncientRome` → `Ancient Rome`. Boş/yorum satırı için boş dize."""
    temiz = satir.strip()
    if not temiz or temiz.startswith("#") and len(temiz) == 1 or temiz.startswith("//"):
        return ""
    temiz = temiz.lstrip("#").replace("_", " ").replace("-", " ")
    return _CAMEL.sub(" ", temiz).strip()


def terimleri_oku(yol: Path | None = None) -> list[gtrends.TrendTerimi]:
    """Elle beslenen terim listesi. Dosya yoksa boş liste — hata değil."""
    yol = yol or dosya_yolu()
    if yol is None:
        return []
    terimler = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        terim = terime_cevir(satir)
        if terim:
            terimler.append(gtrends.TrendTerimi(terim=terim, geo="tiktok", trafik=""))
    return terimler


def isle(
    veri_yolu: Path,
    *,
    pazarlar: tuple[str, ...] | None = None,
    terim_getir=None,
    makale_bul=None,
) -> gtrends.IslemeSonucu:
    """TikTok terimlerini DW-55 borusuna verir.

    Kendi yazma/sınıflandırma kodunu **kopyalamıyor**: `gtrends.isle`'nin
    terim kaynağı takılabilir olduğu için aynı boru yeniden kullanılıyor.
    ADR-0010'un tarif ettiği desen budur — kaynak çoğalır, boru tektir.
    """
    terimler = terim_getir() if terim_getir else terimleri_oku()
    if not terimler:
        return gtrends.IslemeSonucu()
    return gtrends.isle(
        veri_yolu,
        pazarlar=pazarlar,
        # Coğrafya döngüsü tek bir sanal kaynağa indiriliyor: TikTok terimi
        # ülkeye değil, listenin kendisine ait.
        terim_getir=lambda geo: terimler,
        makale_bul=makale_bul,
        geo_kodlari={p: ("tiktok",) for p in (pazarlar or gtrends.bosluk.hedef_pazarlar())},
    )
