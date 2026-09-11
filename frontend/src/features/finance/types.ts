/** Shapes returned by `/api/v1/expenses/finance/` (Phase 13). */

export interface FinanceSummary {
  date_from: string;
  date_to: string;
  channel: string | null;
  gross_sales: string;
  taxable_sales: string;
  gst_collected: string;
  discounts: string;
  refunds: string;
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

export interface UnitProfit {
  serial_number: string;
  sale_id: number;
  sales_channel: string;
  purchase_cost: string;
  taxable_selling_value: string;
  amazon_fees: string;
  courier: string;
  advertising: string;
  other_charges: string;
  unit_profit: string;
}
