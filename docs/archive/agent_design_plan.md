# 京东用户行为分析 Agent 设计方案

## 1. 项目定位

在现有京东用户行为分析项目基础上，新增一个面向电商运营场景的智能数据分析 Agent。它不是通用聊天机器人，也不是替代原有 Tableau 看板，而是把已经完成的数据清洗、行为漏斗、RFM 用户分层、地区分析、设备分析、评论词频等能力封装成可交互的自然语言问数工具。

最终目标是让用户可以直接输入业务问题，例如“为什么用户浏览很多但购买少”“哪些用户适合做促销”“晚上做活动有没有价值”，系统自动调用对应分析函数，返回数据结论、图表和运营建议。

## 2. 目标用户

### 电商运营人员

运营人员通常关注转化、留存、促销、用户分层和商品表现，但不一定会 Python、SQL 或 Tableau。Agent 可以让他们直接用自然语言提问，并得到可执行的运营建议。

### 数据分析实习生或业务分析同学

分析人员可以用 Agent 快速验证业务假设，减少重复打开 notebook、筛选数据、重新写代码的成本。

### 面试官或项目评审者

Agent 是项目展示入口。它能证明该项目不只是静态数据分析报告，而是把分析能力封装成了一个可使用的数据产品，和简历中“AI 工具、DeepSeek API、LangChain 数据分析 Agent”的表述形成对应。

## 3. Agent 的具体作用

1. 自然语言问数：用户不用写代码，直接提问业务问题。
2. 自动选择分析工具：系统根据问题调用漏斗、RFM、时段、地区、设备、评论等固定分析函数。
3. 输出数据证据：返回关键指标、表格和图表，而不是只给主观建议。
4. 生成业务解释：把指标转化为运营语言，解释现象背后的可能原因。
5. 生成策略建议：针对不同用户分层、行为流失、活跃时段、地区差异输出运营动作。

## 4. 推荐技术路线

推荐使用 Streamlit + Pandas + DuckDB + DeepSeek API / OpenAI-compatible API。

Streamlit 用于快速构建交互式 Web 页面，Pandas 负责复用现有 CSV 数据处理逻辑，DuckDB 用于对大 CSV 进行更灵活的 SQL 查询，DeepSeek API 或兼容接口负责自然语言理解和结果解释。

不建议一开始做 FastAPI + React + 多 Agent 架构，因为当前项目的核心价值在于“把已有分析产品化”，不是展示复杂工程架构。轻量 Web Demo 更适合简历、答辩和面试演示。

## 5. 功能边界

### 第一版必须实现

1. 数据概览：展示总记录数、用户数、商品数、行为类型、时间范围。
2. 行为漏斗分析：浏览、加购、收藏、购买的数量和转化率。
3. RFM 用户分层分析：展示不同用户标签数量、占比和运营建议。
4. 时间趋势分析：按日期和小时展示活跃趋势，识别高峰时段。
5. 地区与设备分析：展示高活跃地区、高销售地区、不同设备转化率。
6. 评论关键词分析：基于已有词频结果输出用户关注点。
7. 自然语言问答：用户输入问题后，Agent 自动选择对应工具并生成中文回答。

### 第一版不做

1. 不让大模型随意执行任意 Python 代码。
2. 不让大模型无限制生成 SQL 后直接执行。
3. 不做复杂权限系统、登录系统和数据库后台。
4. 不重新爬取数据。
5. 不替代 Tableau 工作簿，只作为更易演示的交互入口。

## 6. 推荐目录结构

```text
data_analyse/
  agent_app/
    app.py
    data_loader.py
    metrics.py
    agent.py
    prompts.py
    sample_questions.py
    requirements.txt
  docs/README_agent.md
```

### 文件职责

`app.py`：Streamlit 主页面，负责输入框、示例问题、指标卡片、图表和结果展示。

`data_loader.py`：读取 `data/processed/jd_analysis_final.csv`、`data/processed/jd_rfm_result.csv`、`data/processed/comment_word_freq.csv`，统一处理路径和缓存。

`metrics.py`：封装稳定的分析工具函数，例如行为漏斗、RFM 分布、时段趋势、地区销售、设备转化、评论词频。

