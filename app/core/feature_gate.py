PLAN_FEATURES = {
    "admin": {
        "pipeline":            True,
        "shortlist":           True,
        "heatmap":             True,
        "knowledge_graph":     True,
        "bias_audit":          True,
        "skill_forecast":      True,
        "hr_chatbot":          True,
        "compare_candidates":  True,
        "interview_questions": True,
        "hiring_summary":      True,
        "pdf_report":          True,
        "emails":              True,
        "multi_jd":            True,
    },
    "trial": {
        "pipeline":            True,
        "shortlist":           True,
        "heatmap":             True,
        "knowledge_graph":     True,
        "bias_audit":          True,
        "skill_forecast":      True,
        "hr_chatbot":          True,
        "compare_candidates":  True,
        "interview_questions": True,
        "hiring_summary":      True,
        "pdf_report":          True,
        "emails":              True,
        "multi_jd":            True,
    },
    "six_months": {
        "pipeline":            True,
        "shortlist":           True,
        "heatmap":             True,
        "knowledge_graph":     True,
        "bias_audit":          True,
        "skill_forecast":      True,
        "hr_chatbot":          True,
        "compare_candidates":  True,
        "interview_questions": True,
        "hiring_summary":      True,
        "pdf_report":          True,
        "emails":              True,
        "multi_jd":            True,
    },
    "twelve_months": {
        "pipeline":            True,
        "shortlist":           True,
        "heatmap":             True,
        "knowledge_graph":     True,
        "bias_audit":          True,
        "skill_forecast":      True,
        "hr_chatbot":          True,
        "compare_candidates":  True,
        "interview_questions": True,
        "hiring_summary":      True,
        "pdf_report":          True,
        "emails":              True,
        "multi_jd":            True,
    },
}

def can_access(plan: str, feature: str) -> bool:
    plan_perms = PLAN_FEATURES.get(plan, PLAN_FEATURES["trial"])
    return plan_perms.get(feature, False)

def get_upgrade_message(feature: str) -> str:
    messages = {
        "hr_chatbot":          "💬 HR Chatbot costs ₹50/question. Contact TechXdigisolutions to add wallet credits.",
        "compare_candidates":  "⚖️ Candidate Comparison is available on paid plans. Contact TechXdigisolutions to upgrade.",
        "interview_questions": "🎯 Interview Questions is available on paid plans. Contact TechXdigisolutions to upgrade.",
        "hiring_summary":      "📋 Hiring Summary is available on paid plans. Contact TechXdigisolutions to upgrade.",
        "pdf_report":          "📄 PDF Reports cost ₹75 each. Contact TechXdigisolutions to add wallet credits.",
        "emails":              "📧 Email sending is available on paid plans. Contact TechXdigisolutions to upgrade.",
        "multi_jd":            "💼 Multiple JDs are available on paid plans. Contact TechXdigisolutions to upgrade.",
    }
    return messages.get(feature, "🔒 This feature requires a paid plan. Contact TechXdigisolutions.")
