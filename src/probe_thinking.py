"""探测网关支持哪种"关闭思考模式"的参数。每次请求 max_tokens=150，成本可忽略。"""
import os, sys, time, json
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/src")
from vlm_report import load_env  # noqa: E402

load_env()
client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url=os.environ["DEEPSEEK_BASE_URL"])
model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

MSG = [{"role": "user", "content": "用一句话说明为什么混凝土浇筑后需要养护。"}]

VARIANTS = [
    ("baseline",        {}),
    ("thinking:disabled", {"extra_body": {"thinking": {"type": "disabled"}}}),
    ("enable_thinking",  {"extra_body": {"enable_thinking": False}}),
    ("reasoning_effort", {"reasoning_effort": "none"}),
    ("effort_minimal",   {"reasoning_effort": "minimal"}),
]

print(f"model={model}  base={os.environ['DEEPSEEK_BASE_URL']}\n")
for name, extra in VARIANTS:
    t0 = time.time()
    try:
        r = client.chat.completions.create(model=model, messages=MSG,
                                           max_tokens=150, **extra)
        u = r.usage
        msg = r.choices[0].message
        think = getattr(msg, "reasoning_content", None)
        print(f"{name:18s} OK   {time.time()-t0:5.1f}s  "
              f"in={u.prompt_tokens:4d} out={u.completion_tokens:4d} "
              f"thinking={'有(' + str(len(think)) + '字符)' if think else '无'}")
        print(f"{'':18s}     内容: {(msg.content or '')[:60]}")
    except Exception as e:                              # noqa: BLE001
        body = getattr(getattr(e, "response", None), "text", "")
        print(f"{name:18s} 失败 {type(e).__name__}: {str(e)[:90]}")
        if body:
            print(f"{'':18s}     {body[:200]}")
