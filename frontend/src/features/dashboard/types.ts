export interface DashboardSales {
  total_sales: string;
  today_sales: string;
  weekly_sales: string;
  monthly_sales: string;
  yearly_sales: string;
  by_channel: Record<string, string>;
  total_orders: number;
  products_sold: number;
  units_sold: number;
}

export interface DashboardInventory {
  total_inventory: number;
  total_serialized_units: number;
  available_units: number;
  reserved_units: number;
  in_transit_units: number;
  sold_units: number;
  returned_units: number;
  damaged_units: number;
  lost_units: number;
  low_stock_products: number;
  out_of_stock_products: number;
  overstock_products: number;
}

export interface DashboardFinance {
  date_from: string;
  date_to: string;
  revenue: string;
  taxable_sales: string;
  gst_collected: string;
  product_cost: string;
  amazon_fees: string;
  shipping: string;
  advertising: string;
  packaging: string;
  other_expenses: string;
  gross_profit: string;
  net_profit: string;
  profit_margin: string;
}

export interface DashboardSalesGraphPoint {
  date: string;
  total: string;
  by_channel: Record<string, string>;
}

export interface DashboardTopSellingRow {
  id: number;
  name: string;
  units_sold: number;
  taxable_sales: string;
}

export interface DashboardLowStockRow {
  sku: string;
  product_name: string;
  available: number;
  type: "low_stock" | "out_of_stock";
}

export interface DashboardRecentOrder {
  id: number;
  channel: string;
  customer_name: string | null;
  grand_total: string;
  status: string;
  created_at: string;
}

export interface DashboardRecentReturn {
  id: number;
  sale_id: number;
  reason: string;
  refund_total: string;
  created_at: string;
}

export interface DashboardRecentStockMovement {
  id: number;
  kind: string;
  sku: string;
  product_name: string;
  location: string;
  quantity: number;
  created_at: string;
}

export interface DashboardAnalytics {
  sales_graph: DashboardSalesGraphPoint[];
  top_selling_products: DashboardTopSellingRow[];
  top_selling_skus: DashboardTopSellingRow[];
  low_stock_products: DashboardLowStockRow[];
  recent_orders: DashboardRecentOrder[];
  recent_returns: DashboardRecentReturn[];
  recent_stock_movements: DashboardRecentStockMovement[];
}
