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
  AgentTrace,
  Message,
  Overview,
  RagSource,
  Session,
  ToolCall,
  ToolPayload,
  VisualPayload
} from "./types";

const primarySampleQuestions = [
  "给我一份运营概览",
  "用户最常见的购买路径是什么？",
  "哪些类目高流量低转化？",
  "质量问题主要集中在哪些方面？",
  "设计一个浏览到加购流失的 A/B 测试"
];

const moreSampleGroups = [
  {
    title: "诊断",
    questions: ["为什么浏览多但购买少？", "哪个价格带转化率最高？", "核心价值用户和流失用户有什么差异？"]
  },
  {
    title: "预测",
    questions: ["未来 24 小时销售额趋势如何？"]
  },
  {
    title: "口径",
    questions: ["RFM 是什么含义？", "行为漏斗的口径是什么？"]
  }
];

const emptyConfidence: Confidence = {
  level: "中",
  reason: "发送问题后会根据工具结果和知识库来源计算可信度。"
};

const emptyAgentTrace: AgentTrace = {
  intent: "",
  planned_tools: [],
  planning_reason: "发送问题后展示模型如何规划工具。",
  planning_used_llm: false,
  model_status: "",
  evidence_summary: []
};

function formatNumber(value: unknown) {
  if (typeof value !== "number") return String(value ?? "-");
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatCell(value: unknown) {
  if (typeof value === "number") {
    if (value >= 0 && value <= 1) return `${(value * 100).toFixed(2)}%`;
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
  }
  if (Array.isArray(value)) return `${value.length} 项`;
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "-");
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
    user_path_analysis: "用户路径",
    rfm_summary: "RFM 分层",
    rfm_behavior_differences: "RFM 行为差异",
    hourly_trend: "小时趋势",
    daily_trend: "日期趋势",
    sales_forecast: "销售额预测",
    area_summary: "地区分析",
    device_conversion: "设备转化",
    comment_keywords: "评论关键词",
    comment_semantic: "评论语义",
    semantic_linkage: "语义联动",
    top_categories: "品类分析",
    operation_matrix: "运营矩阵",
    price_band_analysis: "价格带分析",
    ab_test_plan: "A/B 测试方案",
    rag: "知识库 RAG"
  };
  return names[name] || name;
}