`agent.py`：负责问题理解、工具选择、工具调用和最终回答生成。

`prompts.py`：保存 Agent 提示词，限制模型基于工具结果回答，不编造数据。

`sample_questions.py`：保存页面上的示例问题，方便演示。

`docs/README_agent.md`：说明如何运行、能问什么问题、项目亮点和简历写法。

## 7. Agent 工作流程

```text
用户输入自然语言问题
  -> Agent 判断问题意图
  -> 选择一个或多个分析工具
  -> 从 CSV / DuckDB / Pandas 中计算结果
  -> 把结构化结果交给 LLM
  -> LLM 生成中文解释和运营建议
  -> Streamlit 展示图表、表格和结论
```

示例：

```text
问题：为什么用户浏览很多但购买少？

调用工具：
1. get_behavior_funnel()
2. get_top_categories()
3. get_hourly_behavior()

输出：
浏览到加购阶段流失率最高，说明用户有浏览兴趣但没有形成进一步购买意向。可能原因包括商品推荐匹配度不足、详情页说服力弱、价格刺激不足。建议优化推荐策略、强化详情页卖点，并在高活跃时段推送限时优惠。
```

## 8. 可支持的问题类型

```text
为什么浏览量高但购买量低？
哪一步转化流失最严重？
核心价值用户占比是多少，应该怎么运营？
哪些用户适合发优惠券？
哪个时间段最适合做促销？
哪些地区销售额最高？
不同设备的转化率有什么差异？
评论里用户最关注什么问题？
帮我生成一份京东用户行为运营分析摘要。
```

注意：这些不是固定问法，用户可以换表达。Agent 的底层能力是固定的，但提问方式可以自然变化。

## 9. 开发步骤

### 第一步：整理数据读取层

读取现有三个结果文件：

```text
data/processed/jd_analysis_final.csv
data/processed/jd_rfm_result.csv
data/processed/comment_word_freq.csv
```

要求能够返回数据概览，包括记录数、用户数、商品数、行为类型、日期范围。

### 第二步：封装指标函数

从原 notebook 中抽出稳定分析逻辑，封装为函数：

```text
get_data_overview()
get_behavior_funnel()
get_rfm_summary()
get_hourly_trend()
get_daily_trend()
get_area_summary()
get_device_conversion()
get_comment_keywords()
```

这些函数必须返回结构化数据，例如 DataFrame 或 dict，不能只打印结果。

### 第三步：构建工具选择逻辑

先用关键词规则实现稳定版本，例如：

```text
转化 / 流失 / 漏斗 -> get_behavior_funnel()
用户价值 / 分层 / RFM -> get_rfm_summary()
时间 / 高峰 / 促销 -> get_hourly_trend()
地区 / 城市 -> get_area_summary()
设备 / 手机 -> get_device_conversion()
评论 / 评价 / 关键词 -> get_comment_keywords()
```

后续可以再升级为 LangChain tool-calling。

### 第四步：接入 LLM 解释层

把工具计算出的真实结果传给 DeepSeek API 或 OpenAI-compatible API，让模型只做解释和建议，不直接编造指标。

提示词要求：

1. 必须基于工具结果回答。
2. 不知道的数据明确说明“当前数据无法判断”。
3. 输出结构固定为“结论、数据依据、原因分析、运营建议”。
4. 中文回答，适合电商运营人员阅读。

### 第五步：构建 Streamlit 页面

页面包括：

1. 顶部项目名称和数据概览。
2. 左侧示例问题。
3. 中间自然语言输入框。
4. 回答区域展示结论、表格和图表。
5. 下方展示可用分析能力。

### 第六步：补充项目说明

新增 `docs/README_agent.md`，写清楚：

1. 项目背景。
2. Agent 能力。
3. 运行方式。
4. 示例问题。
5. 技术架构。
6. 简历亮点写法。

## 10. 验收标准

1. 可以在本地通过 `streamlit run agent_app/app.py` 启动。
2. 页面能正常加载现有 CSV 数据。
3. 至少 8 个示例问题可以稳定回答。
4. 每个回答至少包含一个真实数据依据。
5. 不出现模型凭空编造指标。
6. 可以作为面试演示入口使用。


