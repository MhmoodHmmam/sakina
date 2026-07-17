"""UI and trace localization — English and Arabic.

This module only translates text SAKINA itself generates: trace labels,
static UI chrome, and enum-like display values (confidence, severity,
allow/refuse, congestion trend). It never touches the model's own free-text
reasoning — that is localized separately, at generation time, via the
Arabic directive brain.py appends to its prompts when language="ar". Two
different problems: this is deterministic lookup (same spirit as
signals.py); that is asking the model to think in a different language.

Evidence text built for the model (signals.py's ZoneEvidence.render(), the
DECIDE node's prompt blocks in agent.py) is deliberately NOT translated here
— it is model input, not something a human reads directly, and translating
it would mean maintaining two evidence-formatting code paths for no benefit.
"""
from __future__ import annotations

Language = str  # "en" | "ar"

_STRINGS: dict[str, dict[str, str]] = {
    # -- phases --
    "phase.perceive": {"en": "PERCEIVE", "ar": "الإدراك"},
    "phase.perceive.detail": {"en": "Gathering network signals across {zone}",
                              "ar": "جمع إشارات الشبكة عبر {zone}"},
    "phase.assess": {"en": "ASSESS", "ar": "التقييم"},
    "phase.assess.detail": {"en": "Weighing evidence — is this crowd or is this noise?",
                             "ar": "وزن الأدلة — هل هذا ازدحام حقيقي أم مجرد تشويش؟"},
    "phase.verify": {"en": "VERIFY", "ar": "التحقق"},
    "phase.verify.detail": {
        "en": "Risk is material — checking identity of {n} responder(s) before considering bandwidth elevation",
        "ar": "الخطورة كبيرة — جارٍ التحقق من هوية {n} من المستجيبين قبل النظر في رفع أولوية النطاق الترددي",
    },
    "phase.decide": {"en": "DECIDE", "ar": "القرار"},
    "phase.decide.detail": {"en": "Gating bandwidth elevation per responder",
                             "ar": "بوابة رفع النطاق الترددي لكل مستجيب"},
    "phase.act": {"en": "ACT", "ar": "التنفيذ"},
    "phase.act.detail": {"en": "Applying network changes", "ar": "تطبيق تغييرات الشبكة"},
    "phase.report": {"en": "REPORT", "ar": "التقرير"},

    # -- perceive --
    "perceive.gathered": {"en": "Signals gathered", "ar": "تم جمع الإشارات"},
    "perceive.summary": {
        "en": "{n} CAMARA calls · congestion weighted mean {wm} (naive {nm}) · telemetry confidence {trend}",
        "ar": "{n} طلبات CAMARA · متوسط الازدحام المرجَّح {wm} (المتوسط البسيط {nm}) · موثوقية القياس عن بُعد {trend}",
    },

    # -- assess --
    "assess.risk_label": {"en": "Risk {score} ({confidence} confidence) · via {model}",
                           "ar": "الخطورة {score} (موثوقية {confidence}) · عبر {model}"},
    "assess.primary_driver": {"en": "primary driver: {driver}", "ar": "العامل الرئيسي: {driver}"},
    "assess.contradictions": {"en": "contradictions: {items}", "ar": "تناقضات: {items}"},
    "assess.escalate": {"en": "Escalate to identity verification",
                         "ar": "التصعيد إلى التحقق من الهوية"},
    "assess.escalate.detail": {
        "en": "risk {score} ≥ {threshold} or model requested pre-emptive check",
        "ar": "الخطورة {score} ≥ {threshold} أو طلب النموذج فحصًا استباقيًا",
    },
    "assess.continue": {"en": "Continue monitoring", "ar": "الاستمرار في المراقبة"},
    "assess.continue.detail": {
        "en": "risk {score} below escalation floor {threshold}; spending no further API budget",
        "ar": "الخطورة {score} أقل من حد التصعيد {threshold}؛ لا حاجة لمزيد من استدعاءات API",
    },

    # -- verify --
    "verify.concerns": {"en": "{label} — {n} concern(s)", "ar": "{label} — {n} من المخاوف"},
    "verify.clean_label": {"en": "{label} — identity clean", "ar": "{label} — الهوية سليمة"},
    "verify.clean_detail": {"en": "no anomalies in network signals",
                             "ar": "لا توجد أي شذوذات في إشارات الشبكة"},
    "concern.sim_swapped_aged": {"en": "SIM was swapped {age}h ago",
                                  "ar": "تم تغيير شريحة SIM قبل {age} ساعة"},
    "concern.sim_swapped_recent": {"en": "SIM was swapped recently",
                                    "ar": "تم تغيير شريحة SIM مؤخرًا"},
    "concern.roaming": {"en": "device is roaming ({country})", "ar": "الجهاز في حالة تجوال ({country})"},
    "concern.roaming_unknown": {"en": "device is roaming (unknown network)",
                                 "ar": "الجهاز في حالة تجوال (شبكة غير معروفة)"},
    "concern.location_false": {"en": "network says device is NOT in its assigned zone",
                                "ar": "تُفيد الشبكة أن الجهاز ليس في منطقته المخصصة"},
    "concern.location_unknown": {"en": "network could not confirm device position",
                                  "ar": "تعذّر على الشبكة تأكيد موقع الجهاز"},

    # -- decide --
    "decide.verdict_label": {"en": "{name} → {verdict} [{severity}]",
                              "ar": "{name} ← {verdict} [{severity}]"},
    "decide.proceed": {"en": "Proceed to elevation", "ar": "المتابعة إلى الرفع"},
    "decide.proceed.detail": {"en": "risk {score} ≥ {threshold} and {n} responder(s) cleared",
                               "ar": "الخطورة {score} ≥ {threshold} وتمت الموافقة على {n} من المستجيبين"},
    "decide.hold": {"en": "Hold — no elevation", "ar": "التوقف — لا رفع"},
    "decide.hold_low_risk": {"en": "risk {score} below action floor {threshold}",
                              "ar": "الخطورة {score} أقل من حد التنفيذ {threshold}"},
    "decide.hold_none_cleared": {"en": "no responder cleared the identity gate",
                                  "ar": "لم يجتز أي مستجيب بوابة التحقق من الهوية"},

    # -- act --
    "act.qod_session": {"en": "QoD session for {label}", "ar": "جلسة QoD لـ {label}"},
    "act.qod_detail": {"en": "profile {profile} · status {status} · id {sid}",
                        "ar": "الملف الشخصي {profile} · الحالة {status} · المعرّف {sid}"},
    "act.none_applied": {"en": "No elevations applied", "ar": "لم يتم تطبيق أي رفع"},
    "act.none_applied_detail": {"en": "every candidate was refused or none qualified",
                                 "ar": "تم رفض جميع المرشحين أو لم يتأهل أي منهم"},

    # -- report --
    "report.summary": {
        "en": "Cycle complete · {total} CAMARA calls ({live} live, {cached} cached) across {n} APIs · {ms}ms · next poll in {s}s",
        "ar": "اكتملت الدورة · {total} طلبات CAMARA ({live} حي، {cached} مخزَّن) عبر {n} واجهات · {ms} م.ث · الاستطلاع التالي خلال {s} ثانية",
    },

    # -- CAMARA call labels (camara.py) --
    "api.congestion": {"en": "Congestion · {label}", "ar": "الازدحام · {label}"},
    "api.locate": {"en": "Locate · {label}", "ar": "تحديد الموقع · {label}"},
    "api.verify": {"en": "Verify {label} in {zone}", "ar": "التحقق من {label} في {zone}"},
    "api.reachability": {"en": "Reachability · {label}", "ar": "إمكانية الوصول · {label}"},
    "api.roaming": {"en": "Roaming · {label}", "ar": "التجوال · {label}"},
    "api.simswap_check": {"en": "SIM swap check · {label}", "ar": "فحص تبديل الشريحة · {label}"},
    "api.simswap_date": {"en": "SIM swap date · {label}", "ar": "تاريخ تبديل الشريحة · {label}"},
    "api.qod_elevate": {"en": "QoD elevate · {label}", "ar": "رفع جودة الخدمة · {label}"},
    "api.geofences": {"en": "Geofence subscriptions", "ar": "اشتراكات السياج الجغرافي"},
    "api.watch_zone": {"en": "Watch {zone} · {label}", "ar": "مراقبة {zone} · {label}"},
    "api.qod_release_replay": {"en": "QoD release (replay)", "ar": "تحرير جلسة QoD (إعادة تشغيل)"},
    "api.qod_released": {"en": "QoD released", "ar": "تم تحرير جلسة QoD"},
    "api.qod_release_failed": {"en": "QoD release failed", "ar": "فشل تحرير جلسة QoD"},
    "api.replay_detail": {"en": "replay mode — recorded response", "ar": "وضع إعادة التشغيل — استجابة مسجَّلة"},
    "api.fallback_detail": {"en": "fallback after live failure", "ar": "احتياطي بعد فشل الاتصال الحي"},
    "api.call_failed": {"en": "{api} failed", "ar": "فشل {api}"},
    "api.call_unavailable": {"en": "{api} unavailable", "ar": "{api} غير متاح"},
    "api.degrade_detail": {"en": "{err} — serving recorded response", "ar": "{err} — تقديم استجابة مسجَّلة"},

    # -- multi-zone scheduler (app.py) --
    "scheduler.chosen": {"en": "Multi-zone scheduler → {zone}", "ar": "جدولة المناطق المتعددة ← {zone}"},
    "scheduler.never_polled": {
        "en": "never polled — establishing a baseline reading (criticality {crit}/5)",
        "ar": "لم يُستطلع من قبل — إنشاء قراءة أساسية (الأهمية الحرجة {crit}/5)",
    },
    "scheduler.overdue": {
        "en": "{elapsed:.0f}s since last poll (recommended {next_s}s), last risk {risk:.2f}, criticality {crit}/5",
        "ar": "{elapsed:.0f} ثانية منذ آخر استطلاع (الموصى به {next_s} ثانية)، آخر خطورة {risk:.2f}، الأهمية الحرجة {crit}/5",
    },
}

