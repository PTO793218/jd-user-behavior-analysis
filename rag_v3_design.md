# 第三版 RAG 设计方案

## 1. 设计目标

第三版在现有京东用户行为分析 Agent 上增加轻量本地 RAG 能力，使系统可以回答项目背景、字段含义、指标定义、样本口径和运营策略等知识型问题。

RAG 的目标不是重新计算数据，而是增强解释能力。结构化指标仍由现有 `metrics.py` 工具函数计算，RAG 只负责检索本地知识库，为 LLM 提供可靠上下文。

## 2. 功能边界

### RAG 应该支持

- 项目背景和数据范围解释。
- 字段含义解释。
- 行为类型和指标口径解释。
- RFM 分层方法解释。
- 评论语义分析样本口径解释。
- 运营策略知识检索。
- 和数据工具组合回答“指标 + 口径”类问题。

### RAG 不应该支持

- 不直接读取 75 万行行为明细重新计算指标。
- 不替代行为漏斗、RFM、地区、设备、评论语义等现有工具。
- 不做联网搜索。
- 不接入向量数据库。
- 不额外调用 embedding API。
- 不回答与项目无关的通用闲聊问题。
- 不把“这个项目怎么写进简历”作为业务知识库问题。

## 3. 推荐目录结构

```text
knowledge_base/
  project_overview.md
  data_dictionary.md
  metric_definitions.md
  semantic_analysis_notes.md
  operation_strategy.md

agent_app/
  knowledge_base.py
  rag.py
```

## 4. 检索设计

第三版采用本地轻量检索。

流程：

```text
读取 Markdown 文档
  -> 按标题和段落切片
  -> 为每个片段记录 source、heading、content
  -> 对用户问题和片段做关键词/字符 n-gram 匹配
  -> 返回 Top K 相关片段
  -> LLM 基于片段生成回答
```

不使用向量数据库的原因：

- 当前知识库规模很小，Markdown 文档数量有限。
- 关键词和 n-gram 检索已经足够覆盖字段、指标和运营策略问题。
- 不增加 embedding API 成本。
- GitHub 展示和本地运行更简单。

## 5. Agent 路由设计

现有 Agent 已有结构化工具路由。第三版增加 RAG 路由规则：

当问题包含以下意图时，调用 RAG：

```text
定义、含义、口径、字段、为什么、怎么理解、样本、范围、RFM 是什么、sentiment_score、语义分析、运营策略、使用边界
```

当问题包含具体指标计算时，继续调用现有数据工具：

```text
多少、占比、转化率、最高、最低、趋势、地区、设备、用户分层、负面数量
```

组合问题同时调用 RAG 和数据工具。

示例：

```text
问题：为什么浏览量高但购买少？这个转化率怎么算？
调用：behavior_funnel + RAG
```

```text
问题：sentiment_score 是什么意思？
调用：RAG
```

```text
问题：售后问题严重吗，应该怎么处理？
调用：comment_semantic + RAG
```

## 6. 页面设计

Streamlit 页面新增一个 Tab：

```text
项目知识库 RAG
```

该 Tab 包含：

- 输入框：输入项目知识问题。
- “检索知识库”按钮。
- 回答区：展示中文回答。
- 依据区：展示 Top K 片段，包括文档名、标题和片段内容。

自然语言问数 Tab 也可以接入 RAG。当用户问题需要口径解释时，回答中增加“参考知识库依据”。

## 7. 回答格式

RAG 回答建议使用：

```text
结论：
知识库依据：
解释：
使用边界：
```

如果同时调用数据工具，则使用：

```text
结论：
数据依据：
知识库依据：
原因分析：
运营建议：
```

## 8. 验收标准

- 可以读取 `knowledge_base/*.md`。
- 可以返回 Top 3 相关知识片段。
- 可以回答字段含义、RFM 定义、行为漏斗口径、语义分析样本口径等问题。
- 找不到依据时明确说明知识库暂无相关内容。
- 不影响现有自然语言问数、固定分析看板和评论语义分析功能。
- 单元测试覆盖文档加载、切片、检索和 Agent 路由。
- `python -m pytest agent_app\tests -q` 通过。

## 9. GitHub 提交建议

建议先提交当前稳定版，再提交 RAG 第三版：

```powershell
git add .gitignore README_agent.md assets agent_app agent_design_plan.md comment_semantic_result.csv semantic_summary.csv
git commit -m "feat: add JD behavior analysis agent"

git add knowledge_base rag_v3_design.md agent_app README_agent.md
git commit -m "feat: add project knowledge RAG"
```

如果第三版暂时只提交设计和知识库，不提交代码，也可以只提交：

```powershell
git add knowledge_base rag_v3_design.md
git commit -m "docs: add RAG knowledge base design"
```

## 10. 给 Codex 的提示词

请在 `D:\Agent_data_analyse\data_analyse` 当前京东用户行为分析 Agent 项目上新增第三版 RAG 能力。开始前请先阅读 `README_agent.md`、`agent_design_plan.md`、`rag_v3_design.md` 和 `knowledge_base/` 下的全部 Markdown 文档，不要覆盖 `.env`，不要影响现有自然语言问数、固定分析看板、评论语义分析和示例问题点击填入输入框功能。请新增轻量本地 RAG 模块，用于回答项目背景、字段含义、指标定义、RFM 口径、行为漏斗口径、评论语义分析样本说明、运营策略和使用边界等项目知识问题；结构化数据问题仍然调用现有 `metrics.py` 工具，不要用 RAG 查询 75 万行 CSV。请新增 `agent_app/knowledge_base.py` 和 `agent_app/rag.py`，实现 Markdown 加载、按标题/段落切片、本地关键词或字符 n-gram 检索、Top K 片段返回，并在 Streamlit 中新增“项目知识库 RAG”Tab，展示回答和参考片段来源；自然语言问数在遇到“定义、含义、口径、字段、为什么、样本、范围、运营策略”等问题时可以同时调用 RAG。回答必须基于知识库片段，找不到依据时明确说明知识库暂无相关内容；涉及评论语义分析时必须说明当前是 960 条去重评论样本，不是全量评论。请补充测试，更新 `README_agent.md`，运行 `python -m pytest agent_app\tests -q` 验证，并告诉我启动命令和测试结果。
