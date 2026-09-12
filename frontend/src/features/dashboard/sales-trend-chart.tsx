import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DashboardSalesGraphPoint } from "./types";

const BLUE = "#2a78d6";

function formatDay(value: string): string {
  const d = new Date(value);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function money(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}

export function SalesTrendChart({ data }: { data: DashboardSalesGraphPoint[] }) {
  const rows = data.map((row) => ({ date: row.date, total: Number(row.total) }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="salesTrendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={BLUE} stopOpacity={0.25} />
            <stop offset="100%" stopColor={BLUE} stopOpacity={0} />
          </linearGradient>
        </defs>
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
        <Area
          type="monotone"
          dataKey="total"
          name="Sales"
          stroke={BLUE}
          strokeWidth={2}
          fill="url(#salesTrendFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
