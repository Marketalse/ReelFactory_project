#!/usr/bin/env python3
"""Maintainer tool (T147): download a starter icon set (Lucide, ISC licence: free for commercial use) into library/broll/ as icon-<name>.svg,
paint them in the brand accent colour, write Arabic tags to library/broll/tags.json, and run the safe-zone asset check on each.
Run once:  python3 scripts/fetch_icons.py      (needs internet; icons are then committed, so reels never need the internet)."""
import json, os, re, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import asset_check as ac, config as cfg          # noqa: E402

VER = "0.468.0"
URL = "https://cdn.jsdelivr.net/npm/lucide-static@%s/icons/%s.svg" % (VER, "%s")
# icon: Arabic words people say (Iraqi marketing / online shop / delivery talk)
ICONS = {
    "truck": ["شاحنة", "توصيل", "شحن", "سيارة"], "package": ["طرد", "شحنة", "بضاعة", "منتج"], "ship": ["سفينة", "باخرة", "استيراد"],
    "plane": ["طيارة", "طائرة", "سفر"], "warehouse": ["مخزن", "مستودع"], "store": ["محل", "متجر", "دكان", "ستور"],
    "shopping-cart": ["سلة", "سلّة", "شراء"], "shopping-bag": ["تسوق", "مشتريات"], "credit-card": ["دفع", "بطاقة", "كارت"],
    "banknote": ["فلوس", "مبلغ", "نقد", "كاش"], "wallet": ["محفظة"], "dollar-sign": ["دولار", "ربح"], "coins": ["عملات", "فلوس", "تكلفة"],
    "trending-up": ["نمو", "ارتفاع", "زيادة", "مبيعات"], "trending-down": ["هبوط", "نزول", "خسارة", "خسران"], "chart-bar": ["احصائيات", "ارقام", "تقرير"],
    "chart-pie": ["نسبة", "حصة"], "target": ["هدف", "استهداف", "جمهور"], "users": ["زبائن", "عملاء", "جمهور", "فريق"], "user": ["شخص", "عميل", "زبون"],
    "handshake": ["اتفاق", "شراكة", "صفقة"], "megaphone": ["اعلان", "حملة", "تسويق"], "mail": ["ايميل", "رسالة", "بريد"], "phone": ["تلفون", "اتصال", "موبايل"],
    "message-circle": ["رسالة", "دردشة", "تعليق"], "message-square": ["محادثة", "ردود"], "heart": ["اعجاب", "لايك", "حب"], "thumbs-up": ["لايك"],
    "star": ["نجمة", "تقييم", "مميز"], "share-2": ["مشاركة", "شير"], "eye": ["مشاهدات", "مشاهدة"], "play": ["فيديو", "تشغيل"], "camera": ["كاميرا", "تصوير"],
    "smartphone": ["موبايل", "تطبيق", "جوال"], "laptop": ["لابتوب", "كمبيوتر"], "globe": ["عالم", "انترنت", "عالمي"], "link": ["رابط", "لينك"],
    "search": ["بحث", "سيرش"], "lightbulb": ["فكرة", "افكار", "ابداع"], "rocket": ["انطلاق", "اطلاق"], "zap": ["سرعة"], "shield-check": ["ضمان", "حماية", "امان", "ثقة"],
    "lock": ["قفل", "حماية", "سرية"], "clock": ["ساعة", "دقيقة"], "calendar": ["تاريخ", "موعد"], "check": ["صح", "نجاح"], "x": ["خطأ", "لا", "رفض"],
    "triangle-alert": ["تحذير", "انتبه", "خطر", "مشكلة"], "circle-help": ["سؤال", "استفسار"], "settings": ["اعدادات", "ضبط"], "wrench": ["تصليح", "اصلاح", "اداة"],
    "file-text": ["ملف", "مستند", "عقد", "وثيقة"], "clipboard-list": ["قائمة", "خطوات", "خطة"], "receipt": ["فاتورة", "وصل"], "tag": ["تخفيض", "عرض"],
    "percent": ["خصم", "نسبة", "تخفيض"], "gift": ["هدية", "هدايا", "جائزة"], "award": ["جائزة", "مركز"], "crown": ["ملك", "رقم واحد"],
    "building-2": ["شركة", "مكتب", "مؤسسة"], "briefcase": ["وظيفة"], "headphones": ["دعم", "خدمة العملاء", "سماعة"], "map-pin": ["عنوان"],
    "repeat": ["تكرار"], "arrow-right": ["الخطوة"], "layers": ["مراحل", "طبقات", "مستويات"], "puzzle": ["قطعة", "تكامل"],
}


def main():
    d = os.path.join(ROOT, "library", "broll"); os.makedirs(d, exist_ok=True)
    tags_p = os.path.join(d, "tags.json")
    try: tags = json.load(open(tags_p, encoding="utf-8"))
    except (OSError, ValueError): tags = {}
    accent = cfg.BRAND["colors"]["accent"]; ok = bad = 0
    for name, ar in ICONS.items():
        try:
            svg = urllib.request.urlopen(URL % name, timeout=20).read().decode()
        except Exception as e:                                                   # noqa: BLE001
            print("skip", name, e); bad += 1; continue
        svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S).replace("currentColor", accent)
        fn = f"icon-{name}.svg"; p = os.path.join(d, fn); open(p, "w", encoding="utf-8").write(svg)
        r = ac.check(p)
        if not r["ok"]: print("FAILED the asset check:", fn, r["problems"]); os.remove(p); bad += 1; continue
        json.dump(r, open(os.path.join(d, f"icon-{name}.placement.json"), "w"), indent=1, ensure_ascii=False)
        tags[fn] = ar + [name.replace("-", " ")]; ok += 1
    json.dump(tags, open(tags_p, "w"), ensure_ascii=False, indent=1)
    open(os.path.join(d, "ICONS_LICENSE.txt"), "w").write(f"Icons icon-*.svg: Lucide {VER} (https://lucide.dev), ISC licence. Free for commercial use; keep this notice.\n")
    print(f"{ok} icons ready, {bad} skipped")


if __name__ == "__main__":
    main()
