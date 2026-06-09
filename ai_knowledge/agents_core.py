"""
agents_core.py - AI agent entry points.
Imports from individual agent modules and adds enhanced AI capabilities.
"""
import logging
logger = logging.getLogger(__name__)

# Import base agents from their dedicated modules
from ai_knowledge.agents.multi_agent_system import (
    MultiAgentCoordinator, get_agent_coordinator,
)
from ai_knowledge.agents.intelligent_assistant import (
    IntelligentAssistant, intelligent_assistant,
)
from ai_knowledge.agents.master_brain import (
    MasterBrain, get_master_brain, ask_azad, quick_calc, explain_concept,
)

# ============================================================================
# intelligent_response - dispatcher-aware wrapper
# ============================================================================

def intelligent_response(message: str, user_id: int = None, context: dict = None) -> str:
    """Get AI response - tries action dispatch first, then local intelligence."""
    try:
        # Seed trainer on first call
        from ai_knowledge.trainer import trainer
        trainer.seed()
    except Exception:
        pass
    try:
        from ai_knowledge.action_dispatcher import action_dispatcher
        parsed = action_dispatcher.parse_chat_action(message)
        if parsed:
            action_type, args = parsed
            if action_type in ("greeting", "help"):
                if action_type == "help":
                    return action_dispatcher.format_help()
                name = args.get("name", "")
                from datetime import datetime
                h = datetime.utcnow().hour
                greeting = "صباح الخير" if 5 <= h < 12 else "مساء الخير" if 12 <= h < 18 else "مساء النور"
                return f"{greeting} {'👤 ' + name if name else ''}! 🌟 أنا أزاد، مساعدك الذكي. اسألني عن أي شيء!\n\n{action_dispatcher.format_help()}"
            result = action_dispatcher.dispatch(action_type, args)
            if result.success:
                # Train from successful action
                try:
                    from ai_knowledge.trainer import trainer
                    trainer.learn_from_interaction(message, result.message, user_id, success=True)
                except Exception:
                    pass
                return result.message
            if result.needs_permission:
                return f"⚠️ {result.message}\n\nيمكنك سؤالي عن معلومات النظام بدلاً من ذلك."
            return result.message

        # Fallback to local intelligence
        result = intelligent_assistant.process(message, user_id, context)
        response = result.get('response', 'عذراً، حدث خطأ')
        return response
    except Exception as e:
        try:
            from ai_knowledge.action_dispatcher import _log_ai_error
            _log_ai_error("intelligent_response_error", str(e), request_data={"message": message[:200]})
        except Exception:
            pass
        return f"عذراً، حدث خطأ أثناء المعالجة. يرجى المحاولة مرة أخرى."

# ============================================================================
# ENHANCED AI - System Knowledge + Groq Chain-of-Thought + Tool-Use
# ============================================================================

_llm_available = None


def _check_llm_availability() -> bool:
    """Check if any LLM provider (Groq/Gemini/OpenAI) is configured."""
    global _llm_available
    if _llm_available is not None:
        return _llm_available
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass
    _llm_available = bool(os.environ.get('GROQ_API_KEY') or
                          os.environ.get('GEMINI_API_KEY') or
                          os.environ.get('OPENAI_API_KEY'))
    return _llm_available


def _get_llm_response(system_prompt: str, user_message: str) -> str | None:
    """Send a message to the LLM provider and return the response."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key:
        try:
            import requests
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    gemini_key = os.environ.get('GEMINI_API_KEY')
    if gemini_key:
        try:
            import requests
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gemini_key}",
                json={"contents": [{"parts": [{"text": system_prompt + "\n\n" + user_message}]}]},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except Exception:
            pass

    return None


def _build_system_prompt(question: str, user_role: str = "user") -> str:
    """Build a system prompt with system knowledge context for the LLM."""
    from ai_knowledge.system_knowledge import search_knowledge, SYSTEM_INFO

    results = search_knowledge(question)
    context_parts = [f"أنت أزاد، المساعد الذكي لنظام {SYSTEM_INFO['name_ar']} (v{SYSTEM_INFO['version']})."]

    if results:
        context_parts.append("\nالمعرفة المتعلقة بالسؤال:")
        for r in results[:5]:
            if r["type"] == "model":
                context_parts.append(f"- المودل {r['name']}: جدول {r['info']['table']}")
            elif r["type"] == "permission":
                context_parts.append(f"- صلاحية {r['code']}: {r['info']['name_ar']}")
            elif r["type"] == "feature":
                context_parts.append(f"- ميزة {r['name']}: {r['info']['name_ar']}")

    from ai_knowledge.system_knowledge import ROLES
    role_info = None
    for r in ROLES:
        if r["slug"] == user_role:
            role_info = r
            break
    if role_info:
        context_parts.append(f"\nدور المستخدم: {role_info['name_ar']}")

    context_parts.append("""