# Enum-like display values — deliberately NOT left to the model's discretion.
# brain.py instructs the model to keep confidence/severity as fixed English
# tokens precisely so this lookup stays reliable regardless of which
# provider (Gemini/Groq) answered.
_CONFIDENCE = {"low": {"en": "low", "ar": "منخفضة"},
               "medium": {"en": "medium", "ar": "متوسطة"},
               "high": {"en": "high", "ar": "عالية"}}
_SEVERITY = {"clear": {"en": "clear", "ar": "واضح"},
             "caution": {"en": "caution", "ar": "تحذير"},
             "block": {"en": "block", "ar": "حظر"}}
_TREND = {"improving": {"en": "improving", "ar": "في تحسّن"},
          "degrading": {"en": "degrading", "ar": "في تدهور"},
          "stable": {"en": "stable", "ar": "مستقرة"},
          "unknown": {"en": "unknown", "ar": "غير معروفة"}}
_VERDICT = {True: {"en": "ALLOW", "ar": "سماح"}, False: {"en": "REFUSE", "ar": "رفض"}}


def t(key: str, lang: Language = "en", **kwargs) -> str:
    """Look up and format a trace/UI string. Falls back to English, then the
    key itself, if a translation is missing — never raises on a typo."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    template = entry.get(lang, entry.get("en", key))
    return template.format(**kwargs) if kwargs else template


def confidence_label(value: str, lang: Language = "en") -> str:
    return _CONFIDENCE.get(value, {}).get(lang, value)


def severity_label(value: str, lang: Language = "en") -> str:
    return _SEVERITY.get(value, {}).get(lang, value)


def trend_label(value: str, lang: Language = "en") -> str:
    return _TREND.get(value, {}).get(lang, value)


def verdict_label(allow: bool, lang: Language = "en") -> str:
    return _VERDICT.get(bool(allow), {}).get(lang, "ALLOW" if allow else "REFUSE")