function confidenceClass(level: Confidence["level"]) {
  if (level === "高") return "border-success/40 bg-emerald-50 text-emerald-900";
  if (level === "中") return "border-accent/45 bg-amber-50 text-amber-900";
  return "border-danger/35 bg-red-50 text-red-900";
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
  const [agentTrace, setAgentTrace] = useState<AgentTrace>(emptyAgentTrace);
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
    setAgentTrace(emptyAgentTrace);
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
      setAgentTrace(emptyAgentTrace);
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
    setStatus("Agent 正在让模型规划工具，并计算真实指标");

    try {
      const response: ChatResponse = await api.chat(trimmed, currentSessionId);
      setCurrentSessionId(response.session_id);
      await refreshSessions(response.session_id);
      setToolCalls(response.tools);
      setRagSources(response.rag_sources);
      setVisualPayloads(response.visual_payloads || []);
      setRoutingExplanation(response.routing_explanation || "");
      setConfidence(response.confidence || emptyConfidence);
      setAgentTrace(response.agent_trace || emptyAgentTrace);
      setContextSummary(response.context_summary || "");
      setReportMarkdown("");
      setStatus(response.error || (response.used_llm ? "已使用模型规划工具并生成回答" : "模型未完成回答，可查看工具结果"));
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
    <main className="min-h-screen bg-transparent text-foreground">
      <header className="border-b border-border bg-[#fffdf8]/95 px-5 py-4 shadow-[0_1px_0_rgba(255,255,255,0.8)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-950">AI 电商运营分析工作台</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <span>运营诊断、短期预测、实验方案与可解释 Agent</span>
              <span
                className={`rounded-md border px-2 py-0.5 text-xs ${
                  overview?.model_status?.configured
                    ? "border-success/30 bg-emerald-50 text-emerald-800"
                    : "border-accent/40 bg-amber-50 text-amber-800"
                }`}
              >
                {overview?.model_status?.configured ? "模型已配置" : "模型未配置"}
                {overview?.model_status?.model ? ` · ${overview.model_status.model}` : ""}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
            <Metric icon={<Database size={17} />} label="行为记录" value={overview?.records} />
            <Metric icon={<Users size={17} />} label="用户数" value={overview?.users} />
            <Metric icon={<BarChart3 size={17} />} label="商品数" value={overview?.goods} />
            <Metric icon={<Users size={17} />} label="RFM 用户" value={overview?.rfm_users} />
            <Metric icon={<MessageSquare size={17} />} label="语义样本" value={overview?.semantic_sample_count} />
          </div>
        </div>
      </header>

      <div className="grid h-[calc(100vh-105px)] grid-cols-1 gap-4 p-4 lg:grid-cols-[270px_minmax(520px,1fr)_460px]">
        <Panel className="flex min-h-[260px] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border bg-[#fbf7ef] px-4 py-3">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.08em] text-slate-600">
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
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 transition ${
                      session.id === currentSessionId ? "border-primary bg-[#e7f0ec]" : "border-transparent bg-transparent hover:border-border hover:bg-[#f8f3ea]"
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
          <div className="border-t border-border bg-[#fbf7ef] p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.08em] text-slate-500">核心问题</p>
            <div className="space-y-2">
              {primarySampleQuestions.map((item) => (
                <button
                  key={item}
                  className="w-full rounded-md border border-border bg-[#fffdf8] px-3 py-2 text-left text-sm leading-5 text-slate-800 transition hover:border-primary hover:bg-[#edf5f1]"
                  onClick={() => setQuestion(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <details className="mt-3 rounded-md border border-border bg-[#fffdf8] px-3 py-2">
              <summary className="cursor-pointer text-xs font-semibold text-slate-500">更多示例</summary>
              <div className="mt-3 space-y-3">
                {moreSampleGroups.map((group) => (
                  <div key={group.title}>
                    <div className="mb-1 text-xs font-semibold text-slate-400">{group.title}</div>
                    <div className="space-y-2">
                      {group.questions.map((item) => (
                        <button
                          key={item}
                          className="w-full rounded-md border border-border px-3 py-2 text-left text-sm transition hover:border-primary hover:bg-[#edf5f1]"
                          onClick={() => setQuestion(item)}
                        >
                          {item}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          </div>
        </Panel>

        <Panel className="flex min-h-[420px] flex-col overflow-hidden">
          <div className="border-b border-border bg-[#fbf7ef] px-5 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-slate-950">{currentSession?.title || "运营分析对话"}</h2>
                <p className="text-xs text-slate-500">{status || "模型负责规划与分析，工具负责计算真实指标"}</p>
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
          <div className="min-h-0 flex-1 overflow-y-auto bg-[#f8f4ec] px-5 py-4">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-center text-sm text-slate-500">
                选择示例问题或直接输入，开始一轮基于真实数据的分析。
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message) => (
                  <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[86%] whitespace-pre-wrap rounded-md px-4 py-3 text-sm leading-6 ${
                        message.role === "user"
                          ? "bg-slate-900 text-white shadow-sm"
                          : "border border-border border-l-[4px] border-l-primary bg-[#fffdf8] text-slate-900 shadow-[0_8px_22px_rgba(30,35,42,0.06)]"
                      }`}
                    >
                      {renderMessageContent(message.content)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="shrink-0 border-t border-border bg-[#fffdf8] p-4">
            <div className="mb-3 grid max-h-28 gap-2 overflow-y-auto pr-1 lg:grid-cols-[1fr_1fr]">
              <InfoBox title="可信度" body={`${confidence.level}：${confidence.reason}`} tone={confidence.level} />
              <InfoBox title="路由解释" body={routingExplanation || "发送问题后展示本轮为什么调用这些工具。"} />
            </div>
            <AgentTraceBlock trace={agentTrace} />
            {contextSummary && (
              <details className="mb-3 rounded-md border border-border bg-[#fffdf8] px-3 py-2 text-xs text-slate-600">
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
                className="min-h-11 flex-1 resize-none rounded-md border border-border bg-[#fffdf8] px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/10"
                placeholder="输入问题，例如：那应该优先优化哪个？"
              />
              <Button variant="primary" onClick={() => sendQuestion()} disabled={loading || !question.trim()}>
                <Send size={16} />
                发送
              </Button>
            </div>
          </div>
        </Panel>

        <aside className="grid min-h-[420px] grid-rows-[minmax(250px,1.08fr)_minmax(230px,0.92fr)] gap-4 overflow-hidden">
          <Panel className="overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border bg-[#fbf7ef] px-4 py-3 text-sm font-bold text-slate-950">
              <Wrench size={16} />
              工具结果可视化
            </div>
            <div className="h-[calc(100%-45px)] overflow-y-auto p-3">
              {visualPayloads.length === 0 ? (
                <p className="rounded-md border border-dashed border-border bg-[#fbf7ef] px-3 py-5 text-center text-sm text-slate-500">
                  暂无可视化工具结果
                </p>
              ) : (
                <div className="space-y-3">
                  {visualPayloads.map((payload, index) => (
                    <VisualBlock key={`${payload.tool_name}-${index}`} payload={payload} />
                  ))}
                </div>
              )}

              {toolCalls.length > 0 && (
                <details className="mt-4 rounded-md border border-border bg-[#fffdf8] p-3">
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
            <div className="flex items-center justify-between border-b border-border bg-[#fbf7ef] px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-950">
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
                <p className="mb-4 rounded-md border border-dashed border-border bg-[#fbf7ef] px-3 py-4 text-center text-sm text-slate-500">
                  RAG 问题会在这里展示参考片段来源
                </p>
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
    <div className="min-w-28 rounded-md border border-border bg-[#fffdf8] px-3 py-2 shadow-[0_4px_14px_rgba(30,35,42,0.05)]">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-lg font-bold text-slate-950">{value === undefined ? "-" : formatNumber(value)}</div>
    </div>
  );
}

function AgentTraceBlock({ trace }: { trace: AgentTrace }) {
  const hasTrace = Boolean(trace.planned_tools.length || trace.evidence_summary.length || trace.intent);
  if (!hasTrace) return null;

  return (
    <details className="mb-3 rounded-md border border-primary/25 bg-[#edf5f1] px-3 py-2 text-xs text-slate-700">
      <summary className="cursor-pointer font-semibold text-slate-900">Agent Trace</summary>
      <div className="mt-3 grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-2">
          <div>
            <span className="font-semibold">意图：</span>
            {trace.intent || "-"}
          </div>
          <div>
            <span className="font-semibold">规划：</span>
            {trace.planning_used_llm ? "模型规划" : "规则兜底"}
          </div>
          <div>
            <span className="font-semibold">工具：</span>
            {trace.planned_tools.length ? trace.planned_tools.join(" / ") : "-"}
          </div>
          {trace.planning_reason && <div className="leading-5 text-slate-600">{trace.planning_reason}</div>}
        </div>
        <div className="space-y-1">
          {trace.evidence_summary.slice(0, 4).map((fact, index) => (
            <div key={`${fact.source}-${fact.label}-${index}`} className="rounded-md border border-white/70 bg-[#fffdf8] px-2 py-1.5">
              <span className="font-semibold text-slate-900">{fact.label}</span>
              <span>：{formatCell(fact.value)}</span>
              <span className="ml-1 text-slate-500">({fact.source})</span>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}

function InfoBox({ title, body, tone }: { title: string; body: string; tone?: Confidence["level"] }) {
  const toneClass = tone ? confidenceClass(tone) : "border-border bg-[#fffdf8] text-slate-700";
  return (
    <div className={`rounded-md border px-3 py-2 text-xs leading-5 shadow-[0_1px_0_rgba(255,255,255,0.7)_inset] ${toneClass}`}>
      <div className="mb-1 font-semibold">{title}</div>
      <div className="max-h-20 overflow-y-auto whitespace-pre-wrap pr-1">{body}</div>
    </div>
  );
}

function VisualBlock({ payload }: { payload: VisualPayload }) {
  if (payload.type === "metric_cards") {
    return (
      <div className="rounded-md border border-border bg-[#fffdf8] p-3">
        <div className="mb-3 text-sm font-bold text-slate-950">{payload.title}</div>
        <div className="grid grid-cols-2 gap-2">
          {payload.data.map((item, index) => (
            <div key={index} className="rounded-md border border-border bg-[#fbf7ef] px-3 py-2">
              <div className="text-xs text-slate-500">{String(item.name)}</div>
              <div className="text-base font-bold text-slate-950">{formatNumber(item.value)}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (payload.type === "references") {
    return (
      <div className="rounded-md border border-border bg-[#fffdf8] p-3">
        <div className="mb-3 text-sm font-bold text-slate-950">{payload.title}</div>
        <div className="space-y-2">
          {(payload.data as unknown as RagSource[]).map((source, index) => (
            <ReferenceCard key={`${source.source}-${index}`} source={source} />
          ))}
        </div>
      </div>
    );
  }

  if (payload.type === "table" || payload.type === "matrix") {
    return <TableBlock title={payload.title} data={payload.data} columns={payload.columns || []} compact={payload.type === "matrix"} />;
  }

  if (payload.type === "plan") {
    return <PlanBlock title={payload.title} data={payload.data[0] || {}} />;
  }

  return (
    <ChartBlock
      title={payload.title}
      data={payload.data}
      xKey={payload.x_key || "name"}
      yKey={payload.y_key || "value"}
      type={payload.type === "line" ? "line" : "bar"}
    />
  );
}

function TableBlock({
  title,
  data,
  columns,
  compact
}: {
  title: string;
  data: Array<Record<string, unknown>>;
  columns: Array<{ key: string; label: string }>;
  compact?: boolean;
}) {
  const visibleColumns = columns.length > 0 ? columns : Object.keys(data[0] || {}).slice(0, 5).map((key) => ({ key, label: key }));
  return (
    <div className="rounded-md border border-border bg-[#fffdf8] p-3">
      <div className="mb-3 text-sm font-bold text-slate-950">{title}</div>
      {data.length === 0 ? (
        <div className="rounded-md bg-[#fbf7ef] px-3 py-4 text-center text-sm text-slate-500">暂无表格数据</div>
      ) : (
        <div className="max-h-72 overflow-auto">
          <table className="w-full min-w-[360px] border-collapse text-left text-xs">
            <thead className="sticky top-0 bg-[#f3ece0] text-slate-600">
              <tr>
                {visibleColumns.map((column) => (
                  <th key={column.key} className="border-b border-border px-2 py-2 font-semibold">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.slice(0, compact ? 16 : 20).map((row, index) => (
                <tr key={index} className="border-b border-[#eee5d8] last:border-0 hover:bg-[#fbf7ef]">
                  {visibleColumns.map((column) => (
                    <td key={column.key} className="max-w-44 px-2 py-2 align-top text-slate-700">
                      <span className="line-clamp-3">{formatCell(row[column.key])}</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PlanBlock({ title, data }: { title: string; data: Record<string, unknown> }) {
  const groups = Array.isArray(data.groups) ? (data.groups as Array<Record<string, unknown>>) : [];
  const metrics = Array.isArray(data.metrics) ? (data.metrics as Array<Record<string, unknown>>) : [];
  return (
    <div className="rounded-md border border-border bg-[#fffdf8] p-3">
      <div className="mb-3 text-sm font-bold text-slate-950">{title}</div>
      <div className="space-y-3 text-xs leading-5 text-slate-700">
        <div className="rounded-md border border-primary/20 bg-[#edf5f1] px-3 py-2">
          <div className="font-semibold text-slate-900">实验目标</div>
          <div>{formatCell(data.experiment_goal)}</div>
        </div>
        <div>
          <div className="font-semibold text-slate-900">实验假设</div>
          <div>{formatCell(data.hypothesis)}</div>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {groups.map((group, index) => (
            <div key={index} className="rounded-md border border-border bg-[#fbf7ef] px-3 py-2">
              <div className="font-semibold text-slate-900">{formatCell(group.group)}</div>
              <div>{formatCell(group.design)}</div>
            </div>
          ))}
        </div>
        <div>
          <div className="font-semibold text-slate-900">核心指标</div>
          <div className="mt-1 flex flex-wrap gap-2">
            {metrics.map((metric, index) => (
              <span key={index} className="rounded-md border border-border bg-[#fbf7ef] px-2 py-1">
                {formatCell(metric.name)} · {formatCell(metric.role)}
              </span>
            ))}
          </div>
        </div>
        <div className="grid gap-2">
          <div>
            <span className="font-semibold text-slate-900">分流：</span>
            {formatCell(data.traffic_split)}
          </div>
          <div>
            <span className="font-semibold text-slate-900">观察周期：</span>
            {formatCell(data.observation_period)}
          </div>
          <div>
            <span className="font-semibold text-slate-900">成功标准：</span>
            {formatCell(data.success_criteria)}
          </div>
        </div>
        {Boolean(data.limit_note) && <div className="rounded-md border border-accent/25 bg-amber-50 px-3 py-2 text-amber-900">{formatCell(data.limit_note)}</div>}
      </div>
    </div>
  );
}

function ReferenceCard({ source }: { source: RagSource }) {
  return (
    <div className="rounded-md border border-border bg-[#fffdf8] p-3">
      <div className="text-sm font-bold text-slate-950">
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
    <div className="rounded-md border border-border bg-[#fffdf8] p-3">
      <div className="mb-3 text-sm font-bold text-slate-950">{title}</div>
      <div className="h-44">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">暂无图表数据</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {type === "line" ? (
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6dccd" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line dataKey={yKey} stroke="#1c7479" strokeWidth={2} dot={false} />
              </LineChart>
            ) : (
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6dccd" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey={yKey} fill="#1c7479" radius={[3, 3, 0, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default App;
