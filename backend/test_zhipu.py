import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 1. 加载环境变量
load_dotenv()

# 2. 读取配置
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_API_BASE")
model_name = os.getenv("MODEL_NAME")

print(f"🔧 当前配置：")
print(f"   - 模型: {model_name}")
print(f"   - 接口地址: {base_url}")
print(f"   - API Key: {api_key[:6]}...{api_key[-4:]} (仅显示前后几位)")

# 3. 初始化 LLM（大语言模型）
llm = ChatOpenAI(
    model=model_name,
    openai_api_key=api_key,
    openai_api_base=base_url,
    temperature=0.2  # 0-1，越低回答越稳定
)

# 4. 发送测试提问
print("\n🤖 正在向智谱发送测试请求...")
response = llm.invoke("你好！请用一句话介绍你自己。")

# 5. 打印回答
print(f"\n✅ 智谱回答：\n{response.content}")