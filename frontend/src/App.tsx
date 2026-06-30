import { Fragment, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  BookOpen,
  Clipboard,
  Copy,
  Database,
  FileText,
  History,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  Trash2,
  Users,
  Wrench
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { api } from "./api";
import { Button } from "./components/ui/button";
import { Panel } from "./components/ui/panel";
import type {
  ChatResponse,
  Confidence,
  Message,
  Overview,
  RagSource,
  Session,
  ToolCall,
  ToolPayload,
  VisualPayload
} from "./types";

const sampleQuestions = [
  "给我一份京东用户行为数据概览",
  "为什么浏览量高但购买少，哪一步流失最严重？",
  "那应该优先优化哪个？",
  "RFM 是什么含义？",
  "行为漏斗的口径是什么？",
  "负面评论主要集中在哪些方面？",
  "质量和物流哪个问题更严重？"
];

const emptyConfidence: Confidence = {
  level: "中",
  reason: "发送问题后会根据工具结果和知识库来源计算可信度。"
};

function formatNumber(value: unknown) {
  if (typeof value !== "number") return String(value ?? "-");
  return new Intl.NumberFormat("zh-CN").format(value);
}

function shortTitle(title: string) {
  return title.length > 18 ? `${title.slice(0, 18)}...` : title;
}

function parseToolCalls(toolCalls: ToolCall[]): ToolPayload[] {
  return toolCalls.map((call) => {
    let result: unknown = call.result_json;
    try {
      result = JSON.parse(call.result_json);
    } catch {
      result = call.result_json;
    }
    return { name: call.tool_name, result };
  });
}

function extractRagSources(tools: ToolPayload[]): RagSource[] {
  const rag = tools.find((tool) => tool.name === "rag");
  const result = rag?.result as { sources?: RagSource[] } | undefined;
  return result?.sources || [];
}

function prettyToolName(name: string) {
  const names: Record<string, string> = {
    data_overview: "数据概览",
    behavior_funnel: "行为漏斗",
    rfm_summary: "RFM 分层",
    hourly_trend: "小时趋势",
    daily_trend: "日期趋势",
    area_summary: "地区分析",
    device_conversion: "设备转化",
    comment_keywords: "评论关键词",
    comment_semantic: "评论语义",
    top_categories: "品类分析",
    rag: "知识库 RAG"
  };
  return names[name] || name;
}

function confidenceClass(level: Confidence["level"]) {
  if (level === "高") return "border-success bg-emerald-50 text-emerald-800";
  if (level === "中") return "border-accent bg-amber-50 text-amber-800";
  return "border-danger bg-red-50 text-red-800";
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function renderMessageContent(content: string) {
  return content.split(/\n/).map((line, index) => {
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.+)$/);
    if (heading) {
      return (
        <div key={index} className="mt-2 font-semibold">
          {renderInlineMarkdown(heading[1])}
        </div>
      );
    }
    return (
      <div key={index} className={line.trim() ? "" : "h-3"}>
        {renderInlineMarkdown(line)}
      </div>
    );
  });
}

