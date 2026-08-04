"""Trend tespiti — tarih ve bilim alanında ülke/dil bazlı yükselen içerik.

Yükleme hattından ayrı bir iş kolu ama **aynı kota bütçesini** paylaşıyor:
`kota.KaliciSayac` ile muhasebe ortak, `depo.py` ile depo ortak.

PRD'nin *"SEO araştırması kapsamda değil"* maddesiyle çelişmiyor. O maddenin
gerekçesi fiyattı — `search.list` 100 birim. Buradaki yol `videos.list` +
`chart=mostPopular`: **1 birim**, çağrı başına 50 video. Ayrıca amaç sıralama
oyunu değil, faz 2'nin kaynak katmanı (PRD → dört karşı önlemin birincisi:
*"her videonun altında gerçek bir kaynak"*).
"""
