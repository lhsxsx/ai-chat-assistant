import os
from contextvars import ContextVar
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from embeddings import get_embeddings

load_dotenv()

# ========== 1. 向量库（和 RAG 共用） ==========
VECTOR_DB_DIR = "./chroma_db"
embeddings = get_embeddings()

# 当前请求的用户 ID（调用 Agent 前注入，供知识库工具做租户隔离）
current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def _get_user_retriever(user_id: int | None):
    """按 user_id 构建检索器，只检索该用户自己上传的文档。未登录时返回 None。"""
    if user_id is None:
        return None
    vector_store = Chroma(
        persist_directory=VECTOR_DB_DIR,
        embedding_function=embeddings
    )
    return vector_store.as_retriever(
        search_kwargs={"k": 3, "filter": {"user_id": user_id}}
    )


# ========== 2. 工具1：知识库检索 ==========
@tool("知识库检索")
def rag_tool_func(query: str) -> str:
    """从用户上传的 PDF 文档知识库中检索原文片段。
    只返回命中的文本片段与来源文件名，不做二次总结，由你自己根据片段组织答案。
    当问题明确涉及“文档内容”“上传的文件”“知识库”时，优先使用这个工具。
    输入 query 为用户原始问题或检索关键词。"""
    retriever = _get_user_retriever(current_user_id.get())
    if retriever is None:
        return "知识库尚未初始化，请先登录并通过 /upload/ 接口上传 PDF 文件后再重试。"

    try:
        docs = retriever.invoke(query)
        if not docs:
            return "知识库中未找到相关信息，建议换个关键词或上传更多相关文档后再试。"

        # 只拼接原文片段 + 文件名，不在工具内部再调用一次模型
        parts = []
        for doc in docs:
            source = os.path.basename(doc.metadata.get("source", "未知来源"))
            page = doc.metadata.get("page")
            header = f"【{source}】" if not isinstance(page, int) else f"【{source} 第{page + 1}页】"
            parts.append(f"{header}\n{doc.page_content}")
        result = "\n\n---\n\n".join(parts)
    except Exception as e:
        result = f"知识库检索失败：{e}"

    # 兜底：保证永远返回非空字符串，避免 ReAct 解析把 Observation/None 反注入下一轮
    if not result or not isinstance(result, str) or not result.strip():
        result = "知识库检索未返回有效内容。"
    return result


# ========== 3. 工具2：搜索引擎（带异常兜底，永远返回非空字符串） ==========
_raw_search = DuckDuckGoSearchRun()


@tool("搜索引擎")
def search_tool_func(query: str) -> str:
    """用于查找实时信息、新闻、天气、体育赛事结果等公开外部信息。
    当问题涉及最新动态或未知事实、且不属于文档范围时使用。
    输入 query 为精简后的搜索关键词。"""
    try:
        # 使用 .invoke 而非 .run，新版推荐路径
        raw = _raw_search.invoke(query)
        if raw is None:
            return f"搜索引擎未返回结果（关键词：{query}）。建议换个关键词再试。"
        result = str(raw)
        if not result.strip():
            return f"搜索引擎返回空内容（关键词：{query}）。建议换个关键词再试。"
        return result
    except Exception as e:
        # 包含 SSL/Mojeek/网络超时等任何情况，一律友好兜底，不抛给 ReAct 循环
        hint = ""
        estr = str(e)
        if "mojeek" in estr.lower() or "certificate" in estr.lower() or "ConnectError" in estr:
            hint = "（可能是当前网络环境下搜索接口证书异常，可稍后再试。）"
        return f"搜索引擎暂时不可用：{estr}{hint}"


# ========== 4. 工具3：获取当前时间（弥补 LLM 无时钟的缺陷） ==========
@tool("获取当前时间")
def current_time_func(_: str = "") -> str:
    """获取服务器当前的日期、时间和星期。
    当用户询问“现在几点”“今天星期几”“今天日期”等与时钟相关的问题时，必须调用这个工具。
    输入可为空字符串。"""
    try:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return now.strftime(f"%Y年%m月%d日 %H时%M分%S秒 {weekdays[now.weekday()]}")
    except Exception as e:
        return f"获取当前时间失败：{e}"


