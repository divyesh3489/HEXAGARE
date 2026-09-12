import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DashboardSalesGraphPoint } from "./types";

const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

function formatDay(value: string): string {
  const d = new Date(value);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function money(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}

/** Title-cases a channel code (``AMAZON`` -> ``Amazon``) for the legend --
 * channel codes/names are never hardcoded, they come from whatever
 * SalesChannel rows exist. */
function channelLabel(code: string): string {
  return code.charAt(0) + code.slice(1).toLowerCase();
}

export function ChannelComparisonChart({ data }: { data: DashboardSalesGraphPoint[] }) {
  const channels = Object.keys(data[0]?.by_channel ?? {}).sort();
  const rows = data.map((row) => ({
    date: row.date,
    ...Object.fromEntries(channels.map((code) => [code, Number(row.by_channel[code] ?? 0)])),
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={formatDay}
          tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          axisLine={{ stroke: "hsl(var(--border))" }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis
          tickFormatter={money}
          tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          axisLine={false}
          tickLine={false}
          width={64}
        />
        <Tooltip
          formatter={(value) => money(Number(value))}
          labelFormatter={(label) => formatDay(String(label))}
          contentStyle={{
            background: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "var(--radius)",
            fontSize: 12,
          }}
        />
        <Legend
          formatter={(value: string) => channelLabel(value)}
          wrapperStyle={{ fontSize: 12 }}
        />
        {channels.map((code, i) => (
          <Line
            key={code}
            type="monotone"
            dataKey={code}
            name={code}
            stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