تعليمات:
1. أجب باللغة العربية الفصحى أو العامية حسب سياق السؤال
2. إذا كان السؤال عن عملية في النظام، اشرح الخطوات بالتفصيل
3. إذا كان السؤال محاسبيًا، استخدم المصطلحات المحاسبية الصحيحة
4. إذا كان السؤال عن صلاحيات، اذكر الصلاحية المطلوبة
5. كن دقيقًا ومختصرًا (لا تزيد عن 3 فقرات)
6. إذا لم تعرف الإجابة، قل بصراحة "لا أعرف" بدلاً من التخمين
    """)

    return "\n".join(context_parts)


def ask_azad_enhanced(question: str, context: dict = None, user_id: int = None) -> dict:
    """
    Enhanced ask_azad with LLM chain-of-thought and system knowledge.
    Uses Groq/Gemini for complex questions, falls back to local MasterBrain.
    """
    result = {
        "answer": "",
        "source": "local",
        "confidence": 0.5,
        "thinking_steps": [],
    }

    role = context.get("role", "user") if context else "user"

    # Step 1: Check system knowledge first
    try:
        from ai_knowledge.system_knowledge import search_knowledge, FAQ
        q_lower = question.lower()
        for role_key, faqs in FAQ.items():
            for faq in faqs:
                if any(word in q_lower for word in faq["q"].split() if len(word) > 2):
                    result["answer"] = faq["a"]
                    result["source"] = "faq"
                    result["confidence"] = 0.9
                    result["thinking_steps"].append("Matched FAQ entry")
                    return result

        knowledge = search_knowledge(q_lower)
        if knowledge:
            result["thinking_steps"].append(f"Found {len(knowledge)} knowledge results")
            for k in knowledge[:3]:
                if k["type"] == "model":
                    info = k["info"]
                    fields = "\n".join(f"  - {f}: {t}" for f, t in list(info.get("fields", {}).items())[:10])
                    result["answer"] += f"**مودل {k['name']}** (جدول {info['table']}):\n{fields}\n\n"
                    result["source"] = "system_knowledge"
                    result["confidence"] = 0.85
                elif k["type"] == "permission":
                    info = k["info"]
                    result["answer"] += f"**صلاحية {k['code']}**: {info['name_ar']} ({info['name']})\n"
                    result["source"] = "system_knowledge"
                    result["confidence"] = 0.85
                elif k["type"] == "feature":
                    info = k["info"]
                    result["answer"] += f"**ميزة {k['name']}**: {info['name_ar']}\n  {info['description']}\n"
                    result["source"] = "system_knowledge"
                    result["confidence"] = 0.9
    except Exception:
        pass

    # Step 2: If no system knowledge answer, try LLM
    if not result["answer"] and _check_llm_availability():
        try:
            system_prompt = _build_system_prompt(question, role)
            llm_response = _get_llm_response(system_prompt, question)
            if llm_response:
                result["answer"] = llm_response
                result["source"] = "llm"
                result["confidence"] = 0.9
                result["thinking_steps"].append("Used LLM chain-of-thought")
        except Exception as e:
            result["thinking_steps"].append(f"LLM error: {str(e)[:100]}")

    # Step 3: Fallback to MasterBrain
    if not result["answer"]:
        try:
            brain = get_master_brain()
            brain_result = brain.ask(question, context, user_id)
            result["answer"] = brain_result.get("answer", "")
            result["source"] = "master_brain"
            result["confidence"] = 0.6
            result["thinking_steps"].append("Fell back to MasterBrain")
        except Exception as e:
            result["answer"] = "عذراً، حدث خطأ في معالجة سؤالك. يرجى المحاولة مرة أخرى."
            result["thinking_steps"].append(f"Error: {str(e)[:100]}")

    # Step 4: Learn from interaction
    try:
        from ai_knowledge.trainer import trainer
        trainer.learn_from_interaction(question, result["answer"], user_id, success=(result["source"] != "error"))
    except Exception:
        pass

    return result
