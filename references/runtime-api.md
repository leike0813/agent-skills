# 运行 API 速查

生成具体代码前按所选结构阅读对应示例，执行约束以主文件为准。以下 API 示例的版本基线为 langgraph 1.2.16、langchain 1.4.7、langchain-core 1.6.13、langgraph-cli 0.4.37。

## 固定图

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    value: str

def process(state: State):
    return {"value": state["value"].strip()}

builder = StateGraph(State)
builder.add_node("process", process)
builder.add_edge(START, "process")
builder.add_edge("process", END)
graph = builder.compile()
result = graph.invoke({"value": " example "})
```

例中 `process` 只更新 `value`。聚合通道的写法为 `Annotated[类型, reducer]`，消息聚合常用 `add_messages`。
条件路由可用 `add_conditional_edges(节点, 路由函数, 路由映射)`；`Command(update=..., goto=...)` 合并更新和跳转，和同目标静态边并用会产生重复调度。`Send(节点名, 子任务输入)` 可表示源许可的动态任务分发。

## agent 与混合流程

```python
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

def make_agent(model_id: str, provider: str, tools, instructions: str):
    model = init_chat_model(model_id, model_provider=provider)
    return create_agent(model=model, tools=tools, system_prompt=instructions)
```

例中模型标识及 provider 由调用方传入，对应集成包是应用运行依赖。agent 输入通常为 `{"messages": [...]}`，业务结果从返回状态提取。
固定图的节点可调用 `agent.invoke(agent_input, config=config)`，再将所需结果映射回外层状态。这里的 config 连接当前调用与嵌套运行；子图恢复还涉及检查点传播及调用命名空间。

## 暂停与存储

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

def confirm(state):
    reply = interrupt({"question": "Proceed?"})
    return {"approved": reply is True}

# 假定 builder 已按源契约构建。
graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "task-1"}}
paused = graph.invoke(input_state, config)
resumed = graph.invoke(Command(resume=True), config)
```

例中两次调用共用图实例和 `thread_id`；`InMemorySaver` 的恢复记录仅在该进程存活期间存在。
`interrupt()` 恢复会从节点开头重跑，因此 `confirm` 只提问并记录回复，写入安排在批准后的节点。checkpointer 保存执行恢复记录，store 提供跨会话数据；二者不是同一设施。

## 应用入口

```json
{
  "dependencies": ["."],
  "graphs": {"source-name": "./skill_graph/graph.py:graph"}
}
```

入口值支持模块或文件的 `:对象名`，对象可为编译图，也可为服务可加载的工厂。上例导出 `graph`；工厂入口可写为 `./skill_graph/graph.py:cli_graph`。在应用目录执行 `langgraph dev` 会启动服务，启动与依赖安装均受调用环境授权约束。

基线服务按完整签名统计工厂参数，可选 keyword-only 参数也计入。例如 `make_graph(config, *, checkpointer=None, store=None)` 有三个参数，不能直接作为该服务的单参数工厂。下面的薄入口与 Python 调用共享装配逻辑：

```python
def cli_graph(config):
    return make_graph(config)

# Python 调用可用 make_graph(config, checkpointer=调用方提供的检查点)。
# CLI 运行使用服务设施，cli_graph 不绑定具体存储后端。
```

已配置 Agent Server 的基本调用：

```text
POST /runs/wait
{"assistant_id":"source-name","input":{...}}
```

有会话恢复需求时，`POST /threads` 返回的 thread_id 用于 `/threads/{thread_id}/runs/wait`。恢复请求中的 `{"command":{"resume":true}}` 对应 Python 的 `Command(resume=True)`，两者提交同一业务回复。

`langgraph.json` 的 `env` 可指定 dotenv 文件或环境变量映射。应用目录中的资源可相对 `Path(__file__).resolve()` 定位；wheel 是否仍有同样资源，取决于实际打包内容，应用目录运行成功不能提供 wheel 安装后的证据。

来源：

- https://reference.langchain.com/python/langgraph/graphs/
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/langsmith/cli
- https://docs.langchain.com/langsmith/agent-server-api
