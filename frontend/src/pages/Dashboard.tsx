import { useEffect, useState } from "react";
import {
  getDashboardStats,
  getCallVolume,
  getCallOutcome,
  getAgentPerformanceRanking,
  getCallDuration,
  getBusinessPerformance,
  getAgentPositiveRate,
  getTechnicalMetrics,
} from "@/lib/api";
import {
  ResponsiveContainer,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Legend,
  LineChart,
  Line,
} from "recharts";

// ─────────────────────────── helpers ───────────────────────────
function fmtDuration(sec: number | null | undefined): string {
  const s = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function formatChange(value:number | undefined){

  if(value === undefined || value === null){
    return "0.0%";
  }

  const num = Number(value);

  if(num === 0){
    return "0.0%";
  }

  return `${num > 0 ? "+" : ""}${num.toFixed(1)}%`;
}



// ─────────────────────────── small components ───────────────────────────
function Kpi({
  label,
  value,
  change,
  sub,
  positive = true,
}: {
  label: string;
  value: string;
  change?: string;
  sub?: string;
  positive?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">

      <p className="text-sm text-slate-500">
        {label}
      </p>

      <p className="mt-3 text-2xl font-bold text-slate-900">
        {value}
      </p>

      {change && (
        <p
          className={`mt-3 text-sm font-medium ${
            positive
              ? "text-emerald-600"
              : "text-red-500"
          }`}
        >
          {change}
        </p>
      )}

      {sub && (
        <p className="text-sm text-slate-400">
          {sub}
        </p>
      )}

    </div>
  );
}


// ─────────────────────────── types ───────────────────────────
interface Stats {

  today_calls:number;
  today_calls_change:number;

  connected_calls:number;
  connected_calls_change:number;

  answer_rate:number;


  positive_calls:number;
  positive_calls_change:number;
  positive_rate:number;


  neutral_calls:number;
  neutral_calls_change:number;
  neutral_rate:number;


  negative_calls:number;
  negative_calls_change:number;
  negative_rate:number;


  active_calls:number;

  transfer_rate:number;

  today_avg_duration_seconds:number;

  ai_cost_today:number;
}



interface TechnicalMetrics {

  avg_call_duration_seconds:number;

  first_call_resolution:number;

  latency_ms:number;

  api_uptime:number;

  transcription_accuracy:number;

  webhook_delivery_rate:number;

}


// ─────────────────────────── page ───────────────────────────
export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [activeTab, setActiveTab] = useState("Business Performance");


  // Line chart data (replace later with API if available)
  const [trendData,setTrendData] = useState<{ day:string; calls:number;} []>([]);
  const [pieData,setPieData] = useState<{ name:string; value:number; color:string;} []>([]);
  const [agentRanking,setAgentRanking] = useState<{name:string; value:number;}[]>([]);
  const [durationData,setDurationData] = useState<{ hour:string; seconds:number;}[]>([]);
  const [business,setBusiness] = useState<any>(null);
  const [agentQualityData,setAgentQualityData] = useState<any[]>([]);
  const [technicalMetrics,setTechnicalMetrics] = useState<TechnicalMetrics | null>(null);







  useEffect(() => {
    const loadFast = async () => {
      try {
        const [statsRes, trendRes, outcomeRes, rankingRes, durationRes, positiveRateRes] = await Promise.all([
          getDashboardStats(),
          getCallVolume(),
          getCallOutcome(),
          getAgentPerformanceRanking(),
          getCallDuration(),
          getAgentPositiveRate(),
        ]);

        setStats(statsRes.data);
        setTrendData(trendRes.data);
        setPieData(outcomeRes.data);
        setAgentRanking(rankingRes.data);
        setDurationData(durationRes.data);
        setAgentQualityData(positiveRateRes.data);
      } catch (err) {
        console.error(err);
      }
    };

    const loadSlow = async () => {
      try {
        const [ businessRes, technicalRes] = await Promise.all([
          getBusinessPerformance(),
          getTechnicalMetrics(),
        ]);

        setBusiness(businessRes.data);
        setTechnicalMetrics(technicalRes.data);
      } catch (err) {
        console.error(err);
      }
    };

    loadFast();
    loadSlow();

    const fastTimer = setInterval(loadFast, 5000);
    const slowTimer = setInterval(loadSlow, 30000);

    return () => {
      clearInterval(fastTimer);
      clearInterval(slowTimer);
    };
  }, []);

return (
  <div className="space-y-8 px-2 pb-8">
  {/* ================= HEADER ================= */}

  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
    <div>
      <h1 className="text-2xl font-bold text-slate-900">
        Dashboard
      </h1>

      <p className="mt-2 text-slate-500">
        Operations overview • Live AI Call Analytics
      </p>
    </div>

    <div className="flex gap-3">
      {/* <button
        onClick={() => window.location.reload()}
        className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm shadow-sm hover:bg-slate-50"
      >
        <RefreshCw size={16} />
        Refresh
      </button>

      <button
        className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm shadow-sm hover:bg-slate-50"
      >
        <Download size={16} />
        Export
      </button> */}
    </div>
  </div>

  {/* ================= KPI CARDS ================= */}

  <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">


    <Kpi
      label="Calls Today"
      value={stats?.today_calls.toLocaleString() ?? "0"}
      change={formatChange(stats?.today_calls_change)}
      sub="vs. yesterday"
      positive={(stats?.today_calls_change ?? 0) >= 0}
    />


    <Kpi
      label="Connected Calls"
      value={stats?.connected_calls.toLocaleString() ?? "0"}
      change={formatChange(stats?.connected_calls_change)}
      sub={`${stats?.answer_rate ?? 0}% connect rate`}
      positive={(stats?.connected_calls_change ?? 0) >= 0}
    />


    <Kpi
      label="Positive Calls"
      value={stats?.positive_calls.toLocaleString() ?? "0"}
      change={formatChange(stats?.positive_calls_change)}
      sub={`${stats?.positive_rate ?? 0}% of connected`}
      positive={(stats?.positive_calls_change ?? 0) >= 0}
    />


    <Kpi
      label="Neutral Calls"
      value={stats?.neutral_calls.toLocaleString() ?? "0"}
      change={formatChange(stats?.neutral_calls_change)}
      sub={`${stats?.neutral_rate ?? 0}% of connected`}
      positive={(stats?.neutral_calls_change ?? 0) >= 0}
    />


    <Kpi
      label="Negative Calls"
      value={stats?.negative_calls.toLocaleString() ?? "0"}
      change={formatChange(stats?.negative_calls_change)}
      sub={`${stats?.negative_rate ?? 0}% of connected`}
      positive={(stats?.negative_calls_change ?? 0) <= 0}
    />


    </div>


  {/* ================= CHART SECTION ================= */}

  <div className="grid gap-6 xl:grid-cols-3">
    {/* ================= CALL VOLUME TREND ================= */}

<div className="xl:col-span-2 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">

  <div className="mb-6 flex items-center justify-between">

    <div>
      <h2 className="text-l font-semibold text-slate-900">
        Call Volume Trend
      </h2>

      <p className="text-sm text-slate-500">
        Last 14 Days
      </p>
    </div>

    <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
      Live
    </span>

  </div>

  <ResponsiveContainer width="100%" height={340}>

    <AreaChart data={trendData}>

      <defs>

        <linearGradient
          id="lineFill"
          x1="0"
          y1="0"
          x2="0"
          y2="1"
        >
          <stop
            offset="0%"
            stopColor="#7C3AED"
            stopOpacity={0.35}
          />

          <stop
            offset="100%"
            stopColor="#7C3AED"
            stopOpacity={0.02}
          />

        </linearGradient>

      </defs>

      <CartesianGrid
        strokeDasharray="3 3"
        vertical={false}
      />

      <XAxis
        dataKey="day"
        tick={{ fontSize: 12 }}
      />

      <YAxis tick={{ fontSize: 12 }} />

      <Tooltip />

        <Area
          type="monotone"
          dataKey="calls"
          stroke="#7C3AED"
          fill="url(#lineFill)"
          strokeWidth={3}
        />

    </AreaChart>

  </ResponsiveContainer>

</div>

{/* ================= DONUT CHART ================= */}

<div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">

  <h2 className="text-l font-semibold text-slate-900">
    Call Outcome Distribution
  </h2>

  <p className="mb-6 text-sm text-slate-500">
    Toady - Connected Calls
  </p>

  <div className="relative">

  <ResponsiveContainer
    width="100%"
    height={260}
  >

    <PieChart>

      <Pie
        data={
          pieData.some(x => x.value > 0)
            ? pieData
            : [{ name: "No Data", value: 1, color: "#E2E8F0" }]
        }
        dataKey="value"
        innerRadius={60}
        outerRadius={90}
        paddingAngle={5}
      >

        {
          (pieData.some(x => x.value > 0)
            ? pieData
            : [{ name:"No Data", value:1, color:"#E2E8F0" }]
          ).map((item)=>(
            <Cell
              key={item.name}
              fill={item.color}
            />
          ))
        }

      </Pie>

      <Tooltip />

    </PieChart>

  </ResponsiveContainer>


  {!pieData.some(x=>x.value>0) && (
    <div className="absolute inset-0 flex items-center justify-center">
      <span className="text-sm text-slate-400">
        No calls
      </span>
    </div>
  )}

</div>

  <div className="mt-5 space-y-4">

    {pieData.map((item) => (

      <div
        key={item.name}
        className="flex items-center justify-between"
      >

        <div className="flex items-center gap-3">

          <span
            className="h-3 w-3 rounded-full"
            style={{
              backgroundColor: item.color,
            }}
          />

          <span className="text-sm text-slate-700">
            {item.name}
          </span>

        </div>

        <div className="text-sm font-semibold">
          {item.value}
        </div>

      </div>

    ))}

  </div>

</div>

</div>



{/* ================= ANALYTICS SECTION ================= */}

<div className="grid gap-6 xl:grid-cols-2">

  {/* Agent Ranking */}

  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">

    <h2 className="text-sm font-semibold text-slate-900">
      Agent Performance Ranking
    </h2>

    <p className="text-xs text-slate-500">
      Positive call rate today
    </p>


    <ResponsiveContainer width="100%" height={260}>

      <BarChart
        data={agentRanking}
        layout="vertical"
        margin={{
          left: 20,
          right: 20
        }}
      >

        <CartesianGrid
          strokeDasharray="3 3"
          horizontal={false}
        />

        <XAxis
          type="number"
          tick={{fontSize:12}}
          domain={[0,24]}
        />

        <YAxis
          type="category"
          dataKey="name"
          tick={{fontSize:12}}
          width={60}
        />

        <Tooltip />

        <Bar
          dataKey="value"
          fill="#6D28D9"
          radius={[0,5,5,0]}
          barSize={22}
        />

      </BarChart>

    </ResponsiveContainer>

  </div>



  {/* Duration Analysis */}

  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">

    <h2 className="text-sm font-semibold text-slate-900">
      Call Duration Analysis
    </h2>

    <p className="text-xs text-slate-500">
      Average duration by hour (seconds)
    </p>


    <ResponsiveContainer width="100%" height={260}>

      <BarChart data={durationData}>

        <CartesianGrid
          strokeDasharray="3 3"
          vertical={false}
        />


        <XAxis
          dataKey="hour"
          tick={{fontSize:12}}
        />


        <YAxis
          tick={{fontSize:12}}
          tickFormatter={(v)=>`${v}s`}
        />


        <Tooltip
          formatter={(v)=>`${v}s`}
        />


        <Bar
          dataKey="seconds"
          fill="#A78BFA"
          radius={[5,5,0,0]}
        />

      </BarChart>

    </ResponsiveContainer>

  </div>


</div>

{/* ================= BUSINESS PERFORMANCE ================= */}

<div className="space-y-5">


  {/* ================= TABS ================= */}

  <div className="space-y-5">

    <div className="inline-flex rounded-full bg-slate-100 p-1">
      {[
        "Business Performance",
        "Agent Quality",
        "Technical Metrics",
      ].map((tab) => (
        <button
          key={tab}
          onClick={() => setActiveTab(tab)}
          className={`rounded-full px-5 py-2 text-sm transition-all ${
            activeTab === tab
              ? "bg-white shadow border border-slate-200 text-slate-900"
              : "text-slate-500"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>

    {/* Business Performance */}
    {activeTab === "Business Performance" && (
      <>
        {/* Chart */}

          <div className="rounded-3xl border border-slate-200 bg-white px-8 p-6 shadow-sm">

            <div className="mb-6">

              <h2 className="text-l font-semibold text-slate-900">
                Monthly Call Outcomes
              </h2>

              <p className="text-sm text-slate-500">

                Positive / Neutral / Negative — 
                {
                  business?.monthly_outcomes?.length
                  ?
                  `${business.monthly_outcomes[0].month} ${
                      business.monthly_outcomes[0].year
                  } - ${
                      business.monthly_outcomes[
                        business.monthly_outcomes.length-1
                      ].month
                  } ${
                      business.monthly_outcomes[
                        business.monthly_outcomes.length-1
                      ].year
                  }`
                  :
                  "Loading..."
                }

                </p>


            </div>

            <ResponsiveContainer width="100%" height={330}>

              <BarChart
                data={business?.monthly_outcomes ?? []}
                margin={{
                  top: 10,
                  left: 10,
                  right: 10,
                  bottom: 0,
                }}
              >

                <CartesianGrid
                  vertical={false}
                  stroke="#E5E7EB"
                  strokeDasharray="3 3"
                />

                <XAxis
                  dataKey="month"
                  axisLine={false}
                  tickLine={false}
                  tick={{ 
                    fill:"#64748B",
                    fontSize:12
                  }}
                />

                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{
                    fill:"#64748B",
                    fontSize:12
                  }}
                  />


                <Tooltip />


                <Bar
                  dataKey="Positive"
                  stackId="outcome"
                  fill="#6D28D9"
                  barSize={82}
                />

                <Bar
                  dataKey="Neutral"
                  stackId="outcome"
                  fill="#8B5CF6"
                />

                <Bar
                  dataKey="Negative"
                  stackId="outcome"
                  fill="#C4B5FD"
                  radius={[
                    6,
                    6,
                    0,
                    0
                  ]}
                />


              </BarChart>


            </ResponsiveContainer>

          </div>

          {/* KPI Cards */}

          <div className="grid gap-5 md:grid-cols-3">

            {/* Total Calls */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6">

              <p className="text-sm text-slate-500">
                Total Calls (YTD)
              </p>

              <h2 className="mt-2 text-xl font-bold text-slate-900">
                {business?.kpis?.total_calls?.toLocaleString() ?? 0}
              </h2>

              <p className="mt-2 text-sm font-medium text-emerald-600">
                Year To Date
              </p>

            </div>


            {/* Positive Rate */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6">

              <p className="text-sm text-slate-500">
                Positive Rate (YTD)
              </p>

              <h2 className="mt-2 text-xl font-bold text-slate-900">
                {business?.kpis?.positive_rate ?? 0}%
              </h2>

              <p className="mt-2 text-sm font-medium text-emerald-600">
                Based on sentiment score
              </p>

            </div>


            {/* Avg Duration */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6">

              <p className="text-sm text-slate-500">
                Avg Call Duration
              </p>

              <h2 className="mt-2 text-xl font-bold text-slate-900">
                {fmtDuration(
                  business?.kpis?.avg_call_duration_seconds
                )}
              </h2>

              <p className="mt-2 text-sm font-medium text-emerald-600">
                Average duration
              </p>

            </div>


          </div>
      </>
    )}

    {/* Agent Quality */}
    {activeTab === "Agent Quality" && (
      <>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">

          <h2 className="mb-6 text-l font-semibold text-slate-900">
              Agent Positive Rate — Last 7 Days
          </h2>

          <ResponsiveContainer
              width="100%"
              height={330}
          >

              <LineChart
                  data={agentQualityData}
                  margin={{
                      top: 10,
                      right: 20,
                      left: 10,
                      bottom: 20,
                  }}
              >

                  <CartesianGrid
                      vertical={false}
                      stroke="#E5E7EB"
                      strokeDasharray="3 3"
                  />

                  <XAxis
                      dataKey="day"
                      axisLine={false}
                      tickLine={false}
                      tick={{
                          fontSize: 12,
                          fill: "#64748B",
                      }}
                  />

                  <YAxis
                      axisLine={false}
                      tickLine={false}
                      domain={[0,100]}
                      ticks={[0,25,50,75,100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{
                          fontSize: 12,
                          fill: "#64748B",
                      }}
                  />

                  <Tooltip
                      formatter={(v) => [`${v}%`, "Positive Rate"]}
                  />

                  <Legend
                      verticalAlign="bottom"
                      align="left"
                      iconType="circle"
                      wrapperStyle={{
                          paddingTop: 20,
                      }}
                  />

                  {
                    Object.keys(agentQualityData[0] || {})
                    .filter(key => key !== "day")
                    .map((agent,index)=>(
                        <Line
                          key={agent}
                          type="monotone"
                          dataKey={agent}
                          stroke={
                            [
                              "#6D28D9",
                              "#8B5CF6",
                              "#9F86FF",
                              "#B8A7FF",
                              "#C4B5FD"
                            ][index % 5]
                          }
                          strokeWidth={2.5}
                          dot={false}
                        />
                    ))
                    }


              </LineChart>

          </ResponsiveContainer>

      </div>

      </>
    )}

    {/* Technical Metrics */}
    {activeTab === "Technical Metrics" && (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">

        {[
          {
            title:"Avg Call Duration",
            value:fmtDuration(
              technicalMetrics?.avg_call_duration_seconds
            ),
            change:"Today"
          },

          {
            title:"First Call Resolution",
            value:
            `${technicalMetrics?.first_call_resolution ?? 0}%`,
            change:"Today"
          },

          {
            title:"Latency (avg)",
            value:
            `${technicalMetrics?.latency_ms ?? 0}ms`,
            change:"Today"
          },


          {
            title:"API Uptime",
            value:
            `${technicalMetrics?.api_uptime ?? 0}%`,
            change:"Today"
          },


          {
            title:"Transcription Accuracy",
            value:
            `${technicalMetrics?.transcription_accuracy ?? 0}%`,
            change:"Today"
          },


          {
            title:"Webhook Delivery Rate",
            value:
            `${technicalMetrics?.webhook_delivery_rate ?? 0}%`,
            change:"Today"
          }

          ].map((item) => (
          <div
            key={item.title}
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-sm text-slate-500">
              {item.title}
            </p>

            <h3 className="mt-3 text-2xl font-bold text-slate-900">
              {item.value}
            </h3>

            <p className="mt-2 text-sm font-medium text-slate-500">
              {item.change}
            </p>

          </div>
        ))}

      </div>
    )}
  </div>
</div>
</div>
);
 }