"""RAG 检索评测脚本：测量当前切片与检索配置下的 top-k 命中率。

题目来自 PDF 自身内容（eval/questions.json），命中判定：
top-k 个切片中任意一个包含题目任意一个期望关键词（比对时忽略空白差异）即算命中。

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe eval\\retrieval_eval.py
    .venv\\Scripts\\python.exe eval\\retrieval_eval.py --pdf "temp/前端实习生-侯志方 .pdf" --k 3
"""
import argparse
import json
import os
import re
import sys

from dotenv import load_dotenv

# 允许从 backend 目录直接运行时导入同级模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from embeddings import get_embeddings

load_dotenv()

DEFAULT_PDF = os.path.join("temp", "前端实习生-侯志方 .pdf")
QUESTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions.json")


def normalize(text: str) -> str:
    """去掉所有空白字符，避免 PDF 提取出的空格差异影响关键词匹配。"""
    return re.sub(r"\s+", "", text or "")


def load_retriever(pdf_path: str, chunk_size: int, chunk_overlap: int, k: int):
    """按当前项目配置构造检索器（与 routers/upload.py 的参数保持一致）。"""
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(documents)

    embeddings = get_embeddings()
    # 内存态向量库，不写磁盘，避免污染线上 chroma_db
    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="eval_tmp",
    )
    return vector_store.as_retriever(search_kwargs={"k": k}), chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=DEFAULT_PDF)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=50)
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"找不到 PDF：{args.pdf}")
        return 2

    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print(f"PDF: {args.pdf}")
    print(f"题目数: {len(questions)}   chunk_size={args.chunk_size} overlap={args.chunk_overlap} k={args.k}")

    try:
        retriever, chunks = load_retriever(args.pdf, args.chunk_size, args.chunk_overlap, args.k)
    except Exception as e:
        print(f"\n[失败] 构建向量库出错（多为 embedding 接口不可用）：{e}")
        return 1

    print(f"切片总数: {len(chunks)}（每块上限 {args.chunk_size} 字符）\n")

    hits = 0
    ranks = []
    rows = []
    for item in questions:
        try:
            docs = retriever.invoke(item["question"])
        except Exception as e:
            print(f"\n[失败] 检索时出错（多为 embedding 接口不可用）：{e}")
            return 1

        keywords = [normalize(kw) for kw in item["keywords"]]
        hit_rank = 0
        for rank, doc in enumerate(docs, start=1):
            content = normalize(doc.page_content)
            if any(kw in content for kw in keywords):
                hit_rank = rank
                break

        if hit_rank:
            hits += 1
            ranks.append(hit_rank)
        rows.append({
            "id": item["id"],
            "question": item["question"],
            "hit_rank": hit_rank,
        })
        mark = f"命中(第{hit_rank}位)" if hit_rank else "未命中"
        print(f"[{item['id']:>2}] {mark:<12} {item['question']}")

    total = len(questions)
    rate = hits / total if total else 0
    print("\n" + "=" * 60)
    print(f"top-{args.k} 命中: {hits}/{total} = {rate:.1%}")
    if ranks:
        print(f"平均命中排位: {sum(ranks) / len(ranks):.2f}")
    print("=" * 60)

    report = {
        "pdf": args.pdf,
        "total_chunks": len(chunks),
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "k": args.k,
        "hit_count": hits,
        "total_questions": total,
        "hit_rate": round(rate, 4),
        "avg_hit_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "details": rows,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
