import re

AR_TO_EN = {
    "هيلثي": "healthy",
    "هيلث": "health",
    "داش": "dashboard",
    "بورد": "dashboard",
    "داشبورد": "dashboard",
    "صحة": "health",
    "صفحه": "page",
    "صفحة": "page",
    "الصفحة": "page",
    "الصفحه": "page",
    "مشروع": "project",
    "تطبيق": "app",
    "نظام": "system",
    "ملف": "file",
    "موديول": "module",
    "قالب": "template",
    "الصحة": "health",
    "الرئيسية": "main",
    "رئيسي": "main",
    "هوم": "home",
    "home": "home",
    "page": "page",
    "dashboard": "dashboard",
}

ARABIC_CREATE = ("أنشئ", "أنشاء", "إنشاء", "انشاء", "انشئ", "صنع", "عمل",
                 "صمم", "تصميم", "اعمل", "أعمل", "كوّن", "كون", "ابنِ", "ابني")
ARABIC_MODIFY = ("عدل", "تعديل", "طور", "تطوير", "حسن", "تحسين", "بدل", "تغيير")
ARABIC_FIX = ("اصلح", "أصلح", "صلح", "تصليح", "إصلاح")
ARABIC_SCAN = ("افحص", "فحص", "حلل", "تحليل", "مسح", "راجع")
ARABIC_PAGE = ("صفحة", "صفحه", "الصفحة", "الصفحه")
ARABIC_PROJECT = ("مشروع", "تطبيق", "نظام")

ENGLISH_CREATE = ("create", "build", "make", "new", "design", "generate", "construct", "develop", "write")
ENGLISH_MODIFY = ("modify", "update", "change", "edit", "improve", "upgrade", "add", "refactor")
ENGLISH_FIX = ("fix", "repair", "correct", "bug", "issue", "patch", "resolve")
ENGLISH_SCAN = ("scan", "search", "check", "review", "audit", "analyze", "inspect", "report")

SKIP_WORDS = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
              "is", "are", "was", "were", "be", "been", "being", "have", "has",
              "had", "do", "does", "did", "will", "would", "could", "should",
              "may", "might", "can", "shall", "لا", "في", "من", "الى", "على",
              "مع", "عن", "و", "او", "او", "ثم", "كان", "ليس", "هذا", "هذه",
              "ذلك", "تلك", "ان", "إن", "قد"}


def normalize_text(text):
    if not text:
        return ""
    t = text.lower().strip()
    for ar, en in AR_TO_EN.items():
        t = t.replace(ar, en)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def has_arabic(text):
    return bool(re.search(r'[\u0600-\u06FF]', text))


def extract_page_name(text):
    words = text.lower().split()
    meaningful = [w for w in words if w not in SKIP_WORDS and len(w) > 1]
    create_words = set(ARABIC_CREATE + ENGLISH_CREATE)
    mod_words = set(ARABIC_MODIFY + ENGLISH_MODIFY)
    fix_words = set(ARABIC_FIX + ENGLISH_FIX)
    scan_words = set(ARABIC_SCAN + ENGLISH_SCAN)
    skip = create_words | mod_words | fix_words | scan_words
    meaningful = [w for w in meaningful if w not in skip]
    return "_".join(meaningful) if meaningful else "page"


def detect_task_type(text):
    lowered = normalize_text(text)
    if has_arabic(text):
        lowered_ar = text.lower()
    else:
        lowered_ar = lowered

    is_create = any(w in lowered_ar for w in ARABIC_CREATE) or any(w in lowered for w in ENGLISH_CREATE)
    is_modify = any(w in lowered_ar for w in ARABIC_MODIFY) or any(w in lowered for w in ENGLISH_MODIFY)
    is_fix = any(w in lowered_ar for w in ARABIC_FIX) or any(w in lowered for w in ENGLISH_FIX)
    is_scan = any(w in lowered_ar for w in ARABIC_SCAN) or any(w in lowered for w in ENGLISH_SCAN)
    is_page = any(w in lowered_ar for w in ARABIC_PAGE) or "page" in lowered or "html" in lowered
    is_project = any(w in lowered_ar for w in ARABIC_PROJECT) or "project" in lowered or "app" in lowered

    if is_scan and ("jarvis" in lowered or "جارفيس" in lowered_ar or "جارس" in lowered_ar or "report" in lowered or "تقرير" in lowered_ar):
        return "engineering_scan_report"
    if is_create and is_project:
        return "engineering_create_project"
    if is_create and is_page:
        return "engineering_create_file"
    if is_create:
        return "engineering_create_project"
    if is_modify:
        return "engineering_modify_existing"
    if is_fix:
        return "engineering_fix"
    if is_scan:
        return "engineering_scan_report"
    if "refactor" in lowered or "هيكلة" in lowered_ar or "تنظيف" in lowered_ar:
        return "engineering_refactor"
    if "rollback" in lowered or "تراجع" in lowered_ar or "رجوع" in lowered_ar:
        return "rollback_action"
    if "status" in lowered or "حالة" in lowered_ar:
        return "status_report"
    if "voice" in lowered or "صوت" in lowered_ar:
        return "voice_action"
    if any(w in lowered for w in ("scan", "search", "check", "review")):
        return "engineering_scan_report"
    if any(w in lowered for w in ("hello", "hi", "مرحبا", "اهلا", "السلام")):
        return "status_report"
    return "opencode_engineering"
