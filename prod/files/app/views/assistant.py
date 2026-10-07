import streamlit as st

from core import ui
from core.assistant import Step, ask
from core.config import LLM_ENDPOINT, current_env
from core.data import list_catalogs

SUGGESTIONS = [
    ("📈", "What was net revenue by month this year?"),
    ("🏆", "Top 5 products by net revenue, with their category"),
    ("🛡️", "Which dataset has the highest DQ failure rate, and why are records quarantined?"),
    ("🧪", "Did the latest QA run have any failures or warnings?"),
    ("🗂", "What catalogs and datasets are available in this workspace?"),
    ("💡", "Explain how net revenue is calculated in this lakehouse"),
]

TOOL_ICONS = {"run_sql": "▶", "describe_table": "🧬", "list_tables": "🗂", "recent_job_runs": "⚙️",
              "list_catalogs": "📚", "search_tables": "🔎"}


def _viewer() -> str | None:
    try:
        return st.context.headers.get("X-Forwarded-Email")
    except Exception:
        return None


def _render_steps(steps: list[Step]) -> None:
    if not steps:
        return
    queries = sum(1 for s in steps if s.tool == "run_sql")
    with st.expander(f"🔍 How I got this — {len(steps)} step(s), {queries} quer{'y' if queries == 1 else 'ies'}"):
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}. {TOOL_ICONS.get(step.tool, '•')} {ui.esc(step.summary)}**")
            if step.sql:
                st.code(step.sql, language="sql")
            if step.error:
                st.caption(f"⚠️ {step.error[:400]}")
            elif step.result is not None and not step.result.empty and step.tool != "describe_table":
                st.dataframe(step.result.head(100), hide_index=True, width="stretch")


def _history(env_key: str) -> list[dict]:
    return st.session_state.setdefault("chat", {}).setdefault(env_key, [])


def _queue(prompt: str) -> None:
    st.session_state["pending_prompt"] = prompt


def render() -> None:
    env = current_env()
    history = _history(env.key)

    ui.hero(
        "Ask AI",
        "Ask anything about your sales, customers, data quality, QA results, pipeline runs — or any "
        "other data in the workspace. Answers are computed live; every query is shown.",
        [f"Retail env · {env.key}", f"Catalogs readable · {len(list_catalogs())}", "Read-only SQL",
         f"Model · {st.session_state.get('llm_endpoint') or LLM_ENDPOINT}"],
        overline="Analyze",
    )
    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        with st.popover("Model", icon=":material/tune:", width="stretch"):
            st.text_input("Model serving endpoint", value=LLM_ENDPOINT, key="llm_endpoint",
                          help="Any chat endpoint with tool calling, e.g. a Foundation Model API endpoint.")
            st.caption("The app's service principal needs CAN QUERY on the endpoint.")
    with c2:
        if st.button("New chat", icon=":material/add_comment:", width="stretch", disabled=not history):
            history.clear()
            st.rerun()

    endpoint = st.session_state.get("llm_endpoint") or LLM_ENDPOINT

    if not history:
        viewer = _viewer()
        greeting = f"Hi {viewer.split('@')[0].split('.')[0].title()}!" if viewer else "Hi there!"
        st.markdown(f"#### 👋 {greeting} What would you like to know?")
        catalogs = list_catalogs()
        st.caption(
            f"Retail questions use `{env.catalog}` (switch environments in the sidebar). "
            f"I can also search every other catalog I can read: "
            + (", ".join(f"`{c}`" for c in catalogs[:12]) + (" …" if len(catalogs) > 12 else "") if catalogs
               else "none yet — the app needs USE CATALOG / SELECT grants.")
        )
        grid = st.columns(2)
        for i, (icon, text) in enumerate(SUGGESTIONS):
            grid[i % 2].button(f"{icon} {text}", key=f"suggest_{i}", width="stretch",
                               on_click=_queue, args=(text,))

    for message in history:
        with st.chat_message(message["role"], avatar="🧑‍💼" if message["role"] == "user" else "✨"):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_steps(message.get("steps", []))

    prompt = st.chat_input(f"Ask anything about {env.key} — e.g. “Which category had the most refunds?”")
    prompt = st.session_state.pop("pending_prompt", None) or prompt
    if not prompt:
        return

    prior = [{"role": m["role"], "content": m["content"]} for m in history]
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✨"):
        with st.status("Thinking…", expanded=False) as status:
            def on_step(step: Step) -> None:
                status.update(label=f"{TOOL_ICONS.get(step.tool, '•')} {step.summary}…")
                st.write(f"{TOOL_ICONS.get(step.tool, '•')} {step.summary}")

            try:
                answer = ask(prompt, prior, env, endpoint, on_step=on_step)
                status.update(label=f"Done · {len(answer.steps)} step(s)", state="complete")
            except Exception as exc:
                status.update(label="Something went wrong", state="error")
                history.pop()
                st.error(
                    f"Couldn't reach the model endpoint `{endpoint}`: {str(exc)[:500]}\n\n"
                    "Check that the endpoint exists, supports tool calling, and that the app can query it."
                )
                return

        st.markdown(answer.text)
        _render_steps(answer.steps)

    history.append({"role": "assistant", "content": answer.text, "steps": answer.steps})
