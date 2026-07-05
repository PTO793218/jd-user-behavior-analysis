# 数据字典

## 主行为数据：data/processed/jd_analysis_final.csv

`data/processed/jd_analysis_final.csv` 是当前 Agent 的主数据源，包含清洗后的京东用户行为明细。每一行代表一次用户行为记录。

| 字段 | 含义 | 说明 |
| --- | --- | --- |
| `user_id` | 用户 ID | 用于区分不同用户。 |
| `goods_id` | 商品 ID | 用于区分不同商品。 |
| `category_id` | 商品类目 ID | 用于分析类目热度和类目销售表现。 |
| `behavior` | 行为类型 | 包括 `pv`、`cart`、`fav`、`buy`。 |
| `timestamp` | 行为发生时间 | 已转换为可读时间。 |
| `sex` | 性别字段 | 原始数据中的用户性别标记，当前 Agent 第一版未重点使用。 |
| `address` | 地址/地区 | 用于地区活跃度和地区销售分析。 |
| `device` | 设备类型 | 用于设备活跃度、购买量和转化率分析。 |
| `price` | 商品价格 | 与购买数量一起计算销售额。 |
| `amount` | 购买数量 | 非购买行为通常为 0。 |
| `comment` | 评论文本 | 用于评论词频和评论语义分析。 |
| `date` | 日期 | 从时间字段拆分得到，用于日趋势分析。 |
| `hour` | 小时 | 从时间字段拆分得到，用于小时活跃趋势分析。 |
| `month` | 月份 | 从时间字段拆分得到。 |
| `weekday` | 星期 | 从时间字段拆分得到。 |
| `sales` | 销售额 | 计算方式为 `price * amount`。 |

## 行为类型口径

| 行为 | 含义 | 业务解释 |
| --- | --- | --- |
| `pv` | 浏览 | 用户看过商品或页面，代表曝光和兴趣起点。 |
| `cart` | 加购 | 用户将商品加入购物车，代表较强购买意向。 |
| `fav` | 收藏 | 用户收藏商品，代表延迟购买或关注意向。 |
| `buy` | 购买 | 用户完成购买，是最终转化行为。 |

## RFM 结果数据：data/processed/jd_rfm_result.csv

`data/processed/jd_rfm_result.csv` 是购买用户的 RFM 分层结果，当前共有 6,108 名用户。

| 字段 | 含义 |
| --- | --- |
| `user_id` | 用户 ID。 |
| `R` | Recency，最近一次购买距离分析结束日的天数。值越小代表越近期活跃。 |
| `F` | Frequency，购买频次。值越高代表购买越频繁。 |
| `M` | Monetary，消费金额。值越高代表贡献金额越高。 |
| `R_score` | R 指标评分。 |
| `F_score` | F 指标评分。 |
| `M_score` | M 指标评分。 |
| `RFM` | R、F、M 三个评分组合。 |
| `label` | 用户分层标签。 |

当前 RFM 分层包括：

- 核心价值用户：1,720 人。
- 流失用户：1,278 人。
- 一般发展用户：919 人。
- 重点保持用户：842 人。
- 高潜力用户：513 人。
- 一般保持用户：344 人。
- 高消费沉睡用户：296 人。
- 高消费流失预警用户：196 人。

## 评论语义结果：data/processed/comment_semantic_result.csv

`data/processed/comment_semantic_result.csv` 是评论语义分析明细结果。当前已完成 960 条去重评论样本分析。

| 字段 | 含义 |
| --- | --- |
| `comment_hash` | 评论文本的哈希值，用于去重和断点续跑。 |
| `comment` | 原始评论文本。 |
| `sentiment` | 情绪分类，包括正面、中性、负面。 |
| `sentiment_score` | 情感分数，范围为 -1 到 1，越接近 1 越正面，越接近 -1 越负面。 |
| `aspects` | 评论涉及的方面标签，例如质量、物流、价格、服务、包装、售后、体验。 |
| `negative_reasons` | 负面或中性偏负评论中的原因短语。 |
| `model` | 使用的大模型名称。 |
| `analyzed_at` | 分析时间。 |

## 评论语义汇总：data/processed/semantic_summary.csv

`data/processed/semantic_summary.csv` 是评论语义分析聚合结果。

| 字段 | 含义 |
| --- | --- |
| `summary_type` | 汇总类型，包括 `sentiment`、`aspect`、`negative_reason`。 |
| `name` | 情绪名称、方面名称或负面原因名称。 |
| `count` | 出现次数。 |
| `percentage` | 占比。 |
| `avg_sentiment_score` | 平均情感分数。 |
| `negative_count` | 负面数量。 |
| `negative_rate` | 负面率。 |