function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolPayload[]>([]);
  const [ragSources, setRagSources] = useState<RagSource[]>([]);
  const [visualPayloads, setVisualPayloads] = useState<VisualPayload[]>([]);
  const [routingExplanation, setRoutingExplanation] = useState("");
  const [confidence, setConfidence] = useState<Confidence>(emptyConfidence);
  const [contextSummary, setContextSummary] = useState("");
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId),
    [sessions, currentSessionId]
  );

  async function refreshSessions(selectId?: string) {
    const rows = await api.listSessions();
    setSessions(rows);
    const nextId = selectId || currentSessionId || rows[0]?.id;
    if (nextId) {
      setCurrentSessionId(nextId);
      await loadSession(nextId);
    }
  }

  async function loadSession(id: string) {
    const detail = await api.getSession(id);
    setCurrentSessionId(id);
    setMessages(detail.messages);
    const parsedTools = parseToolCalls(detail.tool_calls);
    setToolCalls(parsedTools);
    setRagSources(extractRagSources(parsedTools));
    setVisualPayloads([]);
    setRoutingExplanation("");
    setContextSummary("");
    setReportMarkdown("");
  }

  async function createSession() {
    setLoading(true);
    try {
      const session = await api.createSession("运营分析会话");
      await refreshSessions(session.id);
      setQuestion("");
      setStatus("已创建新会话");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "创建会话失败");
    } finally {
      setLoading(false);
    }
  }

  async function deleteSession(id: string) {
    setLoading(true);
    try {
      await api.deleteSession(id);
      setMessages([]);
      setToolCalls([]);
      setRagSources([]);
      setVisualPayloads([]);
      setRoutingExplanation("");
      setContextSummary("");
      setCurrentSessionId(undefined);
      await refreshSessions();
      setStatus("会话已删除");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "删除会话失败");
    } finally {
      setLoading(false);
    }
  }

  async function sendQuestion(text = question) {
    const trimmed = text.trim();
    if (!trimmed) return;

    const tempUser: Message = {
      id: `tmp-${Date.now()}`,
      session_id: currentSessionId || "",
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString()
    };
    setMessages((items) => [...items, tempUser]);
    setQuestion("");
    setLoading(true);
    setStatus("Agent 正在选择工具、读取上下文和计算指标");

    try {
      const response: ChatResponse = await api.chat(trimmed, currentSessionId);
      setCurrentSessionId(response.session_id);
      await refreshSessions(response.session_id);
      setToolCalls(response.tools);
      setRagSources(response.rag_sources);
      setVisualPayloads(response.visual_payloads || []);
      setRoutingExplanation(response.routing_explanation || "");
      setConfidence(response.confidence || emptyConfidence);
      setContextSummary(response.context_summary || "");
      setReportMarkdown("");
      setStatus(response.error || (response.used_llm ? "已使用大模型生成回答" : "已使用本地降级回答"));
    } catch (error) {
      setMessages((items) => items.filter((item) => item.id !== tempUser.id));
      setStatus(error instanceof Error ? error.message : "发送失败");
    } finally {
      setLoading(false);
    }
  }

  async function generateReport() {
    if (!currentSessionId) {
      setStatus("请先创建或选择一个会话");
      return;
    }
    setLoading(true);
    try {
      const response = await api.generateReport(currentSessionId);
      setReportMarkdown(response.report_markdown);
      setStatus("报告已生成，可在右侧预览和复制");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "生成报告失败");
    } finally {
      setLoading(false);
    }
  }

  async function copyReport() {
    if (!reportMarkdown) return;
    await navigator.clipboard.writeText(reportMarkdown);
    setStatus("报告 Markdown 已复制");
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const [overviewPayload, sessionRows] = await Promise.all([
          api.overview(),
          api.listSessions()
        ]);
        setOverview(overviewPayload);
        setSessions(sessionRows);
        if (sessionRows[0]) {
          await loadSession(sessionRows[0].id);
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "无法连接后端 API");
      }
    }
    void bootstrap();
  }, []);

  const behaviorChart = overview?.charts?.behavior_counts || [];
  const dailyChart = overview?.charts?.daily_trend || [];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-white px-5 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-xl font-semibold">AI 电商运营分析工作台</h1>
            <p className="mt-1 text-sm text-slate-500">可解释 Agent、多轮追问和 Markdown 报告生成</p>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric icon={<Database size={17} />} label="行为记录" value={overview?.records} />
            <Metric icon={<Users size={17} />} label="用户数" value={overview?.users} />
            <Metric icon={<BarChart3 size={17} />} label="商品数" value={overview?.goods} />
            <Metric icon={<Users size={17} />} label="RFM 用户" value={overview?.rfm_users} />
            <Metric icon={<MessageSquare size={17} />} label="语义样本" value={overview?.semantic_sample_count} />
          </div>
        </div>
      </header>

      <div className="grid h-[calc(100vh-105px)] grid-cols-1 gap-4 p-4 lg:grid-cols-[280px_minmax(420px,1fr)_430px]">
        <Panel className="flex min-h-[260px] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <History size={16} />
              历史会话
            </div>
            <Button aria-label="新建会话" title="新建会话" onClick={createSession} disabled={loading}>
              <Plus size={16} />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {sessions.length === 0 ? (
              <p className="px-2 py-4 text-sm text-slate-500">暂无历史会话</p>
            ) : (
              <div className="space-y-2">
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 ${
                      session.id === currentSessionId ? "border-primary bg-sky-50" : "border-border bg-white"
                    }`}
                  >
                    <button className="min-w-0 flex-1 text-left text-sm" onClick={() => loadSession(session.id)}>
                      <span className="block truncate font-medium">{shortTitle(session.title)}</span>
                      <span className="block truncate text-xs text-slate-500">{session.updated_at}</span>
                    </button>
                    <button
                      aria-label="删除会话"
                      title="删除会话"
                      className="rounded-md p-1 text-slate-400 hover:bg-red-50 hover:text-danger"
                      onClick={() => deleteSession(session.id)}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="border-t border-border p-3">
            <p className="mb-2 text-xs font-semibold text-slate-500">示例问题</p>
            <div className="space-y-2">
              {sampleQuestions.map((item) => (
                <button
                  key={item}
                  className="w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:border-primary hover:bg-sky-50"
                  onClick={() => setQuestion(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        </Panel>

        <Panel className="flex min-h-[420px] flex-col overflow-hidden">
          <div className="border-b border-border px-5 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">{currentSession?.title || "运营分析对话"}</h2>
                <p className="text-xs text-slate-500">{status || "结构化指标走 metrics.py，知识问题走本地 RAG"}</p>
              </div>
              <div className="flex items-center gap-2">
                <Button onClick={generateReport} disabled={loading || !currentSessionId}>
                  <FileText size={16} />
                  生成报告
                </Button>
                {loading && <Loader2 className="animate-spin text-primary" size={18} />}
              </div>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-center text-sm text-slate-500">
                选择示例问题或直接输入，开始一轮基于真实数据的分析。
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message) => (
                  <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[82%] whitespace-pre-wrap rounded-md px-4 py-3 text-sm leading-6 ${
                        message.role === "user" ? "bg-primary text-white" : "border border-border bg-muted text-slate-900"
                      }`}
                    >
                      {renderMessageContent(message.content)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="shrink-0 border-t border-border p-4">
            <div className="mb-3 grid max-h-28 gap-2 overflow-y-auto pr-1 lg:grid-cols-[1fr_1fr]">
              <InfoBox title="可信度" body={`${confidence.level}：${confidence.reason}`} tone={confidence.level} />
              <InfoBox title="路由解释" body={routingExplanation || "发送问题后展示本轮为什么调用这些工具。"} />
            </div>
            {contextSummary && (
              <details className="mb-3 rounded-md border border-border bg-white px-3 py-2 text-xs text-slate-600">
                <summary className="cursor-pointer font-medium text-slate-700">多轮上下文摘要</summary>
                <pre className="mt-2 whitespace-pre-wrap">{contextSummary}</pre>
              </details>
            )}
            <div className="flex gap-2">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendQuestion();
                  }
                }}
                className="min-h-11 flex-1 resize-none rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary"
                placeholder="输入问题，例如：那应该优先优化哪个？"
              />
              <Button variant="primary" onClick={() => sendQuestion()} disabled={loading || !question.trim()}>
                <Send size={16} />
                发送
              </Button>
            </div>
          </div>
        </Panel>

        <aside className="grid min-h-[420px] grid-rows-[minmax(230px,1fr)_minmax(230px,1fr)] gap-4 overflow-hidden">
          <Panel className="overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border px-4 py-3 text-sm font-semibold">
              <Wrench size={16} />
              工具结果可视化
            </div>
            <div className="h-[calc(100%-45px)] overflow-y-auto p-3">
              {visualPayloads.length === 0 ? (
                <p className="text-sm text-slate-500">暂无可视化工具结果</p>
              ) : (
                <div className="space-y-3">
                  {visualPayloads.map((payload, index) => (
                    <VisualBlock key={`${payload.tool_name}-${index}`} payload={payload} />
                  ))}
                </div>
              )}

              {toolCalls.length > 0 && (
                <details className="mt-4 rounded-md border border-border bg-white p-3">
                  <summary className="cursor-pointer text-sm font-semibold">查看原始工具数据</summary>
                  <div className="mt-3 space-y-3">
                    {toolCalls.slice(-6).map((tool, index) => (
                      <div key={`${tool.name}-${index}`} className="rounded-md border border-border p-3">
                        <div className="mb-2 text-sm font-semibold">{prettyToolName(tool.name)}</div>
                        <pre className="max-h-44 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
                          {JSON.stringify(tool.result, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </Panel>

          <Panel className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <BookOpen size={16} />
                RAG 来源与报告
              </div>
              {reportMarkdown && (
                <Button onClick={copyReport}>
                  <Copy size={15} />
                  复制
                </Button>
              )}
            </div>
            <div className="h-[calc(100%-45px)] overflow-y-auto p-3">
              {ragSources.length > 0 ? (
                <div className="mb-4 space-y-2">
                  {ragSources.map((source, index) => (
                    <ReferenceCard key={`${source.source}-${index}`} source={source} />
                  ))}
                </div>
              ) : (
                <p className="mb-4 text-sm text-slate-500">RAG 问题会在这里展示参考片段来源</p>
              )}

              {reportMarkdown ? (
                <div className="rounded-md border border-border bg-slate-50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                    <Clipboard size={15} />
                    Markdown 报告预览
                  </div>
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-700">
                    {reportMarkdown}
                  </pre>
                </div>
              ) : (
                <>
                  <ChartBlock title="行为类型分布" data={behaviorChart} xKey="name" yKey="count" type="bar" />
                  <ChartBlock title="近 14 日行为趋势" data={dailyChart} xKey="date" yKey="records" type="bar" />
                </>
              )}

              {overview?.semantic_scope_note && (
                <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                  {overview.semantic_scope_note}
                </p>
              )}
            </div>
          </Panel>
        </aside>
      </div>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: unknown }) {
  return (
    <div className="min-w-28 rounded-md border border-border bg-white px-3 py-2 shadow-panel">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold">{value === undefined ? "-" : formatNumber(value)}</div>
    </div>
  );
}

function InfoBox({ title, body, tone }: { title: string; body: string; tone?: Confidence["level"] }) {
  const toneClass = tone ? confidenceClass(tone) : "border-border bg-white text-slate-700";
  return (
    <div className={`rounded-md border px-3 py-2 text-xs leading-5 ${toneClass}`}>
      <div className="mb-1 font-semibold">{title}</div>
      <div className="max-h-20 overflow-y-auto whitespace-pre-wrap pr-1">{body}</div>
    </div>
  );
}

function VisualBlock({ payload }: { payload: VisualPayload }) {
  if (payload.type === "metric_cards") {
    return (
      <div className="rounded-md border border-border p-3">
        <div className="mb-3 text-sm font-semibold">{payload.title}</div>
        <div className="grid grid-cols-2 gap-2">
          {payload.data.map((item, index) => (
            <div key={index} className="rounded-md bg-muted px-3 py-2">
              <div className="text-xs text-slate-500">{String(item.name)}</div>
              <div className="text-base font-semibold">{formatNumber(item.value)}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (payload.type === "references") {
    return (
      <div className="rounded-md border border-border p-3">
        <div className="mb-3 text-sm font-semibold">{payload.title}</div>
        <div className="space-y-2">
          {(payload.data as unknown as RagSource[]).map((source, index) => (
            <ReferenceCard key={`${source.source}-${index}`} source={source} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <ChartBlock
      title={payload.title}
      data={payload.data}
      xKey={payload.x_key || "name"}
      yKey={payload.y_key || "value"}
      type={payload.type}
    />
  );
}

function ReferenceCard({ source }: { source: RagSource }) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="text-sm font-semibold">
        {source.source} / {source.heading}
      </div>
      <p className="mt-1 line-clamp-4 text-xs leading-5 text-slate-600">{source.content}</p>
    </div>
  );
}

function ChartBlock({
  title,
  data,
  xKey,
  yKey,
  type
}: {
  title: string;
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
  type: "bar" | "line";
}) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="mb-3 text-sm font-semibold">{title}</div>
      <div className="h-44">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">暂无图表数据</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {type === "line" ? (
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line dataKey={yKey} stroke="#0c7da8" strokeWidth={2} dot={false} />
              </LineChart>
            ) : (
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey={yKey} fill="#0c7da8" radius={[3, 3, 0, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default App;