# ========== 5. 创建 Agent（LangChain 1.x 推荐 create_agent） ==========
def _build_agent():
    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        temperature=0
    )

    system_prompt = (
        "你是一个会调用工具的中文智能助手。"
        "你可以选择调用【知识库检索】或【搜索引擎】，也可以根据常识直接回答简单问题。"
        "回答使用简洁的中文。"
        "如果工具返回异常提示或空内容，不要反复尝试同一工具，直接基于已有信息给出回答，"
        "或在回答中明确告知当前工具不可用。"
    )

    # 基于 LangChain 1.x 的 create_agent（底层为编译后的 LangGraph，自带解析鲁棒性与步数限制）
    agent = create_agent(
        llm,
        [rag_tool_func, search_tool_func, current_time_func],
        system_prompt=system_prompt,
        debug=False,
    )
    return agent


# 全局实例（启动时创建一次）
agent = _build_agent()


def ask_agent(question: str, user_id: int | None = None) -> str:
    """调用 Agent 回答问题。对外稳定返回字符串，任何异常都封装为友好文案。"""
    # 注入当前用户，供知识库工具做租户隔离
    current_user_id.set(user_id)
    if not question or not str(question).strip():
        return "请输入有效的问题。"

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": str(question)}]})
        messages = result.get("messages") if isinstance(result, dict) else None
        if not messages:
            return "Agent 未返回任何消息。"
        last = messages[-1]
        content = getattr(last, "content", None)
        if content is None:
            content = str(last)
        answer = str(content).strip()
        if not answer:
            return "Agent 返回了空回答。"
        return answer
    except Exception as e:
        return f"Agent 执行失败：{e}"


def stream_ask_agent(question: str, user_id: int | None = None):
    """流式调用 Agent，逐步 yield 思考过程事件。

    每个事件是 dict，格式：
      {"type": "thought",     "content": "..."}   # LLM 的思考/文本
      {"type": "action",      "tool": "...", "input": "..."}  # 工具调用
      {"type": "observation", "content": "..."}   # 工具返回
      {"type": "answer",      "content": "..."}   # 最终答案
      {"type": "error",       "content": "..."}   # 错误
    """
    # 注入当前用户，供知识库工具做租户隔离
    current_user_id.set(user_id)

    if not question or not str(question).strip():
        yield {"type": "error", "content": "请输入有效的问题。"}
        return

    try:
        # stream_mode="updates": 每个节点执行后推送更新（包含 messages 增量）
        stream = agent.stream(
            {"messages": [{"role": "user", "content": str(question)}]},
            stream_mode="updates",
        )
        final_answer = ""
        for update in stream:
            # update 形如 {"agent": {"messages": [...]}} 或 {"tools": {"messages": [...]}}
            for node_name, node_payload in update.items():
                messages = node_payload.get("messages", []) if isinstance(node_payload, dict) else []
                for msg in messages:
                    # 判断消息类型
                    msg_type = type(msg).__name__
                    # AIMessage:可能是思考/工具调用，也可能是最终答案
                    if msg_type in ("AIMessage", "ChatOpenAI"):
                        content = getattr(msg, "content", "") or ""
                        tool_calls = getattr(msg, "tool_calls", None) or []
                        if tool_calls:
                            # 这是一个工具调用动作
                            for tc in tool_calls:
                                tool_name = tc.get("name", "未知工具") if isinstance(tc, dict) else getattr(tc, "name", "未知工具")
                                tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                                # 如果有思考文本，先推送 thought
                                if content and content.strip():
                                    yield {"type": "thought", "content": content.strip()}
                                # 推送 action
                                args_str = str(tool_args) if tool_args else ""
                                yield {
                                    "type": "action",
                                    "tool": tool_name,
                                    "input": args_str,
                                }
                        else:
                            # 没有工具调用，是最终答案（或中间纯文本思考）
                            if content and content.strip():
                                if node_name == "agent":
                                    # 检查是否是最终答案（后面没有更多步骤）
                                    # 简单处理：作为潜在答案推送，最后确认
                                    final_answer = content.strip()
                                    yield {"type": "answer", "content": content.strip()}
                                else:
                                    yield {"type": "thought", "content": content.strip()}
                    elif msg_type == "ToolMessage":
                        # 工具返回结果
                        content = getattr(msg, "content", "") or ""
                        yield {"type": "observation", "content": str(content)}
        # 结束标记
        yield {"type": "done", "content": final_answer}
    except Exception as e:
        yield {"type": "error", "content": f"Agent 执行失败：{e}"}
